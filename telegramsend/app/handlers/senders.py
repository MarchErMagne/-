from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.database import get_db
from app.database.models import User, Sender, SenderType
from app.utils.keyboards import sender_type_keyboard, back_keyboard, confirm_keyboard
from app.utils.decorators import handle_errors, log_user_action, subscription_required
from app.utils.validators import validate_email_address, validate_telegram_api_settings, validate_phone_number
from app.config import SUBSCRIPTION_PLANS
import json
import logging

router = Router()
logger = logging.getLogger(__name__)

class SenderStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_telegram_api_id = State()
    waiting_for_telegram_api_hash = State()
    waiting_for_telegram_phone = State()
    waiting_for_email_host = State()
    waiting_for_email_port = State()
    waiting_for_email_login = State()
    waiting_for_email_password = State()
    waiting_for_whatsapp_token = State()
    waiting_for_sms_api_key = State()
    waiting_for_viber_api_key = State()

@router.message(F.text == "📧 Отправители")
@subscription_required()
@handle_errors
@log_user_action("senders_menu")
async def senders_menu(message: types.Message, user: User, db: AsyncSession):
    """Меню управления отправителями"""
    # Получаем количество отправителей пользователя
    result = await db.execute(
        select(func.count(Sender.id)).where(Sender.user_id == user.id)
    )
    senders_count = result.scalar()
    
    # Проверяем лимиты
    plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
    limit = plan["senders_limit"]
    
    # Получаем список отправителей
    result = await db.execute(
        select(Sender).where(Sender.user_id == user.id).order_by(Sender.created_at.desc())
    )
    senders = result.scalars().all()
    
    senders_text = (
        f"📧 <b>Мои отправители</b>\n\n"
        f"📊 <b>Использовано:</b> {senders_count}/{limit}\n\n"
    )
    
    if senders:
        senders_text += "<b>Подключенные отправители:</b>\n\n"
        
        type_icons = {
            SenderType.TELEGRAM: "📱",
            SenderType.EMAIL: "📧", 
            SenderType.WHATSAPP: "💬",
            SenderType.SMS: "📞",
            SenderType.VIBER: "🟣"
        }
        
        for sender in senders:
            status_icon = "✅" if sender.is_verified else "⚠️"
            type_icon = type_icons.get(sender.type, "❓")
            
            senders_text += (
                f"{type_icon} <b>{sender.name}</b>\n"
                f"   {status_icon} {sender.type.value.capitalize()}\n"
                f"   📅 Добавлен: {sender.created_at.strftime('%d.%m.%Y')}\n\n"
            )
    else:
        senders_text += "📭 <b>У вас пока нет подключенных отправителей</b>\n\n"
    
    if senders_count < limit:
        senders_text += "➕ Вы можете добавить новый отправитель, выбрав тип ниже:"
        
        keyboard = sender_type_keyboard()
    else:
        senders_text += f"⚠️ Достигнут лимит отправителей для плана {user.subscription_plan.capitalize()}"
        keyboard = back_keyboard("back_to_menu")
    
    await message.answer(
        senders_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("sender_"))
@subscription_required()
@handle_errors
async def add_sender_type(callback: types.CallbackQuery, state: FSMContext, user: User, db: AsyncSession):
    """Выбор типа отправителя"""
    sender_type = callback.data.split("_")[1]
    
    # Проверяем лимиты
    result = await db.execute(
        select(func.count(Sender.id)).where(Sender.user_id == user.id)
    )
    senders_count = result.scalar()
    
    plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
    if senders_count >= plan["senders_limit"]:
        await callback.answer("Достигнут лимит отправителей", show_alert=True)
        return
    
    await state.update_data(sender_type=sender_type)
    
    type_names = {
        "telegram": "Telegram",
        "email": "Email",
        "whatsapp": "WhatsApp", 
        "sms": "SMS",
        "viber": "Viber"
    }
    
    type_descriptions = {
        "telegram": "Для рассылки через Telegram вам нужно получить API ID и API Hash на my.telegram.org",
        "email": "Для email рассылки нужны SMTP настройки вашего почтового сервера",
        "whatsapp": "Для WhatsApp рассылки нужен токен Twilio API",
        "sms": "Для SMS рассылки нужен API ключ SMS провайдера",
        "viber": "Для Viber рассылки нужен API ключ Viber Business"
    }
    
    setup_text = (
        f"⚙️ <b>Настройка отправителя {type_names[sender_type]}</b>\n\n"
        f"📝 {type_descriptions[sender_type]}\n\n"
        f"💡 <b>Введите название для этого отправителя:</b>\n"
        f"(например: 'Основной аккаунт', 'Промо рассылки' и т.д.)"
    )
    
    await callback.message.edit_text(
        setup_text,
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu")
    )
    
    await state.set_state(SenderStates.waiting_for_name)
    await callback.answer()

