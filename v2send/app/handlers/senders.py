from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.database.models import User, Sender, SenderType, SubscriptionStatus
from app.utils.keyboards import sender_type_keyboard, back_keyboard, confirm_keyboard
from app.utils.decorators import handle_errors, log_user_action, subscription_required
from app.utils.validators import (
    validate_email_address,
    validate_telegram_api_settings,
    validate_phone_number,
)
from app.config import SUBSCRIPTION_PLANS

import logging

# --- Telethon (Telegram login flow) ---
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError,
)

router = Router()
logger = logging.getLogger(__name__)


class SenderStates(StatesGroup):
    # Общие
    waiting_for_name = State()

    # Telegram
    waiting_for_telegram_api_id = State()
    waiting_for_telegram_api_hash = State()
    waiting_for_telegram_phone = State()
    waiting_for_telegram_code = State()
    waiting_for_telegram_2fa = State()

    # Email
    waiting_for_email_host = State()
    waiting_for_email_port = State()
    waiting_for_email_login = State()
    waiting_for_email_password = State()

    # WhatsApp / SMS / Viber
    waiting_for_whatsapp_token = State()
    waiting_for_sms_api_key = State()
    waiting_for_viber_api_key = State()


# ======================= МЕНЮ ОТПРАВИТЕЛЕЙ =======================

@router.message(F.text == "📧 Отправители")
@subscription_required()
@handle_errors
@log_user_action("senders_menu")
async def senders_menu(message: types.Message, user: User, db: AsyncSession, **kwargs):
    """Главное меню отправителей."""
    count_q = await db.execute(select(func.count(Sender.id)).where(Sender.user_id == user.id))
    senders_count = count_q.scalar()

    plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
    limit = plan["senders_limit"]

    items_q = await db.execute(
        select(Sender).where(Sender.user_id == user.id).order_by(Sender.created_at.desc())
    )
    senders = items_q.scalars().all()

    type_icons = {
        SenderType.TELEGRAM: "📱",
        SenderType.EMAIL: "📧",
        SenderType.WHATSAPP: "💬",
        SenderType.SMS: "📞",
        SenderType.VIBER: "🟣"
    }

    text = (
        f"📧 <b>Мои отправители</b>\n\n"
        f"📊 <b>Использовано:</b> {senders_count}/{limit}\n\n"
    )

    if senders:
        text += "<b>Подключенные отправители:</b>\n\n"
        for s in senders:
            status_icon = "✅" if s.is_verified else "⚠️"
            type_icon = type_icons.get(s.type, "❓")
            text += (
                f"{type_icon} <b>{s.name}</b>\n"
                f"   {status_icon} {s.type.value.capitalize()}\n"
                f"   📅 Добавлен: {s.created_at.strftime('%d.%m.%Y')}\n\n"
            )
    else:
        text += "📭 <b>У вас пока нет подключенных отправителей</b>\n\n"

    # Клавиатура: кнопки добавления типов + меню удаления + назад
    if senders_count < limit:
        base_kb = sender_type_keyboard()
        kb_rows = list(base_kb.inline_keyboard) if base_kb and base_kb.inline_keyboard else []
        kb_rows.append([types.InlineKeyboardButton(text="🗑 Удалить отправителя", callback_data="senders_delete_menu")])
        kb_rows.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_rows)
    else:
        text += f"⚠️ Достигнут лимит отправителей для плана {user.subscription_plan.capitalize()}"
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🗑 Удалить отправителя", callback_data="senders_delete_menu")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
            ]
        )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "senders_menu")
