from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, and_
from app.config import settings
from app.database.models import Campaign, Contact, Sender, CampaignLog, CampaignStatus, SenderType
from app.services.telegram_sender import TelegramSenderService
from app.services.email_sender import EmailSenderService
from app.services.whatsapp_sender import WhatsAppSenderService
from app.services.sms_sender import SMSSenderService
from app.services.viber_sender import ViberSenderService
from datetime import datetime
import asyncio
import logging
import time

# Настройка Celery
celery_app = Celery(
    'telegram_sender',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000
)

# Настройка БД для Celery
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

logger = logging.getLogger(__name__)

async def get_async_db():
    """Получение асинхронной сессии БД"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@celery_app.task(bind=True)
def start_campaign_task(self, campaign_id: int):
    """Запуск кампании рассылки"""
    return asyncio.run(run_campaign_async(self, campaign_id))

async def run_campaign_async(task, campaign_id: int):
    """Асинхронное выполнение кампании"""
    try:
        async for db in get_async_db():
            # Получаем кампанию
            campaign = await db.get(Campaign, campaign_id)
            if not campaign:
                logger.error(f"Campaign {campaign_id} not found")
                return {"status": "error", "message": "Campaign not found"}
            
            # Проверяем статус
            if campaign.status != CampaignStatus.DRAFT:
                logger.warning(f"Campaign {campaign_id} is not in draft status")
                return {"status": "error", "message": "Campaign is not in draft status"}
            
            # Обновляем статус
            campaign.status = CampaignStatus.RUNNING
            campaign.started_at = datetime.utcnow()
            await db.commit()
            
            logger.info(f"Starting campaign {campaign_id}")
            
            # Получаем отправителя
            sender = await db.get(Sender, campaign.sender_id)
            if not sender or not sender.is_active:
                campaign.status = CampaignStatus.FAILED
                await db.commit()
                return {"status": "error", "message": "Sender not found or inactive"}
            
            # Получаем контакты для рассылки
            result = await db.execute(
                select(Contact).where(
                    and_(
                        Contact.user_id == campaign.user_id,
                        Contact.type == campaign.type,
                        Contact.is_active == True
                    )
                )
            )
            contacts = result.scalars().all()
            
            if not contacts:
                campaign.status = CampaignStatus.COMPLETED
                campaign.completed_at = datetime.utcnow()
                await db.commit()
                return {"status": "completed", "message": "No contacts found"}
            
            campaign.total_contacts = len(contacts)
            await db.commit()
            
            # Инициализируем сервис отправки
            sender_service = get_sender_service(campaign.type, sender.config)
            if not sender_service:
                campaign.status = CampaignStatus.FAILED
                await db.commit()
                return {"status": "error", "message": "Invalid sender service"}
            
            # Выполняем рассылку
            sent_count = 0
            failed_count = 0
            
            batch_size = campaign.batch_size or 10
            delay_seconds = campaign.delay_seconds or 1
            
            for i in range(0, len(contacts), batch_size):
                # Проверяем, не остановлена ли кампания
                await db.refresh(campaign)
                if campaign.status == CampaignStatus.PAUSED:
                    logger.info(f"Campaign {campaign_id} paused")
                    break
                elif campaign.status != CampaignStatus.RUNNING:
                    logger.info(f"Campaign {campaign_id} stopped")
                    break
                
                batch = contacts[i:i + batch_size]
                
                for contact in batch:
                    try:
                        # Подготавливаем сообщение с переменными
                        message_text = prepare_message(
                            campaign.message,
                            contact.first_name,
                            contact.last_name
                        )
                        
                        # Отправляем сообщение
                        success = await sender_service.send_message(
                            contact.identifier,
                            message_text,
                            campaign.subject
                        )
                        
                        # Логируем результат
                        log_entry = CampaignLog(
                            campaign_id=campaign.id,
                            contact_identifier=contact.identifier,
                            status="sent" if success else "failed",
                            sent_at=datetime.utcnow()
                        )
                        
                        if success:
                            sent_count += 1
                        else:
                            failed_count += 1
                            log_entry.error_message = "Failed to send message"
                        
                        db.add(log_entry)
                        
                        # Обновляем прогресс
                        task.update_state(
                            state='PROGRESS',
                            meta={
                                'current': sent_count + failed_count,
                                'total': len(contacts),
                                'sent': sent_count,
                                'failed': failed_count
                            }
                        )
                        
                        # Задержка между сообщениями
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)
                    
                    except Exception as e:
                        logger.error(f"Error sending message to {contact.identifier}: {e}")
                        failed_count += 1
                        
                        log_entry = CampaignLog(
                            campaign_id=campaign.id,
                            contact_identifier=contact.identifier,
                            status="failed",
                            error_message=str(e),
                            sent_at=datetime.utcnow()
                        )
                        db.add(log_entry)
                
                # Сохраняем промежуточные результаты
                campaign.sent_count = sent_count
                campaign.failed_count = failed_count
                await db.commit()
                
                # Задержка между батчами
                if i + batch_size < len(contacts) and delay_seconds > 0:
                    time.sleep(delay_seconds * 2)
            
            # Завершаем кампанию
            campaign.sent_count = sent_count
            campaign.failed_count = failed_count
            campaign.completed_at = datetime.utcnow()
            
            if campaign.status == CampaignStatus.RUNNING:
                campaign.status = CampaignStatus.COMPLETED
            
            await db.commit()
            
            logger.info(f"Campaign {campaign_id} completed: {sent_count} sent, {failed_count} failed")
            
            return {
                "status": "completed",
                "sent": sent_count,
                "failed": failed_count,
                "total": len(contacts)
            }
    
    except Exception as e:
        logger.error(f"Error in campaign {campaign_id}: {e}", exc_info=True)
        
        # Обновляем статус кампании при ошибке
        try:
            async for db in get_async_db():
                campaign = await db.get(Campaign, campaign_id)
                if campaign:
                    campaign.status = CampaignStatus.FAILED
                    await db.commit()
        except:
            pass
        
        return {"status": "error", "message": str(e)}

def get_sender_service(sender_type: SenderType, config: dict):
    """Получение сервиса отправки по типу"""
    try:
        if sender_type == SenderType.TELEGRAM:
            return TelegramSenderService(config)
        elif sender_type == SenderType.EMAIL:
            return EmailSenderService(config)
        elif sender_type == SenderType.WHATSAPP:
            return WhatsAppSenderService(config)
        elif sender_type == SenderType.SMS:
            return SMSSenderService(config)
        elif sender_type == SenderType.VIBER:
            return ViberSenderService(config)
        else:
            return None
    except Exception as e:
        logger.error(f"Error creating sender service for {sender_type}: {e}")
        return None

def prepare_message(template: str, first_name: str = None, last_name: str = None) -> str:
    """Подготовка сообщения с переменными"""
    message = template
    
    # Заменяем переменные
    if first_name:
        message = message.replace("{first_name}", first_name)
    if last_name:
        message = message.replace("{last_name}", last_name)
    
    message = message.replace("{datetime}", datetime.now().strftime("%d.%m.%Y %H:%M"))
    
    return message

@celery_app.task
def pause_campaign_task(campaign_id: int):
    """Приостановка кампании"""
    return asyncio.run(update_campaign_status(campaign_id, CampaignStatus.PAUSED))

@celery_app.task
def resume_campaign_task(campaign_id: int):
    """Возобновление кампании"""
    return asyncio.run(update_campaign_status(campaign_id, CampaignStatus.RUNNING))

@celery_app.task
def stop_campaign_task(campaign_id: int):
    """Остановка кампании"""
    return asyncio.run(update_campaign_status(campaign_id, CampaignStatus.COMPLETED))

async def update_campaign_status(campaign_id: int, status: CampaignStatus):
    """Обновление статуса кампании"""
    try:
        async for db in get_async_db():
            campaign = await db.get(Campaign, campaign_id)
            if campaign:
                campaign.status = status
                if status == CampaignStatus.COMPLETED:
                    campaign.completed_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Campaign {campaign_id} status updated to {status.value}")
                return {"status": "success"}
            else:
                return {"status": "error", "message": "Campaign not found"}
    except Exception as e:
        logger.error(f"Error updating campaign {campaign_id}: {e}")
        return {"status": "error", "message": str(e)}

# Периодические задачи
@celery_app.task
def cleanup_old_logs():
    """Очистка старых логов (запускается по расписанию)"""
    return asyncio.run(cleanup_old_logs_async())

async def cleanup_old_logs_async():
    """Асинхронная очистка старых логов"""
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        async for db in get_async_db():
            result = await db.execute(
                select(CampaignLog).where(CampaignLog.sent_at < cutoff_date)
            )
            old_logs = result.scalars().all()
            
            for log in old_logs:
                await db.delete(log)
            
            await db.commit()
            logger.info(f"Cleaned up {len(old_logs)} old campaign logs")
            
            return {"status": "success", "cleaned": len(old_logs)}
    
    except Exception as e:
        logger.error(f"Error cleaning up logs: {e}")
        return {"status": "error", "message": str(e)}

# Настройка периодических задач
celery_app.conf.beat_schedule = {
    'cleanup-old-logs': {
        'task': 'app.tasks.campaigns.cleanup_old_logs',
        'schedule': 24 * 60 * 60,  # Каждый день
    },
}