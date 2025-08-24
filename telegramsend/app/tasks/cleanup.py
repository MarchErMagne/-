from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text, and_
from app.config import settings
from app.database.models import (
    User, Campaign, CampaignLog, Payment, FileUpload, 
    Analytics, AIPrompt, SubscriptionStatus
)
from datetime import datetime, timedelta
import asyncio
import os
import logging

logger = logging.getLogger(__name__)

# Настройка Celery
celery_app = Celery(
    'cleanup',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Настройка БД
engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_async_db():
    """Получение асинхронной сессии БД"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

@celery_app.task
def cleanup_old_campaign_logs():
    """Очистка старых логов кампаний (старше 90 дней)"""
    return asyncio.run(cleanup_old_campaign_logs_async())

async def cleanup_old_campaign_logs_async():
    """Асинхронная очистка старых логов кампаний"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        async for db in get_async_db():
            # Подсчитываем количество логов для удаления
            count_result = await db.execute(
                select(func.count(CampaignLog.id)).where(CampaignLog.sent_at < cutoff_date)
            )
            logs_to_delete = count_result.scalar()
            
            if logs_to_delete > 0:
                # Удаляем старые логи
                result = await db.execute(
                    text("DELETE FROM campaign_logs WHERE sent_at < :cutoff_date"),
                    {"cutoff_date": cutoff_date}
                )
                
                await db.commit()
                logger.info(f"Cleaned up {logs_to_delete} old campaign logs")
                
                return {
                    "status": "success",
                    "deleted_logs": logs_to_delete,
                    "cutoff_date": cutoff_date.isoformat()
                }
            else:
                return {
                    "status": "success",
                    "deleted_logs": 0,
                    "message": "No old logs to delete"
                }
    
    except Exception as e:
        logger.error(f"Error cleaning up old campaign logs: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_expired_payments():
    """Очистка истекших неоплаченных инвойсов (старше 24 часов)"""
    return asyncio.run(cleanup_expired_payments_async())

async def cleanup_expired_payments_async():
    """Асинхронная очистка истекших платежей"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(hours=24)
        
        async for db in get_async_db():
            # Находим истекшие неоплаченные платежи
            result = await db.execute(
                select(Payment).where(
                    and_(
                        Payment.status == "pending",
                        Payment.created_at < cutoff_date
                    )
                )
            )
            expired_payments = result.scalars().all()
            
            deleted_count = 0
            for payment in expired_payments:
                await db.delete(payment)
                deleted_count += 1
            
            await db.commit()
            
            logger.info(f"Cleaned up {deleted_count} expired payments")
            
            return {
                "status": "success",
                "deleted_payments": deleted_count,
                "cutoff_date": cutoff_date.isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error cleaning up expired payments: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_old_files():
    """Очистка старых загруженных файлов (старше 30 дней)"""
    return asyncio.run(cleanup_old_files_async())

async def cleanup_old_files_async():
    """Асинхронная очистка старых файлов"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        async for db in get_async_db():
            # Находим старые файлы
            result = await db.execute(
                select(FileUpload).where(FileUpload.created_at < cutoff_date)
            )
            old_files = result.scalars().all()
            
            deleted_files = 0
            deleted_db_records = 0
            
            for file_record in old_files:
                # Удаляем физический файл
                if file_record.upload_path and os.path.exists(file_record.upload_path):
                    try:
                        os.remove(file_record.upload_path)
                        deleted_files += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file_record.upload_path}: {e}")
                
                # Удаляем запись из БД
                await db.delete(file_record)
                deleted_db_records += 1
            
            await db.commit()
            
            logger.info(f"Cleaned up {deleted_files} old files and {deleted_db_records} DB records")
            
            return {
                "status": "success",
                "deleted_files": deleted_files,
                "deleted_db_records": deleted_db_records,
                "cutoff_date": cutoff_date.isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error cleaning up old files: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_inactive_users():
    """Очистка неактивных пользователей (без подписки более 180 дней)"""
    return asyncio.run(cleanup_inactive_users_async())

async def cleanup_inactive_users_async():
    """Асинхронная очистка неактивных пользователей"""
    try:
        # Пользователи без активной подписки более 180 дней
        cutoff_date = datetime.utcnow() - timedelta(days=180)
        
        async for db in get_async_db():
            # Находим неактивных пользователей
            result = await db.execute(
                select(User).where(
                    and_(
                        User.subscription_status != SubscriptionStatus.ACTIVE,
                        User.created_at < cutoff_date,
                        # Дополнительная проверка - нет кампаний за последние 90 дней
                        ~User.id.in_(
                            select(Campaign.user_id).where(
                                Campaign.created_at > datetime.utcnow() - timedelta(days=90)
                            )
                        )
                    )
                )
            )
            inactive_users = result.scalars().all()
            
            deleted_count = 0
            for user in inactive_users:
                # Удаляем связанные данные
                # Контакты, кампании, логи и т.д. удалятся каскадно
                await db.delete(user)
                deleted_count += 1
            
            await db.commit()
            
            logger.info(f"Cleaned up {deleted_count} inactive users")
            
            return {
                "status": "success",
                "deleted_users": deleted_count,
                "cutoff_date": cutoff_date.isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error cleaning up inactive users: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_old_analytics():
    """Очистка старых записей аналитики (старше 1 года)"""
    return asyncio.run(cleanup_old_analytics_async())

async def cleanup_old_analytics_async():
    """Асинхронная очистка старой аналитики"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=365)
        
        async for db in get_async_db():
            result = await db.execute(
                text("DELETE FROM analytics WHERE timestamp < :cutoff_date"),
                {"cutoff_date": cutoff_date}
            )
            
            deleted_count = result.rowcount
            await db.commit()
            
            logger.info(f"Cleaned up {deleted_count} old analytics records")
            
            return {
                "status": "success",
                "deleted_analytics": deleted_count,
                "cutoff_date": cutoff_date.isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error cleaning up old analytics: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_old_ai_prompts():
    """Очистка старых AI промптов (старше 30 дней)"""
    return asyncio.run(cleanup_old_ai_prompts_async())

async def cleanup_old_ai_prompts_async():
    """Асинхронная очистка старых AI промптов"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        async for db in get_async_db():
            result = await db.execute(
                select(AIPrompt).where(AIPrompt.created_at < cutoff_date)
            )
            old_prompts = result.scalars().all()
            
            deleted_count = 0
            for prompt in old_prompts:
                await db.delete(prompt)
                deleted_count += 1
            
            await db.commit()
            
            logger.info(f"Cleaned up {deleted_count} old AI prompts")
            
            return {
                "status": "success",
                "deleted_prompts": deleted_count,
                "cutoff_date": cutoff_date.isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error cleaning up old AI prompts: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_temp_files():
    """Очистка временных файлов"""
    return asyncio.run(cleanup_temp_files_async())

async def cleanup_temp_files_async():
    """Асинхронная очистка временных файлов"""
    try:
        temp_dirs = [
            settings.UPLOAD_DIR,
            "/tmp",
            "temp"
        ]
        
        deleted_files = 0
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        for temp_dir in temp_dirs:
            if not os.path.exists(temp_dir):
                continue
            
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                
                try:
                    # Проверяем время последнего изменения
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_mtime < cutoff_time:
                        if os.path.isfile(file_path):
                            # Проверяем что это временный файл
                            if any(pattern in filename.lower() for pattern in ['tmp', 'temp', 'cache']):
                                os.remove(file_path)
                                deleted_files += 1
                
                except Exception as e:
                    logger.warning(f"Error processing temp file {file_path}: {e}")
        
        logger.info(f"Cleaned up {deleted_files} temporary files")
        
        return {
            "status": "success",
            "deleted_files": deleted_files
        }
    
    except Exception as e:
        logger.error(f"Error cleaning up temp files: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def full_cleanup():
    """Полная очистка всех старых данных"""
    return asyncio.run(full_cleanup_async())

async def full_cleanup_async():
    """Асинхронная полная очистка"""
    try:
        results = {}
        
        # Запускаем все задачи очистки
        cleanup_tasks = [
            ("campaign_logs", cleanup_old_campaign_logs_async()),
            ("expired_payments", cleanup_expired_payments_async()),
            ("old_files", cleanup_old_files_async()),
            ("old_analytics", cleanup_old_analytics_async()),
            ("old_ai_prompts", cleanup_old_ai_prompts_async()),
            ("temp_files", cleanup_temp_files_async())
        ]
        
        for task_name, task_coro in cleanup_tasks:
            try:
                result = await task_coro
                results[task_name] = result
            except Exception as e:
                logger.error(f"Error in {task_name} cleanup: {e}")
                results[task_name] = {"status": "error", "message": str(e)}
        
        # Подсчитываем общую статистику
        total_deleted = 0
        for result in results.values():
            if result.get("status") == "success":
                total_deleted += sum(
                    v for k, v in result.items() 
                    if k.startswith("deleted_") and isinstance(v, int)
                )
        
        logger.info(f"Full cleanup completed. Total items deleted: {total_deleted}")
        
        return {
            "status": "success",
            "total_deleted": total_deleted,
            "details": results,
            "completed_at": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in full cleanup: {e}")
        return {"status": "error", "message": str(e)}

# Настройка периодических задач очистки
celery_app.conf.beat_schedule.update({
    'cleanup-old-campaign-logs': {
        'task': 'app.tasks.cleanup.cleanup_old_campaign_logs',
        'schedule': 24 * 60 * 60,  # Каждый день
    },
    'cleanup-expired-payments': {
        'task': 'app.tasks.cleanup.cleanup_expired_payments',
        'schedule': 6 * 60 * 60,  # Каждые 6 часов
    },
    'cleanup-old-files': {
        'task': 'app.tasks.cleanup.cleanup_old_files',
        'schedule': 7 * 24 * 60 * 60,  # Каждую неделю
    },
    'cleanup-temp-files': {
        'task': 'app.tasks.cleanup.cleanup_temp_files',
        'schedule': 60 * 60,  # Каждый час
    },
    'full-cleanup': {
        'task': 'app.tasks.cleanup.full_cleanup',
        'schedule': 30 * 24 * 60 * 60,  # Каждые 30 дней
    }
})

# Добавляем недостающий импорт
from sqlalchemy import func