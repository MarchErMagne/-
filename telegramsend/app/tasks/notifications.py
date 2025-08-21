from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, and_
from app.config import settings
from app.database.models import User, Subscription, SubscriptionStatus
from datetime import datetime, timedelta
import asyncio
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

# Настройка Celery
celery_app = Celery(
    'notifications',
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
def check_expiring_subscriptions():
    """Проверка истекающих подписок"""
    return asyncio.run(check_expiring_subscriptions_async())

async def check_expiring_subscriptions_async():
    """Асинхронная проверка истекающих подписок"""
    try:
        bot = Bot(token=settings.BOT_TOKEN)
        
        async for db in get_async_db():
            # Ищем подписки, которые истекают в ближайшие 3 дня
            expiry_threshold = datetime.utcnow() + timedelta(days=3)
            
            result = await db.execute(
                select(User).where(
                    and_(
                        User.subscription_status == SubscriptionStatus.ACTIVE,
                        User.subscription_expires <= expiry_threshold,
                        User.subscription_expires > datetime.utcnow()
                    )
                )
            )
            
            users = result.scalars().all()
            
            notifications_sent = 0
            
            for user in users:
                try:
                    days_left = (user.subscription_expires - datetime.utcnow()).days
                    
                    if days_left <= 1:
                        # Подписка истекает завтра или сегодня
                        message = (
                            "⚠️ <b>Внимание! Ваша подписка истекает!</b>\n\n"
                            f"📅 Осталось: {days_left} дн.\n"
                            f"💼 План: {user.subscription_plan.capitalize()}\n\n"
                            "Продлите подписку, чтобы не потерять доступ к функциям бота.\n\n"
                            "Нажмите /start → 💳 Подписка для продления"
                        )
                    elif days_left <= 3:
                        # Подписка истекает в ближайшие 3 дня
                        message = (
                            "🔔 <b>Напоминание о подписке</b>\n\n"
                            f"📅 Ваша подписка истекает через {days_left} дн.\n"
                            f"💼 План: {user.subscription_plan.capitalize()}\n\n"
                            "Рекомендуем продлить подписку заранее.\n\n"
                            "Нажмите /start → 💳 Подписка"
                        )
                    else:
                        continue
                    
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=message,
                        parse_mode="HTML"
                    )
                    
                    notifications_sent += 1
                    logger.info(f"Expiry notification sent to user {user.telegram_id}")
                    
                    # Небольшая задержка между уведомлениями
                    await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.error(f"Error sending expiry notification to {user.telegram_id}: {e}")
            
            await bot.session.close()
            
            logger.info(f"Expiry notifications sent: {notifications_sent}")
            return {"status": "success", "notifications_sent": notifications_sent}
    
    except Exception as e:
        logger.error(f"Error in check_expiring_subscriptions: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def deactivate_expired_subscriptions():
    """Деактивация истекших подписок"""
    return asyncio.run(deactivate_expired_subscriptions_async())

async def deactivate_expired_subscriptions_async():
    """Асинхронная деактивация истекших подписок"""
    try:
        bot = Bot(token=settings.BOT_TOKEN)
        
        async for db in get_async_db():
            # Ищем истекшие подписки
            result = await db.execute(
                select(User).where(
                    and_(
                        User.subscription_status == SubscriptionStatus.ACTIVE,
                        User.subscription_expires <= datetime.utcnow()
                    )
                )
            )
            
            users = result.scalars().all()
            deactivated_count = 0
            
            for user in users:
                try:
                    # Деактивируем подписку
                    user.subscription_status = SubscriptionStatus.EXPIRED
                    
                    # Уведомляем пользователя
                    message = (
                        "❌ <b>Ваша подписка истекла</b>\n\n"
                        f"💼 План: {user.subscription_plan.capitalize()}\n"
                        f"📅 Истекла: {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}\n\n"
                        "Для продолжения работы с ботом необходимо продлить подписку.\n\n"
                        "Нажмите /start → 💳 Подписка"
                    )
                    
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=message,
                        parse_mode="HTML"
                    )
                    
                    deactivated_count += 1
                    logger.info(f"Subscription expired for user {user.telegram_id}")
                    
                    await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.error(f"Error deactivating subscription for {user.telegram_id}: {e}")
            
            await db.commit()
            await bot.session.close()
            
            logger.info(f"Subscriptions deactivated: {deactivated_count}")
            return {"status": "success", "deactivated": deactivated_count}
    
    except Exception as e:
        logger.error(f"Error in deactivate_expired_subscriptions: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def send_campaign_completion_notification(campaign_id: int, user_id: int, stats: dict):
    """Уведомление о завершении кампании"""
    return asyncio.run(send_campaign_completion_notification_async(campaign_id, user_id, stats))

async def send_campaign_completion_notification_async(campaign_id: int, user_id: int, stats: dict):
    """Асинхронное уведомление о завершении кампании"""
    try:
        bot = Bot(token=settings.BOT_TOKEN)
        
        async for db in get_async_db():
            # Получаем информацию о кампании
            from app.database.models import Campaign
            campaign = await db.get(Campaign, campaign_id)
            
            if not campaign:
                return {"status": "error", "message": "Campaign not found"}
            
            # Формируем уведомление
            success_rate = 0
            if stats.get("total", 0) > 0:
                success_rate = (stats.get("sent", 0) / stats["total"]) * 100
            
            message = (
                f"✅ <b>Кампания '{campaign.name}' завершена!</b>\n\n"
                f"📊 <b>Результаты:</b>\n"
                f"• Отправлено: {stats.get('sent', 0)}\n"
                f"• Ошибок: {stats.get('failed', 0)}\n"
                f"• Всего: {stats.get('total', 0)}\n"
                f"• Успешность: {success_rate:.1f}%\n\n"
                f"📱 Тип: {campaign.type.value.capitalize()}\n"
                f"⏰ Завершено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            
            await bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="HTML"
            )
            
            await bot.session.close()
            
            logger.info(f"Campaign completion notification sent to user {user_id}")
            return {"status": "success"}
    
    except Exception as e:
        logger.error(f"Error sending campaign completion notification: {e}")
        return {"status": "error", "message": str(e)}

# Настройка периодических задач
celery_app.conf.beat_schedule.update({
    'check-expiring-subscriptions': {
        'task': 'app.tasks.notifications.check_expiring_subscriptions',
        'schedule': 12 * 60 * 60,  # Каждые 12 часов
    },
    'deactivate-expired-subscriptions': {
        'task': 'app.tasks.notifications.deactivate_expired_subscriptions', 
        'schedule': 60 * 60,  # Каждый час
    },
})