@handle_errors
async def senders_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Переоткрытие меню отправителей (через callback)."""
    await state.clear()
    user_id = callback.from_user.id

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user:
            return await callback.answer("Пользователь не найден. Используйте /start", show_alert=True)

        if user.subscription_status != SubscriptionStatus.ACTIVE:
            return await callback.answer("🔒 Нужна активная подписка!", show_alert=True)

        count_q = await db.execute(select(func.count(Sender.id)).where(Sender.user_id == user.id))
        senders_count = count_q.scalar()

        plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
        limit = plan["senders_limit"]

        items_q = await db.execute(
            select(Sender).where(Sender.user_id == user.id).order_by(Sender.created_at.desc())
        )
        senders = items_q.scalars().all()

        type_icons = {
            SenderType.TELEGRAM: "📱",
            SenderType.EMAIL: "📧",
            SenderType.WHATSAPP: "💬",
            SenderType.SMS: "📞",
            SenderType.VIBER: "🟣"
        }

        text = (
            f"📧 <b>Мои отправители</b>\n\n"
            f"📊 <b>Использовано:</b> {senders_count}/{limit}\n\n"
        )

        if senders:
            text += "<b>Подключенные отправители:</b>\n\n"
            for s in senders:
                status_icon = "✅" if s.is_verified else "⚠️"
                type_icon = type_icons.get(s.type, "❓")
                text += (
                    f"{type_icon} <b>{s.name}</b>\n"
                    f"   {status_icon} {s.type.value.capitalize()}\n"
                    f"   📅 Добавлен: {s.created_at.strftime('%d.%m.%Y')}\n\n"
                )
        else:
            text += "📭 <b>У вас пока нет подключенных отправителей</b>\n\n"

        if senders_count < limit:
            base_kb = sender_type_keyboard()
            kb_rows = list(base_kb.inline_keyboard) if base_kb and base_kb.inline_keyboard else []
            kb_rows.append([types.InlineKeyboardButton(text="🗑 Удалить отправителя", callback_data="senders_delete_menu")])
            kb_rows.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_rows)
        else:
            text += f"⚠️ Достигнут лимит отправителей для плана {user.subscription_plan.capitalize()}"
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🗑 Удалить отправителя", callback_data="senders_delete_menu")],
                    [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
                ]
            )

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise

    await callback.answer()


# ======================= ДОБАВЛЕНИЕ ОТПРАВИТЕЛЯ: ВЫБОР ТИПА =======================

@router.callback_query(F.data.startswith("sender_"))
@handle_errors
async def add_sender_type(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа отправителя (telegram/email/...)."""
    sender_type = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user:
            return await callback.answer("Пользователь не найден", show_alert=True)

        count_q = await db.execute(select(func.count(Sender.id)).where(Sender.user_id == user.id))
        senders_count = count_q.scalar()

        plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
        if senders_count >= plan["senders_limit"]:
            return await callback.answer("Достигнут лимит отправителей", show_alert=True)

    await state.update_data(sender_type=sender_type)

    type_names = {
        "telegram": "Telegram",
        "email": "Email",
        "whatsapp": "WhatsApp",
        "sms": "SMS",
        "viber": "Viber"
    }

    type_descriptions = {
        "telegram": "Для рассылки через Telegram потребуется API ID и API Hash (my.telegram.org). Далее бот запросит код из Telegram для авторизации.",
        "email": "Для email рассылки нужны SMTP-настройки вашего почтового сервера.",
        "whatsapp": "Для WhatsApp рассылки нужен токен Twilio API.",
        "sms": "Для SMS рассылки нужен API-ключ SMS провайдера.",
        "viber": "Для Viber рассылки нужен API-ключ Viber Business.",
    }

    setup_text = (
        f"⚙️ <b>Настройка отправителя {type_names.get(sender_type, sender_type)}</b>\n\n"
        f"📝 {type_descriptions.get(sender_type, '')}\n\n"
        f"💡 <b>Введите название для этого отправителя:</b>\n"
        f"(например: 'Основной аккаунт', 'Промо рассылки')"
    )

    await callback.message.edit_text(setup_text, parse_mode="HTML", reply_markup=back_keyboard("senders_menu"))
    await state.set_state(SenderStates.waiting_for_name)
    await callback.answer()