@router.message(SenderStates.waiting_for_name)
@handle_errors
async def process_sender_name(message: types.Message, state: FSMContext):
    """Обработка названия отправителя"""
    name = message.text.strip()
    
    if len(name) < 3:
        await message.answer("Название должно содержать минимум 3 символа")
        return
    
    if len(name) > 50:
        await message.answer("Название не должно превышать 50 символов")
        return
    
    data = await state.get_data()
    sender_type = data["sender_type"]
    await state.update_data(sender_name=name)
    
    if sender_type == "telegram":
        await message.answer(
            "📱 <b>Настройка Telegram отправителя</b>\n\n"
            "1️⃣ Перейдите на https://my.telegram.org\n"
            "2️⃣ Авторизуйтесь по номеру телефона\n"
            "3️⃣ Создайте новое приложение\n\n"
            "📋 <b>Введите API ID:</b>",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_telegram_api_id)
        
    elif sender_type == "email":
        await message.answer(
            "📧 <b>Настройка Email отправителя</b>\n\n"
            "📋 <b>Введите SMTP хост:</b>\n"
            "(например: smtp.gmail.com, smtp.yandex.ru)",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_email_host)
        
    elif sender_type == "whatsapp":
        await message.answer(
            "💬 <b>Настройка WhatsApp отправителя</b>\n\n"
            "1️⃣ Зарегистрируйтесь на twilio.com\n"
            "2️⃣ Получите токен авторизации\n\n"
            "📋 <b>Введите Auth Token:</b>",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_whatsapp_token)
        
    elif sender_type == "sms":
        await message.answer(
            "📞 <b>Настройка SMS отправителя</b>\n\n"
            "📋 <b>Введите API ключ SMS провайдера:</b>",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_sms_api_key)
        
    elif sender_type == "viber":
        await message.answer(
            "🟣 <b>Настройка Viber отправителя</b>\n\n"
            "📋 <b>Введите API ключ Viber:</b>",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_viber_api_key)

@router.message(SenderStates.waiting_for_telegram_api_id)
@handle_errors
async def process_telegram_api_id(message: types.Message, state: FSMContext):
    """Обработка Telegram API ID"""
    try:
        api_id = int(message.text.strip())
        if api_id <= 0:
            raise ValueError
        
        await state.update_data(api_id=api_id)
        await message.answer(
            "🔐 <b>Введите API Hash:</b>\n"
            "(32-символьная строка)",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_telegram_api_hash)
        
    except ValueError:
        await message.answer("❌ API ID должен быть положительным числом")

@router.message(SenderStates.waiting_for_telegram_api_hash)
@handle_errors
async def process_telegram_api_hash(message: types.Message, state: FSMContext):
    """Обработка Telegram API Hash"""
    api_hash = message.text.strip()
    
    is_valid, error = validate_telegram_api_settings("123", api_hash)
    if not is_valid and "API Hash" in error:
        await message.answer(f"❌ {error}")
        return
    
    await state.update_data(api_hash=api_hash)
    await message.answer(
        "📱 <b>Введите номер телефона:</b>\n"
        "(с кодом страны, например: +79123456789)",
        parse_mode="HTML"
    )
    await state.set_state(SenderStates.waiting_for_telegram_phone)

