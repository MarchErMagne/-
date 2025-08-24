"""Декораторы для обработчиков"""
from functools import wraps
from typing import Callable, Any
from aiogram import types
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.database.models import User, SubscriptionStatus
from app.config import SUBSCRIPTION_PLANS
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def subscription_required(plans: list = None):
    """Декоратор для проверки подписки"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.TelegramObject, *args, **kwargs):
            user_id = None
            
            if isinstance(event, Message):
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery):
                user_id = event.from_user.id
            
            if not user_id:
                return await event.answer("Ошибка авторизации")
            
            # Получаем сессию БД
            async for db in get_db():
                # Получаем пользователя по telegram_id
                from sqlalchemy import select
                result = await db.execute(
                    select(User).where(User.telegram_id == user_id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    if isinstance(event, Message):
                        return await event.answer("Пользователь не найден. Используйте /start")
                    elif isinstance(event, CallbackQuery):
                        return await event.answer("Пользователь не найден. Используйте /start", show_alert=True)
                
                # Проверяем статус подписки
                if user.subscription_status != SubscriptionStatus.ACTIVE:
                    message_text = (
                        "🔒 Для этой функции нужна активная подписка!\n"
                        "Перейдите в раздел 'Подписка' для оформления."
                    )
                    if isinstance(event, Message):
                        return await event.answer(message_text)
                    elif isinstance(event, CallbackQuery):
                        return await event.answer(message_text, show_alert=True)
                
                # Проверяем срок действия
                if user.subscription_expires and user.subscription_expires < datetime.utcnow():
                    user.subscription_status = SubscriptionStatus.EXPIRED
                    await db.commit()
                    message_text = (
                        "⏰ Ваша подписка истекла!\n"
                        "Продлите подписку для продолжения работы."
                    )
                    if isinstance(event, Message):
                        return await event.answer(message_text)
                    elif isinstance(event, CallbackQuery):
                        return await event.answer(message_text, show_alert=True)
                
                # Проверяем план подписки если указан
                if plans and user.subscription_plan not in plans:
                    plan_names = [SUBSCRIPTION_PLANS[p]["name"] for p in plans]
                    message_text = (
                        f"🔒 Эта функция доступна только в планах: {', '.join(plan_names)}\n"
                        "Обновите подписку для доступа."
                    )
                    if isinstance(event, Message):
                        return await event.answer(message_text)
                    elif isinstance(event, CallbackQuery):
                        return await event.answer(message_text, show_alert=True)
                
                # Добавляем пользователя в kwargs
                kwargs['user'] = user
                kwargs['db'] = db
                
                return await func(event, *args, **kwargs)
        
        return wrapper
    return decorator

def admin_required(func: Callable) -> Callable:
    """Декоратор для админских команд"""
    @wraps(func)
    async def wrapper(event: types.TelegramObject, *args, **kwargs):
        user_id = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        # Импортируем функцию проверки админа
        from app.handlers.admin import is_admin
        
        if not is_admin(user_id):
            message_text = "🚫 У вас нет прав администратора"
            if isinstance(event, Message):
                return await event.answer(message_text)
            elif isinstance(event, CallbackQuery):
                return await event.answer(message_text, show_alert=True)
        
        return await func(event, *args, **kwargs)
    
    return wrapper

def rate_limit(limit: int = 5, window: int = 60):
    """Декоратор для ограничения частоты запросов"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.TelegramObject, *args, **kwargs):
            # Здесь можно добавить логику rate limiting через Redis
            return await func(event, *args, **kwargs)
        return wrapper
    return decorator

def log_user_action(action: str):
    """Декоратор для логирования действий пользователей"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(event: types.TelegramObject, *args, **kwargs):
            user_id = None
            username = None
            
            if isinstance(event, Message):
                user_id = event.from_user.id
                username = event.from_user.username
            elif isinstance(event, CallbackQuery):
                user_id = event.from_user.id
                username = event.from_user.username
            
            logger.info(f"User {user_id} (@{username}) performed action: {action}")
            
            return await func(event, *args, **kwargs)
        return wrapper
    return decorator

def handle_errors(func: Callable) -> Callable:
    """Декоратор для обработки ошибок"""
    @wraps(func)
    async def wrapper(event: types.TelegramObject, *args, **kwargs):
        try:
            return await func(event, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            
            error_msg = "😔 Произошла ошибка. Попробуйте позже или обратитесь в поддержку."
            
            if isinstance(event, Message):
                await event.answer(error_msg)
            elif isinstance(event, CallbackQuery):
                await event.answer(error_msg, show_alert=True)
    
    return wrapper