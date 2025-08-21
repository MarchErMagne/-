from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.database import get_db
from app.database.models import User, Campaign, Sender, Contact, CampaignStatus, SenderType
from app.utils.keyboards import (
    campaign_type_keyboard, campaign_actions_keyboard, 
    back_keyboard, confirm_keyboard, pagination_keyboard
)
from app.utils.decorators import handle_errors, log_user_action, subscription_required
from app.utils.validators import validate_campaign_name, validate_message_content, validate_delay_settings
from app.tasks.campaigns import start_campaign_task
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)

class CampaignStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_sender = State()
    waiting_for_contacts = State()
    waiting_for_subject = State()
    waiting_for_message = State()
    waiting_for_delay = State()
    waiting_for_batch_size = State()

@router.message(F.text == "📊 Мои кампании")
@subscription_required()
@handle_errors
@log_user_action("campaigns_menu")
async def campaigns_menu(message: types.Message, user: User, db: AsyncSession):
    """Меню кампаний"""
    # Получаем кампании пользователя
    result = await db.execute(
        select(Campaign).where(Campaign.user_id == user.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    
    campaigns_text = "📊 <b>Мои кампании</b>\n\n"
    
    if campaigns:
        # Статистика
        total_campaigns = len(campaigns)
        active_campaigns = len([c for c in campaigns if c.status == CampaignStatus.RUNNING])
        completed_campaigns = len([c for c in campaigns if c.status == CampaignStatus.COMPLETED])
        
        campaigns_text += (
            f"📈 <b>Статистика:</b>\n"
            f"• Всего кампаний: {total_campaigns}\n"
            f"• Активных: {active_campaigns}\n"
            f"• Завершенных: {completed_campaigns}\n\n"
        )
        
        # Последние кампании
        campaigns_text += "<b>Последние кампании:</b>\n\n"
        
        status_icons = {
            CampaignStatus.DRAFT: "📝",
            CampaignStatus.SCHEDULED: "⏰",
            CampaignStatus.RUNNING: "🔄",
            CampaignStatus.PAUSED: "⏸",
            CampaignStatus.COMPLETED: "✅",
            CampaignStatus.FAILED: "❌"
        }
        
        type_icons = {
            SenderType.TELEGRAM: "📱",
            SenderType.EMAIL: "📧",
            SenderType.WHATSAPP: "💬",
            SenderType.SMS: "📞",
            SenderType.VIBER: "🟣"
        }
        
        for campaign in campaigns[:5]:  # Показываем последние 5
            status_icon = status_icons.get(campaign.status, "❓")
            type_icon = type_icons.get(campaign.type, "❓")
            
            progress = ""
            if campaign.total_contacts > 0:
                sent_percent = (campaign.sent_count / campaign.total_contacts) * 100
                progress = f"({campaign.sent_count}/{campaign.total_contacts} - {sent_percent:.1f}%)"
            
            campaigns_text += (
                f"{type_icon} <b>{campaign.name}</b>\n"
                f"   {status_icon} {campaign.status.value.capitalize()} {progress}\n"
                f"   📅 {campaign.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        
        # Кнопки управления
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Новая кампания", callback_data="new_campaign")],
                [types.InlineKeyboardButton(text="📋 Все кампании", callback_data="all_campaigns")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
            ]
        )
        
    else:
        campaigns_text += (
            "📭 <b>У вас пока нет кампаний</b>\n\n"
            "Создайте первую кампанию для начала работы с рассылками!"
        )
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="➕ Создать кампанию", callback_data="new_campaign")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
            ]
        )
    
    await message.answer(
        campaigns_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "new_campaign")
@subscription_required()
@handle_errors
async def new_campaign_start(callback: types.CallbackQuery, state: FSMContext, user: User, db: AsyncSession):
    """Начало создания новой кампании"""
    # Проверяем наличие отправителей
    result = await db.execute(
        select(func.count(Sender.id)).where(
            Sender.user_id == user.id,
            Sender.is_active == True
        )
    )
    senders_count = result.scalar()
    
    if senders_count == 0:
        await callback.message.edit_text(
            "⚠️ <b>Нет доступных отправителей</b>\n\n"
            "Для создания кампании сначала добавьте хотя бы одного отправителя.",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="📧 Добавить отправителя", callback_data="senders_menu")],
                    [types.InlineKeyboardButton(text="◀️ Назад", callback_data="campaigns_menu")]
                ]
            )
        )
        return
    
    await callback.message.edit_text(
        "🚀 <b>Создание новой кампании</b>\n\n"
        "Выберите тип рассылки:",
        parse_mode="HTML",
        reply_markup=campaign_type_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("campaign_"))