@router.message(SenderStates.waiting_for_name)
@handle_errors
async def process_sender_name(message: types.Message, state: FSMContext):
    """Название отправителя."""
    name = (message.text or "").strip()
    if len(name) < 3:
        return await message.answer("❌ Название должно содержать минимум 3 символа")
    if len(name) > 50:
        return await message.answer("❌ Название не должно превышать 50 символов")

    data = await state.get_data()
    sender_type = data["sender_type"]
    await state.update_data(sender_name=name)

    if sender_type == "telegram":
        await message.answer(
            "📱 <b>Настройка Telegram отправителя</b>\n\n"
            "1️⃣ Перейдите на https://my.telegram.org\n"
            "2️⃣ Авторизуйтесь по номеру телефона\n"
            "3️⃣ Создайте приложение и получите API ID и API Hash\n\n"
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
            "📋 <b>Введите Auth Token (Twilio):</b>",
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


# ======================= TELEGRAM: API / PHONE / CODE / 2FA =======================

@router.message(SenderStates.waiting_for_telegram_api_id)
@handle_errors
async def process_telegram_api_id(message: types.Message, state: FSMContext):
    try:
        api_id = int((message.text or "").strip())
        if api_id <= 0:
            raise ValueError
    except ValueError:
        return await message.answer("❌ API ID должен быть положительным числом")

    await state.update_data(api_id=api_id)
    await message.answer("🔐 <b>Введите API Hash:</b>\n(32-символьная строка)", parse_mode="HTML")
    await state.set_state(SenderStates.waiting_for_telegram_api_hash)


@router.message(SenderStates.waiting_for_telegram_api_hash)
@handle_errors
async def process_telegram_api_hash(message: types.Message, state: FSMContext):
    api_hash = (message.text or "").strip()
    data = await state.get_data()
    api_id = str(data.get("api_id", ""))

    ok, err = validate_telegram_api_settings(api_id, api_hash)
    if not ok:
        return await message.answer(f"❌ {err}")

    await state.update_data(api_hash=api_hash)
    await message.answer(
        "📱 <b>Введите номер телефона:</b>\n(с кодом страны, например: +79123456789)",
        parse_mode="HTML"
    )
    await state.set_state(SenderStates.waiting_for_telegram_phone)


@router.message(SenderStates.waiting_for_telegram_phone)
@handle_errors
async def process_telegram_phone(message: types.Message, state: FSMContext):
    phone = (message.text or "").strip()
    ok, clean_phone = validate_phone_number(phone)
    if not ok:
        return await message.answer(f"❌ {clean_phone}")

    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(clean_phone)
    except PhoneNumberInvalidError:
        await client.disconnect()
        return await message.answer("❌ Такой номер не найден в Telegram. Проверьте и введите снова.")
    except Exception as e:
        await client.disconnect()
        logger.exception("send_code_request failed: %s", e)
        return await message.answer("⚠️ Не удалось отправить код. Попробуйте позже.")

    await state.update_data(
        tg_tmp_session=client.session.save(),
        tg_phone=clean_phone,
        tg_phone_code_hash=sent.phone_code_hash,
    )
    await client.disconnect()

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔁 Отправить код ещё раз", callback_data="tg_resend_code")],
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="senders_menu")],
        ]
    )
    await message.answer(
        "🔐 Введите код из Telegram (5 цифр). Если код пришёл в приложение — возьмите его там.",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(SenderStates.waiting_for_telegram_code)


@router.callback_query(F.data == "tg_resend_code")
@handle_errors
async def tg_resend_code(callback: types.CallbackQuery, state: FSMContext):
    """Повторная отправка кода авторизации."""
    data = await state.get_data()
    api_id = data.get("api_id")
    api_hash = data.get("api_hash")
    phone = data.get("tg_phone")
    tmp_session = data.get("tg_tmp_session")

    if not (api_id and api_hash and phone):
        return await callback.answer("Нет данных для повтора. Начните заново.", show_alert=True)

    client = TelegramClient(StringSession(tmp_session or ""), api_id, api_hash)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        await state.update_data(
            tg_tmp_session=client.session.save(),
            tg_phone_code_hash=sent.phone_code_hash
        )
    except PhoneNumberInvalidError:
        await client.disconnect()
        return await callback.answer("Номер больше не валиден. Начните заново.", show_alert=True)
    except Exception as e:
        await client.disconnect()
        logger.exception("Resend code failed: %s", e)
        return await callback.answer("Не удалось отправить код. Попробуйте позже.", show_alert=True)

    await client.disconnect()

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🔁 Отправить код ещё раз", callback_data="tg_resend_code")],
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="senders_menu")],
        ]
    )
    try:
        await callback.message.edit_text(
            "🔐 Введите новый код из Telegram (5 цифр).",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise

    await callback.answer("Код отправлен заново.")


@router.message(SenderStates.waiting_for_telegram_code)
@handle_errors
async def process_telegram_code(message: types.Message, state: FSMContext):
    code = (message.text or "").strip().replace(" ", "")
    if not code.isdigit():
        return await message.answer("❌ Код должен содержать только цифры. Введите ещё раз.")

    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    phone = data["tg_phone"]
    phone_code_hash = data["tg_phone_code_hash"]
    tmp_session = data["tg_tmp_session"]

    client = TelegramClient(StringSession(tmp_session or ""), api_id, api_hash)
    await client.connect()
    try:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            await state.update_data(tg_tmp_session=client.session.save())
            await client.disconnect()
            await message.answer("🔒 У вас включён облачный пароль (2FA). Введите пароль:")
            await state.set_state(SenderStates.waiting_for_telegram_2fa)
            return
    except PhoneCodeInvalidError:
        await client.disconnect()
        return await message.answer("❌ Неверный код. Попробуйте снова.")
    except PhoneCodeExpiredError:
        await client.disconnect()
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔁 Отправить код ещё раз", callback_data="tg_resend_code")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="senders_menu")],
            ]
        )
        return await message.answer("⌛ Код истёк. Нажмите «Отправить код ещё раз» и введите новый.", reply_markup=kb)
    except Exception as e:
        await client.disconnect()
        logger.exception("sign_in failed: %s", e)
        return await message.answer("⚠️ Не удалось войти. Попробуйте ещё раз.")

    session_str = client.session.save()
    me = await client.get_me()
    await client.disconnect()

    # Сохраняем отправителя
    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("Пользователь не найден. Нажмите /start")

        sender_name = data["sender_name"]
        sender = Sender(
            user_id=user.id,
            name=sender_name,
            type=SenderType.TELEGRAM,
            config={
                "session": session_str,
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone,
                "user_id": getattr(me, "id", None),
                "username": getattr(me, "username", None),
            },
            is_active=True,
            is_verified=True,
        )
        db.add(sender)
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Telegram-отправитель '{sender_name}' добавлен и подтверждён!</b>\n"
        f"Теперь можно запускать кампании этим отправителем.",
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu"),
    )


