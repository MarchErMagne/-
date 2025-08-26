from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.database import get_db
from app.database.models import User, Campaign, Sender, Contact, CampaignStatus, SenderType, CampaignLog
from app.utils.keyboards import (
    campaign_type_keyboard, campaign_actions_keyboard,
    back_keyboard, confirm_keyboard
)
from app.utils.decorators import handle_errors, log_user_action, subscription_required
from app.utils.validators import validate_campaign_name, validate_message_content
from datetime import datetime
import logging
from app.tasks.campaigns import start_campaign_task
from aiogram.exceptions import TelegramBadRequest

router = Router()
logger = logging.getLogger(__name__)


class CampaignStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_sender = State()
    waiting_for_subject = State()
    waiting_for_message = State()
    waiting_for_edit_batch = State()
    waiting_for_edit_delay = State()


# ------------------ создание кампании ------------------

@router.message(CampaignStates.waiting_for_name)
@handle_errors
async def process_campaign_name(message: types.Message, state: FSMContext):
    """Обработка названия кампании"""
    name = message.text.strip()
    is_valid, result = validate_campaign_name(name)
    if not is_valid:
        await message.answer(f"❌ {result}")
        return

    await state.update_data(campaign_name=result)
    data = await state.get_data()
    campaign_type = data["campaign_type"]
    sender_type = SenderType(campaign_type)

    async for db in get_db():
        res = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден. Нажмите /start")
            return

        res = await db.execute(
            select(Sender).where(
                Sender.user_id == user.id,
                Sender.type == sender_type,
                Sender.is_active == True
            )
        )
        senders = res.scalars().all()

    # один отправитель
    if len(senders) == 1:
        await state.update_data(sender_id=senders[0].id)
        await ask_for_message(message, state)
        return

    # несколько отправителей
    senders_text = "📧 <b>Выберите отправителя:</b>\n\n"
    keyboard_buttons = [
        [types.InlineKeyboardButton(text="🔁 Все отправители", callback_data="select_sender_all")]
    ]
    for s in senders:
        status_icon = "✅" if s.is_verified else "⚠️"
        senders_text += f"{status_icon} {s.name}\n"
        keyboard_buttons.append([
            types.InlineKeyboardButton(text=f"{status_icon} {s.name}", callback_data=f"select_sender_{s.id}")
        ])
    keyboard_buttons.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="new_campaign")])

    await message.answer(
        senders_text,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await state.set_state(CampaignStates.waiting_for_sender)


@router.callback_query(F.data == "select_sender_all")
@handle_errors
async def select_sender_all(callback: types.CallbackQuery, state: FSMContext):
    """Выбор всех отправителей"""
    await state.update_data(sender_id=None, send_from_all=True)
    await ask_for_message(callback.message, state)
    await callback.answer("Будут использованы все активные отправители")


@router.callback_query(F.data.startswith("select_sender_"))
@handle_errors
async def select_sender(callback: types.CallbackQuery, state: FSMContext):
    """Выбор одного отправителя"""
    sender_id = int(callback.data.split("_")[2])
    await state.update_data(sender_id=sender_id, send_from_all=False)
    await ask_for_message(callback.message, state)
    await callback.answer()


async def ask_for_message(message: types.Message, state: FSMContext):
    """Запрос текста сообщения"""
    data = await state.get_data()
    campaign_type = data["campaign_type"]

    if campaign_type == "email":
        await message.answer("✉️ <b>Введите тему письма:</b>", parse_mode="HTML")
        await state.set_state(CampaignStates.waiting_for_subject)
    else:
        await message.answer(
            "💬 <b>Введите текст сообщения:</b>\n\n"
            "💡 Можете использовать переменные:\n"
            "• {first_name}\n• {last_name}\n• {datetime}",
            parse_mode="HTML"
        )
        await state.set_state(CampaignStates.waiting_for_message)


@router.message(CampaignStates.waiting_for_message)
@handle_errors
async def process_campaign_message(message: types.Message, state: FSMContext):
    """Сохраняем сообщение и создаём кампанию"""
    text = message.text.strip()
    is_valid, result = validate_message_content(text)
    if not is_valid:
        await message.answer(f"❌ {result}")
        return

    await state.update_data(message=result)
    data = await state.get_data()

    async for db in get_db():
        res = await db.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if not user:
            await message.answer("Пользователь не найден")
            return

        campaign = Campaign(
            user_id=user.id,
            name=data["campaign_name"],
            type=SenderType(data["campaign_type"]),
            sender_id=data.get("sender_id"),
            subject=data.get("subject"),
            message=data["message"],
            status=CampaignStatus.DRAFT
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)

    await message.answer(
        f"✅ <b>Кампания '{campaign.name}' создана!</b>",
        parse_mode="HTML",
        reply_markup=campaign_actions_keyboard(campaign.id, campaign.status.value)
    )
    await state.clear()


# ------------------ пример подавления ошибки edit_text ------------------

async def safe_edit(callback: types.CallbackQuery, text: str, **kwargs):
    """Безопасный edit_text"""
    try:
        await callback.message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