@subscription_required()
@handle_errors
async def select_campaign_type(callback: types.CallbackQuery, state: FSMContext, user: User, db: AsyncSession):
    """Выбор типа кампании"""
    campaign_type = callback.data.split("_")[1]
    
    # Проверяем наличие отправителей нужного типа
    sender_type = SenderType(campaign_type)
    result = await db.execute(
        select(func.count(Sender.id)).where(
            Sender.user_id == user.id,
            Sender.type == sender_type,
            Sender.is_active == True
        )
    )
    senders_count = result.scalar()
    
    if senders_count == 0:
        type_names = {
            "telegram": "Telegram",
            "email": "Email", 
            "whatsapp": "WhatsApp",
            "sms": "SMS",
            "viber": "Viber"
        }
        
        await callback.answer(
            f"Нет отправителей типа {type_names[campaign_type]}",
            show_alert=True
        )
        return
    
    await state.update_data(campaign_type=campaign_type)
    
    await callback.message.edit_text(
        f"📝 <b>Создание {campaign_type.capitalize()} кампании</b>\n\n"
        f"Введите название кампании:",
        parse_mode="HTML",
        reply_markup=back_keyboard("new_campaign")
    )
    
    await state.set_state(CampaignStates.waiting_for_name)
    await callback.answer()

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
    
    # Получаем отправителей нужного типа
    data = await state.get_data()
    campaign_type = data["campaign_type"]
    sender_type = SenderType(campaign_type)
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        result = await db.execute(
            select(Sender).where(
                Sender.user_id == user.id,
                Sender.type == sender_type,
                Sender.is_active == True
            )
        )
        senders = result.scalars().all()
    
    if len(senders) == 1:
        # Если отправитель только один, автоматически выбираем его
        await state.update_data(sender_id=senders[0].id)
        await ask_for_message(message, state)
    else:
        # Показываем список отправителей для выбора
        senders_text = "📧 <b>Выберите отправителя:</b>\n\n"
        
        keyboard_buttons = []
        for sender in senders:
            status_icon = "✅" if sender.is_verified else "⚠️"
            senders_text += f"{status_icon} {sender.name}\n"
            
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"{status_icon} {sender.name}",
                    callback_data=f"select_sender_{sender.id}"
                )
            ])
        
        keyboard_buttons.append([
            types.InlineKeyboardButton(text="◀️ Назад", callback_data="new_campaign")
        ])
        
        await message.answer(
            senders_text,
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
        
        await state.set_state(CampaignStates.waiting_for_sender)

@router.callback_query(F.data.startswith("select_sender_"))
@handle_errors
async def select_sender(callback: types.CallbackQuery, state: FSMContext):
    """Выбор отправителя"""
    sender_id = int(callback.data.split("_")[2])
    await state.update_data(sender_id=sender_id)
    
    await ask_for_message(callback.message, state)
    await callback.answer()

async def ask_for_message(message: types.Message, state: FSMContext):
    """Запрос текста сообщения"""
    data = await state.get_data()
    campaign_type = data["campaign_type"]
    
    if campaign_type == "email":
        await message.answer(
            "✉️ <b>Введите тему письма:</b>",
            parse_mode="HTML"
        )
        await state.set_state(CampaignStates.waiting_for_subject)
    else:
        await message.answer(
            "💬 <b>Введите текст сообщения:</b>\n\n"
            "💡 Можете использовать переменные:\n"
            "• {first_name} - имя получателя\n"
            "• {last_name} - фамилия получателя\n"
            "• {datetime} - текущие дата и время",
            parse_mode="HTML"
        )
        await state.set_state(CampaignStates.waiting_for_message)

@router.message(CampaignStates.waiting_for_subject)
@handle_errors
async def process_email_subject(message: types.Message, state: FSMContext):
    """Обработка темы email"""
    subject = message.text.strip()
    
    if not subject:
        await message.answer("❌ Тема письма не может быть пустой")
        return
    
    if len(subject) > 200:
        await message.answer("❌ Тема письма не должна превышать 200 символов")
        return
    
    await state.update_data(campaign_subject=subject)
    
    await message.answer(
        "💬 <b>Введите текст письма:</b>\n\n"
        "💡 Можете использовать HTML разметку и переменные:\n"
        "• {first_name} - имя получателя\n"
        "• {last_name} - фамилия получателя\n"
        "• {datetime} - текущие дата и время",
        parse_mode="HTML"
    )
    await state.set_state(CampaignStates.waiting_for_message)

@router.message(CampaignStates.waiting_for_message)
@handle_errors
async def process_campaign_message(message: types.Message, state: FSMContext):
    """Обработка текста сообщения"""
    text = message.text.strip()
    
    is_valid, result = validate_message_content(text)
    if not is_valid:
        await message.answer(f"❌ {result}")
        return
    
    await state.update_data(campaign_message=result)
    
    # Создаем кампанию в БД
    data = await state.get_data()
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        campaign = Campaign(
            user_id=user.id,
            name=data["campaign_name"],
            type=SenderType(data["campaign_type"]),
            sender_id=data["sender_id"],
            subject=data.get("campaign_subject"),
            message=data["campaign_message"],
            status=CampaignStatus.DRAFT
        )
        
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        
        success_text = (
            f"✅ <b>Кампания '{campaign.name}' создана!</b>\n\n"
            f"📝 <b>Тип:</b> {campaign.type.value.capitalize()}\n"
            f"📊 <b>Статус:</b> Черновик\n\n"
            f"Теперь вы можете настроить дополнительные параметры или сразу запустить кампанию."
        )
        
        await message.answer(
            success_text,
            parse_mode="HTML",
            reply_markup=campaign_actions_keyboard(campaign.id, campaign.status.value)
        )
        
        await state.clear()
        logger.info(f"Campaign created: {campaign.id} by user {user.telegram_id}")

@router.callback_query(F.data == "campaigns_menu")
@handle_errors
async def back_to_campaigns_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в меню кампаний"""
    await state.clear()
    await campaigns_menu(callback.message)