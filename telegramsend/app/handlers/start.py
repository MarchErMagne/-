from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import User, SubscriptionStatus
from app.utils.keyboards import main_menu_keyboard, subscription_keyboard
from app.utils.decorators import handle_errors, log_user_action
from app.config import SUBSCRIPTION_PLANS
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
@handle_errors
@log_user_action("start_command")
async def start_command(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
    user_data = message.from_user
    
    # Получаем или создаем пользователя
    async for db in get_db():
        # Проверяем существование пользователя
        result = await db.execute(
            select(User).where(User.telegram_id == user_data.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Создаем нового пользователя
            user = User(
                telegram_id=user_data.id,
                username=user_data.username,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                language_code=user_data.language_code or "ru"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)  # Обновляем объект после сохранения
            logger.info(f"New user created: {user_data.id}")
            
            # Приветствие для нового пользователя
            welcome_text = (
                "🚀 <b>Добро пожаловать в TelegramSender Pro!</b>\n\n"
                "Это мощная платформа для массовых рассылок с поддержкой:\n"
                "📱 Telegram\n"
                "📧 Email\n" 
                "💬 WhatsApp\n"
                "📞 SMS\n"
                "🟣 Viber\n\n"
                "🎯 <b>Возможности:</b>\n"
                "• Умные рассылки с настройкой интервалов\n"
                "• Детальная аналитика и отчеты\n"
                "• AI-ассистент для создания контента\n"
                "• Управление контактами и сегментация\n"
                "• Защита от спам-фильтров\n\n"
                "💰 <b>Тарифные планы:</b>\n"
            )
            
            for plan_id, plan in SUBSCRIPTION_PLANS.items():
                price_usd = plan["price"] / 100
                welcome_text += f"• <b>{plan['name']}</b> - ${price_usd:.2f}/мес\n"
                for feature in plan["features"]:
                    welcome_text += f"  ✓ {feature}\n"
                welcome_text += "\n"
            
            welcome_text += (
                "🎁 <b>Специальное предложение!</b>\n"
                "Попробуйте любой план бесплатно в течение 3 дней!\n\n"
                "Нажмите кнопку ниже, чтобы выбрать подписку и начать работу."
            )
            
            await message.answer(
                welcome_text,
                parse_mode="HTML",
                reply_markup=subscription_keyboard()
            )
            
        else:
            # Обновляем данные существующего пользователя
            user.username = user_data.username
            user.first_name = user_data.first_name
            user.last_name = user_data.last_name
            user.updated_at = datetime.utcnow()
            await db.commit()
            
            # Проверяем статус подписки
            subscription_text = ""
            if user.subscription_status == SubscriptionStatus.ACTIVE:
                if user.subscription_expires:
                    days_left = (user.subscription_expires - datetime.utcnow()).days
                    if days_left > 0:
                        subscription_text = f"✅ Активная подписка: {user.subscription_plan.capitalize()}\n📅 Осталось дней: {days_left}\n\n"
                    else:
                        # Подписка истекла
                        user.subscription_status = SubscriptionStatus.EXPIRED
                        await db.commit()
                        subscription_text = "⚠️ Ваша подписка истекла! Продлите для продолжения работы.\n\n"
                else:
                    subscription_text = f"✅ Активная подписка: {user.subscription_plan.capitalize()}\n\n"
            else:
                subscription_text = "⚠️ У вас нет активной подписки. Выберите план для начала работы.\n\n"
            
            welcome_back_text = (
                f"👋 <b>С возвращением, {user.first_name}!</b>\n\n"
                f"{subscription_text}"
                "🎛 <b>Главное меню:</b>\n"
                "📊 <b>Мои кампании</b> - управление рассылками\n"
                "📧 <b>Отправители</b> - настройка аккаунтов\n"
                "👥 <b>Контакты</b> - управление базой\n"
                "📈 <b>Аналитика</b> - отчеты и статистика\n"
                "💳 <b>Подписка</b> - тарифы и оплата\n"
                "🤖 <b>AI-Ассистент</b> - помощь с контентом\n\n"
                "Выберите нужный раздел в меню ниже ⬇️"
            )
            
            await message.answer(
                welcome_back_text,
                parse_mode="HTML",
                reply_markup=main_menu_keyboard()
            )

@router.message(F.text == "ℹ️ Помощь")
@handle_errors
@log_user_action("help_command")
async def help_command(message: types.Message):
    """Обработчик помощи"""
    help_text = (
        "📚 <b>Справка по использованию бота</b>\n\n"
        "🔧 <b>Основные функции:</b>\n\n"
        "📊 <b>Кампании</b>\n"
        "• Создание рассылок для разных платформ\n"
        "• Настройка интервалов и батчей\n"
        "• Мониторинг статуса отправки\n\n"
        "📧 <b>Отправители</b>\n"
        "• Добавление аккаунтов для рассылки\n"
        "• Telegram: API ID + API Hash\n"
        "• Email: SMTP настройки\n"
        "• WhatsApp: Twilio аккаунт\n"
        "• SMS/Viber: API ключи\n\n"
        "👥 <b>Контакты</b>\n"
        "• Загрузка .txt файлов\n"
        "• Ручное добавление\n"
        "• Управление тегами\n"
        "• Черный список\n\n"
        "📈 <b>Аналитика</b>\n"
        "• Статистика доставки\n"
        "• Открытия и клики\n"
        "• Экспорт отчетов\n\n"
        "🤖 <b>AI-Ассистент</b>\n"
        "• Генерация текстов\n"
        "• Проверка на спам\n"
        "• Улучшение CTA\n\n"
        "📞 <b>Поддержка:</b> @support_username"
    )
    
    await message.answer(help_text, parse_mode="HTML")

@router.message(F.text == "⚙️ Настройки")
@handle_errors
@log_user_action("settings_command")
async def settings_command(message: types.Message):
    """Обработчик настроек"""
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("Пользователь не найден. Используйте /start")
            return
        
        settings_text = (
            "⚙️ <b>Настройки профиля</b>\n\n"
            f"👤 <b>Имя:</b> {user.first_name or 'Не указано'}\n"
            f"📧 <b>Username:</b> @{user.username or 'Не указан'}\n"
            f"🌐 <b>Язык:</b> {user.language_code}\n"
            f"📅 <b>Регистрация:</b> {user.created_at.strftime('%d.%m.%Y')}\n"
            f"💳 <b>Подписка:</b> {user.subscription_plan or 'Нет'}\n"
            f"📊 <b>Статус:</b> {user.subscription_status.value if user.subscription_status else 'Неактивна'}\n\n"
            "Для изменения настроек обратитесь в поддержку."
        )
        
        await message.answer(settings_text, parse_mode="HTML")

@router.callback_query(F.data == "back_to_menu")
@handle_errors
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    
    # Получаем пользователя
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("Пользователь не найден. Используйте /start")
            return
        
        # Проверяем статус подписки
        subscription_text = ""
        if user.subscription_status == SubscriptionStatus.ACTIVE:
            if user.subscription_expires:
                days_left = (user.subscription_expires - datetime.utcnow()).days
                if days_left > 0:
                    subscription_text = f"✅ Активная подписка: {user.subscription_plan.capitalize()}\n📅 Осталось дней: {days_left}\n\n"
                else:
                    # Подписка истекла
                    user.subscription_status = SubscriptionStatus.EXPIRED
                    await db.commit()
                    subscription_text = "⚠️ Ваша подписка истекла! Продлите для продолжения работы.\n\n"
            else:
                subscription_text = f"✅ Активная подписка: {user.subscription_plan.capitalize()}\n\n"
        else:
            subscription_text = "⚠️ У вас нет активной подписки. Выберите план для начала работы.\n\n"
        
        main_menu_text = (
            f"🏠 <b>Главное меню</b>\n\n"
            f"{subscription_text}"
            "🎛 <b>Разделы:</b>\n"
            "📊 <b>Мои кампании</b> - управление рассылками\n"
            "📧 <b>Отправители</b> - настройка аккаунтов\n"
            "👥 <b>Контакты</b> - управление базой\n"
            "📈 <b>Аналитика</b> - отчеты и статистика\n"
            "💳 <b>Подписка</b> - тарифы и оплата\n"
            "🤖 <b>AI-Ассистент</b> - помощь с контентом\n\n"
            "Выберите нужный раздел:"
        )
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="📊 Кампании", callback_data="campaigns_menu"),
                    types.InlineKeyboardButton(text="📧 Отправители", callback_data="senders_menu")
                ],
                [
                    types.InlineKeyboardButton(text="👥 Контакты", callback_data="contacts_menu"),
                    types.InlineKeyboardButton(text="📈 Аналитика", callback_data="analytics_menu")
                ],
                [
                    types.InlineKeyboardButton(text="💳 Подписка", callback_data="subscription_menu"),
                    types.InlineKeyboardButton(text="🤖 AI-Ассистент", callback_data="ai_assistant_menu")
                ]
            ]
        )
        
        await callback.message.edit_text(
            main_menu_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        await callback.answer()