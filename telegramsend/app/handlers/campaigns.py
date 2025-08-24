from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database.database import get_db
from app.database.models import User, Campaign, Sender, Contact, CampaignStatus, SenderType
from app.utils.keyboards import (
    campaign_type_keyboard, campaign_actions_keyboard, 
    back_keyboard, confirm_keyboard
)
from app.utils.decorators import handle_errors, log_user_action, subscription_required
from app.utils.validators import validate_campaign_name, validate_message_content
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)

class CampaignStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_sender = State()
    waiting_for_subject = State()
    waiting_for_message = State()

@router.message(F.text == "📊 Мои кампании")
@subscription_required()
@handle_errors
@log_user_action("campaigns_menu")
async def campaigns_menu(message: types.Message, user: User, db: AsyncSession, **kwargs):
    """Меню кампаний"""
    result = await db.execute(
        select(Campaign).where(Campaign.user_id == user.id)
        .order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    
    campaigns_text = "📊 <b>Мои кампании</b>\n\n"
    
    if campaigns:
        total_campaigns = len(campaigns)
        active_campaigns = len([c for c in campaigns if c.status == CampaignStatus.RUNNING])
        completed_campaigns = len([c for c in campaigns if c.status == CampaignStatus.COMPLETED])
        
        campaigns_text += (
            f"📈 <b>Статистика:</b>\n"
            f"• Всего кампаний: {total_campaigns}\n"
            f"• Активных: {active_campaigns}\n"
            f"• Завершенных: {completed_campaigns}\n\n"
        )
        
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
        
        for campaign in campaigns[:5]:
            status_icon = status_icons.get(campaign.status, "❓")
            type_icon = type_icons.get(campaign.type, "❓")
            
            progress = ""
            if campaign.total_contacts and campaign.total_contacts > 0:
                sent_percent = (campaign.sent_count / campaign.total_contacts) * 100
                progress = f"({campaign.sent_count}/{campaign.total_contacts} - {sent_percent:.1f}%)"
            
            campaigns_text += (
                f"{type_icon} <b>{campaign.name}</b>\n"
                f"   {status_icon} {campaign.status.value.capitalize()} {progress}\n"
                f"   📅 {campaign.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        
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
    
    await message.answer(campaigns_text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data == "campaigns_menu")
@handle_errors
async def campaigns_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Callback для меню кампаний"""
    await state.clear()
    
    user_id = callback.from_user.id
    
    async for db in get_db():
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден. Используйте /start", show_alert=True)
            return
        
        result = await db.execute(
            select(Campaign).where(Campaign.user_id == user.id)
            .order_by(Campaign.created_at.desc())
        )
        campaigns = result.scalars().all()
        
        campaigns_text = "📊 <b>Мои кампании</b>\n\n"
        
        if campaigns:
            total_campaigns = len(campaigns)
            active_campaigns = len([c for c in campaigns if c.status == CampaignStatus.RUNNING])
            completed_campaigns = len([c for c in campaigns if c.status == CampaignStatus.COMPLETED])
            
            campaigns_text += (
                f"📈 <b>Статистика:</b>\n"
                f"• Всего кампаний: {total_campaigns}\n"
                f"• Активных: {active_campaigns}\n"
                f"• Завершенных: {completed_campaigns}\n\n"
            )
            
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
            
            for campaign in campaigns[:5]:
                status_icon = status_icons.get(campaign.status, "❓")
                type_icon = type_icons.get(campaign.type, "❓")
                
                progress = ""
                if campaign.total_contacts and campaign.total_contacts > 0:
                    sent_percent = (campaign.sent_count / campaign.total_contacts) * 100
                    progress = f"({campaign.sent_count}/{campaign.total_contacts} - {sent_percent:.1f}%)"
                
                campaigns_text += (
                    f"{type_icon} <b>{campaign.name}</b>\n"
                    f"   {status_icon} {campaign.status.value.capitalize()} {progress}\n"
                    f"   📅 {campaign.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                )
            
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
        
        await callback.message.edit_text(campaigns_text, parse_mode="HTML", reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data == "new_campaign")
@handle_errors
async def new_campaign_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания новой кампании"""
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
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
@handle_errors
async def select_campaign_type(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа кампании"""
    # Проверяем что это именно тип кампании, а не другая команда
    data_parts = callback.data.split("_")
    if len(data_parts) < 2:
        await callback.answer("Неверная команда", show_alert=True)
        return
    
    campaign_type = data_parts[1]
    
    # Проверяем что это валидный тип кампании
    valid_types = ["telegram", "email", "whatsapp", "sms", "viber"]
    if campaign_type not in valid_types:
        await callback.answer("Неверный тип кампании", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
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
        await state.update_data(sender_id=senders[0].id)
        await ask_for_message(message, state)
    else:
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
    
    await state.update_data(subject=subject)
    
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
    
    await state.update_data(message=result)
    
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
            subject=data.get("subject"),
            message=data["message"],
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

@router.callback_query(F.data.startswith("campaign_start_"))
@handle_errors
async def start_campaign(callback: types.CallbackQuery):
    """Запуск кампании"""
    campaign_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        campaign = await db.get(Campaign, campaign_id)
        if not campaign or campaign.user_id != user.id:
            await callback.answer("Кампания не найдена", show_alert=True)
            return
        
        if campaign.status != CampaignStatus.DRAFT:
            await callback.answer("Кампания уже запущена или завершена", show_alert=True)
            return
        
        # Проверяем наличие контактов
        result = await db.execute(
            select(func.count(Contact.id)).where(
                Contact.user_id == user.id,
                Contact.type == campaign.type,
                Contact.is_active == True
            )
        )
        contacts_count = result.scalar()
        
        if contacts_count == 0:
            await callback.answer("Нет контактов для рассылки", show_alert=True)
            return
        
        # Имитация запуска задачи в Celery (пока без Celery)
        campaign.status = CampaignStatus.RUNNING
        campaign.started_at = datetime.utcnow()
        campaign.total_contacts = contacts_count
        await db.commit()
        
        await callback.message.edit_text(
            f"🚀 <b>Кампания '{campaign.name}' запущена!</b>\n\n"
            f"📊 Контактов для отправки: {contacts_count}\n"
            f"📱 Тип: {campaign.type.value.capitalize()}\n\n"
            f"⚠️ Примечание: Фоновая обработка временно недоступна.\n"
            f"Кампания помечена как запущенная.",
            parse_mode="HTML",
            reply_markup=back_keyboard("campaigns_menu")
        )
        
        await callback.answer("Кампания запущена!")
        logger.info(f"Campaign {campaign_id} started by user {user.telegram_id}")

@router.callback_query(F.data == "all_campaigns")
@handle_errors
async def all_campaigns(callback: types.CallbackQuery):
    """Все кампании пользователя"""
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        result = await db.execute(
            select(Campaign).where(Campaign.user_id == user.id)
            .order_by(Campaign.created_at.desc())
            .limit(10)
        )
        campaigns = result.scalars().all()
        
        if not campaigns:
            await callback.message.edit_text(
                "📭 <b>У вас нет кампаний</b>",
                parse_mode="HTML",
                reply_markup=back_keyboard("campaigns_menu")
            )
            return
        
        campaigns_text = "📋 <b>Все кампании</b>\n\n"
        
        keyboard_buttons = []
        
        for campaign in campaigns:
            status_icons = {
                CampaignStatus.DRAFT: "📝",
                CampaignStatus.RUNNING: "🔄",
                CampaignStatus.COMPLETED: "✅",
                CampaignStatus.FAILED: "❌",
                CampaignStatus.PAUSED: "⏸"
            }
            
            icon = status_icons.get(campaign.status, "❓")
            campaigns_text += f"{icon} {campaign.name} - {campaign.status.value}\n"
            
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"{icon} {campaign.name}",
                    callback_data=f"view_campaign_{campaign.id}"
                )
            ])
        
        keyboard_buttons.append([
            types.InlineKeyboardButton(text="◀️ Назад", callback_data="campaigns_menu")
        ])
        
        await callback.message.edit_text(
            campaigns_text,
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("view_campaign_"))
@handle_errors
async def view_campaign(callback: types.CallbackQuery):
    """Просмотр детальной информации о кампании"""
    campaign_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        campaign = await db.get(Campaign, campaign_id)
        if not campaign or campaign.user_id != user.id:
            await callback.answer("Кампания не найдена", show_alert=True)
            return
        
        # Получаем статистику
        success_rate = 0
        if campaign.total_contacts and campaign.total_contacts > 0:
            success_rate = (campaign.sent_count / campaign.total_contacts) * 100
        
        campaign_text = (
            f"📊 <b>{campaign.name}</b>\n\n"
            f"📱 <b>Тип:</b> {campaign.type.value.capitalize()}\n"
            f"📊 <b>Статус:</b> {campaign.status.value.capitalize()}\n"
            f"📅 <b>Создана:</b> {campaign.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        )
        
        if campaign.started_at:
            campaign_text += f"🚀 <b>Запущена:</b> {campaign.started_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        if campaign.completed_at:
            campaign_text += f"✅ <b>Завершена:</b> {campaign.completed_at.strftime('%d.%m.%Y %H:%M')}\n"
        
        campaign_text += f"\n📈 <b>Статистика:</b>\n"
        
        if campaign.total_contacts:
            campaign_text += (
                f"• Всего контактов: {campaign.total_contacts}\n"
                f"• Отправлено: {campaign.sent_count or 0}\n"
                f"• Ошибок: {campaign.failed_count or 0}\n"
                f"• Успешность: {success_rate:.1f}%\n"
            )
        else:
            campaign_text += "• Статистика пока недоступна\n"
        
        if campaign.subject:
            campaign_text += f"\n✉️ <b>Тема:</b> {campaign.subject}\n"
        
        # Показываем начало сообщения
        message_preview = campaign.message[:100] + "..." if len(campaign.message) > 100 else campaign.message
        campaign_text += f"\n💬 <b>Сообщение:</b>\n<i>{message_preview}</i>"
        
        await callback.message.edit_text(
            campaign_text,
            parse_mode="HTML",
            reply_markup=campaign_actions_keyboard(campaign.id, campaign.status.value)
        )
    
    await callback.answer()