@router.message(SenderStates.waiting_for_telegram_2fa)
@handle_errors
async def process_telegram_2fa(message: types.Message, state: FSMContext):
    password = (message.text or "").strip()
    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    tmp_session = data.get("tg_tmp_session", "")
    phone = data.get("tg_phone", "")

    client = TelegramClient(StringSession(tmp_session or ""), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(password=password)
    except Exception as e:
        await client.disconnect()
        logger.exception("2FA sign_in failed: %s", e)
        return await message.answer("❌ Неверный 2FA пароль. Попробуйте ещё раз.")

    session_str = client.session.save()
    me = await client.get_me()
    await client.disconnect()

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("Пользователь не найден. Нажмите /start")

        sender_name = data["sender_name"]
        sender = Sender(
            user_id=user.id,
            name=sender_name,
            type=SenderType.TELEGRAM,
            config={
                "session": session_str,
                "api_id": api_id,
                "api_hash": api_hash,
                "phone": phone,
                "user_id": getattr(me, "id", None),
                "username": getattr(me, "username", None),
            },
            is_active=True,
            is_verified=True,
        )
        db.add(sender)
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Telegram-отправитель '{sender_name}' добавлен и подтверждён!</b>",
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu"),
    )


# ======================= EMAIL =======================

@router.message(SenderStates.waiting_for_email_host)
@handle_errors
async def process_email_host(message: types.Message, state: FSMContext):
    host = (message.text or "").strip()
    if not host:
        return await message.answer("❌ SMTP хост не может быть пустым")

    await state.update_data(smtp_host=host)
    await message.answer("🔢 <b>Введите SMTP порт:</b>\n(обычно 587 для TLS или 465 для SSL)", parse_mode="HTML")
    await state.set_state(SenderStates.waiting_for_email_port)