@router.message(SenderStates.waiting_for_telegram_phone)
@handle_errors
async def process_telegram_phone(message: types.Message, state: FSMContext):
    """Обработка номера телефона для Telegram"""
    phone = message.text.strip()
    
    is_valid, clean_phone = validate_phone_number(phone)
    if not is_valid:
        await message.answer(f"❌ {clean_phone}")
        return
    
    data = await state.get_data()
    
    # Создаем отправителя
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        sender_config = {
            "api_id": data["api_id"],
            "api_hash": data["api_hash"],
            "phone": clean_phone
        }
        
        sender = Sender(
            user_id=user.id,
            name=data["sender_name"],
            type=SenderType.TELEGRAM,
            config=sender_config,
            is_active=True,
            is_verified=False
        )
        
        db.add(sender)
        await db.commit()
        
        await message.answer(
            "✅ <b>Telegram отправитель добавлен!</b>\n\n"
            "⚠️ Для активации потребуется авторизация через код из SMS\n"
            "Это произойдет при первой отправке сообщений.",
            parse_mode="HTML",
            reply_markup=back_keyboard("senders_menu")
        )
        
        await state.clear()
        logger.info(f"Telegram sender added for user {user.telegram_id}")

@router.message(SenderStates.waiting_for_email_host)
@handle_errors
async def process_email_host(message: types.Message, state: FSMContext):
    """Обработка SMTP хоста"""
    host = message.text.strip()
    
    if not host:
        await message.answer("❌ SMTP хост не может быть пустым")
        return
    
    await state.update_data(smtp_host=host)
    await message.answer(
        "🔢 <b>Введите SMTP порт:</b>\n"
        "(обычно 587 для TLS или 465 для SSL)",
        parse_mode="HTML"
    )
    await state.set_state(SenderStates.waiting_for_email_port)

@router.message(SenderStates.waiting_for_email_port)
@handle_errors
async def process_email_port(message: types.Message, state: FSMContext):
    """Обработка SMTP порта"""
    try:
        port = int(message.text.strip())
        if port < 1 or port > 65535:
            raise ValueError
        
        await state.update_data(smtp_port=port)
        await message.answer(
            "📧 <b>Введите email адрес:</b>",
            parse_mode="HTML"
        )
        await state.set_state(SenderStates.waiting_for_email_login)
        
    except ValueError:
        await message.answer("❌ Порт должен быть числом от 1 до 65535")

@router.message(SenderStates.waiting_for_email_login)
@handle_errors
async def process_email_login(message: types.Message, state: FSMContext):
    """Обработка email логина"""
    email = message.text.strip()
    
    is_valid, clean_email = validate_email_address(email)
    if not is_valid:
        await message.answer(f"❌ {clean_email}")
        return
    
    await state.update_data(email=clean_email)
    await message.answer(
        "🔐 <b>Введите пароль:</b>\n"
        "(рекомендуется использовать App Password)",
        parse_mode="HTML"
    )
    await state.set_state(SenderStates.waiting_for_email_password)

@router.message(SenderStates.waiting_for_email_password)
@handle_errors
async def process_email_password(message: types.Message, state: FSMContext):
    """Обработка email пароля"""
    password = message.text.strip()
    
    if not password:
        await message.answer("❌ Пароль не может быть пустым")
        return
    
    data = await state.get_data()
    
    # Создаем отправителя
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        sender_config = {
            "smtp_host": data["smtp_host"],
            "smtp_port": data["smtp_port"],
            "email": data["email"],
            "password": password,  # В продакшене нужно шифровать!
            "use_tls": True
        }
        
        sender = Sender(
            user_id=user.id,
            name=data["sender_name"],
            type=SenderType.EMAIL,
            config=sender_config,
            is_active=True,
            is_verified=False
        )
        
        db.add(sender)
        await db.commit()
        
        await message.answer(
            "✅ <b>Email отправитель добавлен!</b>\n\n"
            "⚠️ Проверка подключения произойдет при первой отправке",
            parse_mode="HTML",
            reply_markup=back_keyboard("senders_menu")
        )
        
        await state.clear()
        logger.info(f"Email sender added for user {user.telegram_id}")

# Аналогично добавляем обработчики для WhatsApp, SMS и Viber
@router.callback_query(F.data == "senders_menu")
@handle_errors
async def back_to_senders_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в меню отправителей"""
    await state.clear()
    await senders_menu(callback.message)