@router.message(SenderStates.waiting_for_email_port)
@handle_errors
async def process_email_port(message: types.Message, state: FSMContext):
    try:
        port = int((message.text or "").strip())
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        return await message.answer("❌ Порт должен быть числом от 1 до 65535")

    await state.update_data(smtp_port=port)
    await message.answer("📧 <b>Введите email адрес:</b>", parse_mode="HTML")
    await state.set_state(SenderStates.waiting_for_email_login)


@router.message(SenderStates.waiting_for_email_login)
@handle_errors
async def process_email_login(message: types.Message, state: FSMContext):
    email = (message.text or "").strip()
    ok, clean = validate_email_address(email)
    if not ok:
        return await message.answer(f"❌ {clean}")

    await state.update_data(email=clean)
    await message.answer("🔐 <b>Введите пароль:</b>\n(рекомендуется использовать App Password)", parse_mode="HTML")
    await state.set_state(SenderStates.waiting_for_email_password)


@router.message(SenderStates.waiting_for_email_password)
@handle_errors
async def process_email_password(message: types.Message, state: FSMContext):
    password = (message.text or "").strip()
    if not password:
        return await message.answer("❌ Пароль не может быть пустым")

    data = await state.get_data()

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("Пользователь не найден. Нажмите /start")

        sender = Sender(
            user_id=user.id,
            name=data["sender_name"],
            type=SenderType.EMAIL,
            config={
                "smtp_host": data["smtp_host"],
                "smtp_port": data["smtp_port"],
                "email": data["email"],
                "password": password,
                "use_tls": True
            },
            is_active=True,
            is_verified=False,
        )
        db.add(sender)
        await db.commit()

    await state.clear()
    await message.answer(
        "✅ <b>Email отправитель добавлен!</b>\n\n"
        "⚠️ Проверка подключения произойдёт при первой отправке",
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu"),
    )
    logger.info(f"Email sender added for user {message.from_user.id}")


# ======================= WHATSAPP / SMS / VIBER =======================

@router.message(SenderStates.waiting_for_whatsapp_token)
@handle_errors
async def process_whatsapp_token(message: types.Message, state: FSMContext):
    token = (message.text or "").strip()
    if not token:
        return await message.answer("❌ Токен не может быть пустым")

    data = await state.get_data()

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("Пользователь не найден. Нажмите /start")

        sender = Sender(
            user_id=user.id,
            name=data["sender_name"],
            type=SenderType.WHATSAPP,
            config={
                "auth_token": token,
                "account_sid": "auto",
                "from_number": "whatsapp:+14155238886"
            },
            is_active=True,
            is_verified=False,
        )
        db.add(sender)
        await db.commit()

    await state.clear()
    await message.answer(
        "✅ <b>WhatsApp отправитель добавлен!</b>\n\n"
        "⚠️ Проверка подключения произойдёт при первой отправке",
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu"),
    )
    logger.info(f"WhatsApp sender added for user {message.from_user.id}")


@router.message(SenderStates.waiting_for_sms_api_key)
@handle_errors
async def process_sms_api_key(message: types.Message, state: FSMContext):
    api_key = (message.text or "").strip()
    if not api_key:
        return await message.answer("❌ API ключ не может быть пустым")

    data = await state.get_data()

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("Пользователь не найден. Нажмите /start")

        sender = Sender(
            user_id=user.id,
            name=data["sender_name"],
            type=SenderType.SMS,
            config={
                "api_key": api_key,
                "api_url": "https://api.sms.ru/sms/send",
                "sender_name": data["sender_name"]
            },
            is_active=True,
            is_verified=False,
        )
        db.add(sender)
        await db.commit()

    await state.clear()
    await message.answer(
        "✅ <b>SMS отправитель добавлен!</b>\n\n"
        "⚠️ Проверка подключения произойдёт при первой отправке",
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu"),
    )
    logger.info(f"SMS sender added for user {message.from_user.id}")


@router.message(SenderStates.waiting_for_viber_api_key)
@handle_errors
async def process_viber_api_key(message: types.Message, state: FSMContext):
    api_key = (message.text or "").strip()
    if not api_key:
        return await message.answer("❌ API ключ не может быть пустым")

    data = await state.get_data()

    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()
        if not user:
            await state.clear()
            return await message.answer("Пользователь не найден. Нажмите /start")

        sender = Sender(
            user_id=user.id,
            name=data["sender_name"],
            type=SenderType.VIBER,
            config={
                "api_key": api_key,
                "api_url": "https://chatapi.viber.com/pa/send_message",
                "sender_name": data["sender_name"]
            },
            is_active=True,
            is_verified=False,
        )
        db.add(sender)
        await db.commit()

    await state.clear()
    await message.answer(
        "✅ <b>Viber отправитель добавлен!</b>\n\n"
        "⚠️ Проверка подключения произойдёт при первой отправке",
        parse_mode="HTML",
        reply_markup=back_keyboard("senders_menu"),
    )
    logger.info(f"Viber sender added for user {message.from_user.id}")


# ======================= УДАЛЕНИЕ ОТПРАВИТЕЛЕЙ =======================

@router.callback_query(F.data == "senders_delete_menu")
@handle_errors
async def senders_delete_menu(callback: types.CallbackQuery):
    """Список отправителей с кнопками удаления."""
    user_id = callback.from_user.id
    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user:
            return await callback.answer("Пользователь не найден. Используйте /start", show_alert=True)

        q = await db.execute(select(Sender).where(Sender.user_id == user.id).order_by(Sender.created_at.desc()))
        senders = q.scalars().all()

        if not senders:
            try:
                await callback.message.edit_text(
                    "📭 У вас нет отправителей для удаления.",
                    parse_mode="HTML",
                    reply_markup=back_keyboard("senders_menu"),
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    raise
            return

        kb_rows = []
        for s in senders:
            kb_rows.append([
                types.InlineKeyboardButton(text=f"🗑 {s.name} ({s.type.value})", callback_data=f"sender_delete_{s.id}")
            ])
        kb_rows.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="senders_menu")])

        text = "🗑 <b>Удаление отправителей</b>\n\nВыберите, кого удалить:"
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_rows)
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise

    await callback.answer()


@router.callback_query(F.data.startswith("sender_delete_"))
@handle_errors
async def sender_delete_confirm(callback: types.CallbackQuery):
    """Подтверждение удаления конкретного отправителя."""
    try:
        sender_id = int(callback.data.split("_")[-1])
    except Exception:
        return await callback.answer("Некорректная команда", show_alert=True)

    user_id = callback.from_user.id
    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user:
            return await callback.answer("Пользователь не найден", show_alert=True)

        sender = await db.get(Sender, sender_id)
        if not sender or sender.user_id != user.id:
            return await callback.answer("Отправитель не найден", show_alert=True)

        text = (
            f"❗️ Вы действительно хотите удалить отправителя:\n\n"
            f"<b>{sender.name}</b> ({sender.type.value})\n\n"
            f"Действие необратимо."
        )
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=f"sender_delete_yes_{sender.id}")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="senders_delete_menu")],
            ]
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise

    await callback.answer()


@router.callback_query(F.data.startswith("sender_delete_yes_"))
@handle_errors
async def sender_delete_do(callback: types.CallbackQuery):
    """Удаляем отправителя после подтверждения."""
    try:
        sender_id = int(callback.data.split("_")[-1])
    except Exception:
        return await callback.answer("Некорректная команда", show_alert=True)

    user_id = callback.from_user.id
    async for db in get_db():
        user = (await db.execute(select(User).where(User.telegram_id == user_id))).scalar_one_or_none()
        if not user:
            return await callback.answer("Пользователь не найден", show_alert=True)

        sender = await db.get(Sender, sender_id)
        if not sender or sender.user_id != user.id:
            return await callback.answer("Отправитель не найден", show_alert=True)

        await db.delete(sender)
        await db.commit()

    # Покажем подтверждение + кнопку назад
    try:
        await callback.message.edit_text(
            "✅ Отправитель удалён.",
            parse_mode="HTML",
            reply_markup=back_keyboard("senders_delete_menu"),
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise

    await callback.answer("Удалено")
