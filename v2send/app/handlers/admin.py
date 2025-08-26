from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from app.database.database import get_db
from app.database.models import User, Campaign, Contact, Payment, SubscriptionStatus
from app.utils.keyboards import back_keyboard
from app.utils.decorators import handle_errors, log_user_action
from app.config import SUBSCRIPTION_PLANS
from datetime import datetime, timedelta
import logging
import asyncio

router = Router()
logger = logging.getLogger(__name__)

# Основные админы (замените на реальные ID)
MAIN_ADMIN_IDS = [7594615184]
# Дополнительные админы (управляются через панель)
ADDITIONAL_ADMIN_IDS = []

def get_all_admin_ids():
    """Получение всех ID админов"""
    return MAIN_ADMIN_IDS + ADDITIONAL_ADMIN_IDS

def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь админом"""
    return user_id in get_all_admin_ids()

class AdminStates(StatesGroup):
    waiting_for_broadcast_message = State()
    waiting_for_user_id = State()
    waiting_for_subscription_days = State()
    waiting_for_new_admin_id = State()

@router.message(Command("admin"))
@handle_errors
@log_user_action("admin_panel")
async def admin_panel(message: types.Message):
    """Админ панель"""
    
    # Проверяем права
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    
    async for db in get_db():
        # Общая статистика
        users_result = await db.execute(select(func.count(User.id)))
        total_users = users_result.scalar()
        
        active_users_result = await db.execute(
            select(func.count(User.id)).where(User.subscription_status == SubscriptionStatus.ACTIVE)
        )
        active_users = active_users_result.scalar()
        
        campaigns_result = await db.execute(select(func.count(Campaign.id)))
        total_campaigns = campaigns_result.scalar()
        
        payments_result = await db.execute(
            select(func.count(Payment.id)).where(Payment.status == "paid")
        )
        total_payments = payments_result.scalar()
        
        # Статистика за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        new_users_result = await db.execute(
            select(func.count(User.id)).where(User.created_at >= yesterday)
        )
        new_users = new_users_result.scalar()
        
        new_payments_result = await db.execute(
            select(func.count(Payment.id)).where(
                and_(Payment.paid_at >= yesterday, Payment.status == "paid")
            )
        )
        new_payments = new_payments_result.scalar()
        
        # Доходы за месяц
        month_ago = datetime.utcnow() - timedelta(days=30)
        revenue_result = await db.execute(
            select(func.sum(Payment.amount)).where(
                and_(Payment.paid_at >= month_ago, Payment.status == "paid")
            )
        )
        monthly_revenue = (revenue_result.scalar() or 0) / 100  # Переводим в доллары
    
    admin_text = (
        f"🔧 <b>Админ панель</b>\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💳 Активных подписок: {active_users}\n"
        f"📬 Всего кампаний: {total_campaigns}\n"
        f"💰 Всего платежей: {total_payments}\n\n"
        f"📈 <b>За 24 часа:</b>\n"
        f"👥 Новых пользователей: {new_users}\n"
        f"💳 Новых платежей: {new_payments}\n\n"
        f"💵 <b>Доход за месяц:</b> ${monthly_revenue:.2f}\n\n"
        f"<b>Доступные команды:</b>\n"
        f"/stats - Детальная статистика\n"
        f"/broadcast - Рассылка всем пользователям\n"
        f"/user &lt;id&gt; - Информация о пользователе\n"
        f"/grant &lt;id&gt; &lt;plan&gt; &lt;days&gt; - Выдать подписку\n"
        f"/revoke &lt;id&gt; - Отозвать подписку\n"
        f"/cleanup - Очистка старых данных\n"
        f"/addadmin &lt;id&gt; - Добавить админа"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
                types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")
            ],
            [
                types.InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
                types.InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")
            ],
            [
                types.InlineKeyboardButton(text="🔧 Админы", callback_data="admin_manage"),
                types.InlineKeyboardButton(text="🧹 Очистка", callback_data="admin_cleanup")
            ]
        ]
    )
    
    await message.answer(admin_text, parse_mode="HTML", reply_markup=keyboard)

# Обработчики кнопок админской панели

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: types.CallbackQuery):
    """Детальная статистика через кнопку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
        
    await admin_stats_handler(callback.message)
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: types.CallbackQuery, state: FSMContext):
    """Рассылка через кнопку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
        
    await admin_broadcast_start(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "admin_users")
async def admin_users_callback(callback: types.CallbackQuery):
    """Управление пользователями"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    async for db in get_db():
        # Топ-10 последних пользователей
        result = await db.execute(
            select(User).order_by(User.created_at.desc()).limit(10)
        )
        recent_users = result.scalars().all()
        
        users_text = "👥 <b>Последние пользователи:</b>\n\n"
        
        for user in recent_users:
            status_icon = "✅" if user.subscription_status == SubscriptionStatus.ACTIVE else "❌"
            users_text += (
                f"{status_icon} <b>{user.first_name or 'Без имени'}</b>\n"
                f"   ID: {user.telegram_id}\n"
                f"   Username: @{user.username or 'Нет'}\n"
                f"   Подписка: {user.subscription_plan or 'Нет'}\n"
                f"   Регистрация: {user.created_at.strftime('%d.%m.%Y')}\n\n"
            )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(users_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_payments")
async def admin_payments_callback(callback: types.CallbackQuery):
    """Платежи"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    async for db in get_db():
        # Последние 10 платежей
        result = await db.execute(
            select(Payment).where(Payment.status == "paid")
            .order_by(Payment.paid_at.desc()).limit(10)
        )
        recent_payments = result.scalars().all()
        
        payments_text = "💳 <b>Последние платежи:</b>\n\n"
        
        for payment in recent_payments:
            amount_usd = payment.amount / 100
            payments_text += (
                f"💰 ${amount_usd:.2f}\n"
                f"   План: {payment.plan}\n"
                f"   Пользователь: {payment.user_id}\n"
                f"   Дата: {payment.paid_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(payments_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "admin_manage")
async def admin_manage_callback(callback: types.CallbackQuery):
    """Управление админами"""
    if callback.from_user.id not in MAIN_ADMIN_IDS:
        await callback.answer("🚫 Только основные админы могут управлять админами", show_alert=True)
        return
    
    manage_text = (
        "🔧 <b>Управление администраторами</b>\n\n"
        f"👨‍💼 <b>Основные админы:</b>\n"
    )
    
    for admin_id in MAIN_ADMIN_IDS:
        manage_text += f"• {admin_id}\n"
    
    if ADDITIONAL_ADMIN_IDS:
        manage_text += f"\n👤 <b>Дополнительные админы:</b>\n"
        for admin_id in ADDITIONAL_ADMIN_IDS:
            manage_text += f"• {admin_id}\n"
    else:
        manage_text += "\n👤 <b>Дополнительных админов нет</b>\n"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin")],
            [types.InlineKeyboardButton(text="➖ Удалить админа", callback_data="remove_admin")],
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(manage_text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "add_admin")
async def add_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    """Добавление нового админа"""
    if callback.from_user.id not in MAIN_ADMIN_IDS:
        await callback.answer("🚫 Нет прав", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👤 <b>Добавление нового администратора</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML"
    )
    
    await state.set_state(AdminStates.waiting_for_new_admin_id)
    await callback.answer()

@router.message(AdminStates.waiting_for_new_admin_id)
async def process_new_admin_id(message: types.Message, state: FSMContext):
    """Обработка ID нового админа"""
    try:
        new_admin_id = int(message.text.strip())
        
        if new_admin_id in get_all_admin_ids():
            await message.answer("❌ Этот пользователь уже является админом")
            return
        
        ADDITIONAL_ADMIN_IDS.append(new_admin_id)
        
        await message.answer(
            f"✅ <b>Администратор добавлен!</b>\n\n"
            f"👤 ID: {new_admin_id}\n"
            f"📝 Теперь он может использовать админские функции.",
            parse_mode="HTML"
        )
        
        # Уведомляем нового админа
        try:
            await message.bot.send_message(
                new_admin_id,
                "🎉 <b>Вы получили права администратора!</b>\n\n"
                "Используйте команду /admin для доступа к панели управления.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Couldn't notify new admin {new_admin_id}: {e}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число.")

@router.callback_query(F.data == "remove_admin")
async def remove_admin_callback(callback: types.CallbackQuery):
    """Удаление админа"""
    if callback.from_user.id not in MAIN_ADMIN_IDS:
        await callback.answer("🚫 Нет прав", show_alert=True)
        return
    
    if not ADDITIONAL_ADMIN_IDS:
        await callback.answer("Нет дополнительных админов для удаления", show_alert=True)
        return
    
    remove_text = "➖ <b>Удаление администратора</b>\n\nВыберите кого удалить:\n\n"
    
    keyboard_buttons = []
    for admin_id in ADDITIONAL_ADMIN_IDS:
        remove_text += f"• {admin_id}\n"
        keyboard_buttons.append([
            types.InlineKeyboardButton(
                text=f"❌ {admin_id}",
                callback_data=f"confirm_remove_admin_{admin_id}"
            )
        ])
    
    keyboard_buttons.append([
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_manage")
    ])
    
    await callback.message.edit_text(
        remove_text,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_remove_admin_"))
async def confirm_remove_admin(callback: types.CallbackQuery):
    """Подтверждение удаления админа"""
    if callback.from_user.id not in MAIN_ADMIN_IDS:
        await callback.answer("🚫 Нет прав", show_alert=True)
        return
    
    admin_id = int(callback.data.split("_")[-1])
    
    if admin_id in ADDITIONAL_ADMIN_IDS:
        ADDITIONAL_ADMIN_IDS.remove(admin_id)
        
        await callback.message.edit_text(
            f"✅ <b>Администратор удален</b>\n\n"
            f"👤 ID: {admin_id}\n"
            f"📝 У него больше нет прав администратора.",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_manage")]
                ]
            )
        )
        
        # Уведомляем бывшего админа
        try:
            await callback.bot.send_message(
                admin_id,
                "⚠️ <b>Ваши права администратора отозваны</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Couldn't notify removed admin {admin_id}: {e}")
    
    await callback.answer()

@router.callback_query(F.data == "admin_cleanup")
async def admin_cleanup_callback(callback: types.CallbackQuery):
    """Очистка данных"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
        
    await admin_cleanup_handler(callback.message)
    await callback.answer()

@router.callback_query(F.data == "admin_back")
async def admin_back_callback(callback: types.CallbackQuery):
    """Возврат в главную админскую панель"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
        
    await admin_panel(callback.message)
    await callback.answer()

# Команды

@router.message(Command("stats"))
@handle_errors
async def admin_stats_command(message: types.Message):
    """Команда статистики"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    await admin_stats_handler(message)

async def admin_stats_handler(message: types.Message):
    """Обработчик детальной статистики"""
    async for db in get_db():
        # Статистика по планам подписки
        plan_stats = {}
        for plan_id in SUBSCRIPTION_PLANS.keys():
            result = await db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.subscription_plan == plan_id,
                        User.subscription_status == SubscriptionStatus.ACTIVE
                    )
                )
            )
            count = result.scalar()
            if count > 0:
                plan_stats[plan_id] = count
        
        # Статистика по дням регистрации (последние 7 дней)
        daily_stats = []
        for i in range(7):
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            result = await db.execute(
                select(func.count(User.id)).where(
                    and_(User.created_at >= day_start, User.created_at < day_end)
                )
            )
            count = result.scalar()
            daily_stats.append((day_start.strftime('%d.%m'), count))
        
        # Топ пользователи по кампаниям
        result = await db.execute(
            select(
                User.telegram_id,
                User.first_name,
                func.count(Campaign.id).label('campaigns_count')
            )
            .join(Campaign, User.id == Campaign.user_id)
            .group_by(User.id, User.telegram_id, User.first_name)
            .order_by(func.count(Campaign.id).desc())
            .limit(5)
        )
        top_users = result.all()
    
    stats_text = "📊 <b>Детальная статистика</b>\n\n"
    
    if plan_stats:
        stats_text += "<b>Подписки по планам:</b>\n"
        for plan_id, count in plan_stats.items():
            plan_name = SUBSCRIPTION_PLANS[plan_id]["name"]
            stats_text += f"• {plan_name}: {count}\n"
        stats_text += "\n"
    
    if daily_stats:
        stats_text += "<b>Регистрации по дням:</b>\n"
        for date_str, count in reversed(daily_stats):
            stats_text += f"• {date_str}: {count}\n"
        stats_text += "\n"
    
    if top_users:
        stats_text += "<b>Топ пользователи по активности:</b>\n"
        for user_id, name, campaigns_count in top_users:
            stats_text += f"• {name} ({user_id}): {campaigns_count} кампаний\n"
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(stats_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(stats_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("broadcast"))
@handle_errors
async def admin_broadcast_command(message: types.Message, state: FSMContext):
    """Команда рассылки"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    await admin_broadcast_start(message, state)

async def admin_broadcast_start(message: types.Message, state: FSMContext):
    """Начало рассылки администратора"""
    
    broadcast_text = (
        "📢 <b>Рассылка всем пользователям</b>\n\n"
        "Отправьте сообщение для рассылки:\n\n"
        "📝 <b>Вы можете отправить:</b>\n"
        "• Текст\n"
        "• Текст с фото\n"
        "• Текст с видео\n"
        "• Текст с документом\n\n"
        "⚠️ Сообщение будет отправлено ВСЕМ пользователям бота!"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")]
        ]
    )
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(broadcast_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(broadcast_text, parse_mode="HTML", reply_markup=keyboard)
    
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
@handle_errors
async def admin_broadcast_process(message: types.Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        await state.clear()
        return
    
    # Получаем всех пользователей
    async for db in get_db():
        result = await db.execute(select(User.telegram_id))
        user_ids = [row[0] for row in result.all()]
    
    # Определяем тип сообщения
    message_type = "text"
    media_file_id = None
    caption = message.text or message.caption or ""
    
    if message.photo:
        message_type = "photo"
        media_file_id = message.photo[-1].file_id
    elif message.video:
        message_type = "video"
        media_file_id = message.video.file_id
    elif message.document:
        message_type = "document"
        media_file_id = message.document.file_id
    elif message.animation:
        message_type = "animation"
        media_file_id = message.animation.file_id
    
    # Подтверждение
    confirm_text = (
        f"📢 <b>Подтверждение рассылки</b>\n\n"
        f"📝 <b>Тип:</b> {message_type}\n"
        f"📄 <b>Текст:</b> {caption[:100]}{'...' if len(caption) > 100 else ''}\n\n"
        f"👥 <b>Получателей:</b> {len(user_ids)}\n\n"
        f"⚠️ Вы уверены что хотите отправить это сообщение всем пользователям?"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Отправить", callback_data="confirm_broadcast"),
                types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
            ]
        ]
    )
    
    await state.update_data(
        message_type=message_type,
        media_file_id=media_file_id,
        caption=caption,
        user_ids=user_ids
    )
    
    await message.answer(confirm_text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data == "confirm_broadcast")
@handle_errors
async def admin_broadcast_confirmed(callback: types.CallbackQuery, state: FSMContext):
    """Подтвержденная рассылка"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    data = await state.get_data()
    message_type = data["message_type"]
    media_file_id = data.get("media_file_id")
    caption = data["caption"]
    user_ids = data["user_ids"]
    
    await callback.message.edit_text(
        f"📤 <b>Рассылка запущена!</b>\n\n"
        f"Отправляем сообщение {len(user_ids)} пользователям...",
        parse_mode="HTML"
    )
    
    # Отправляем сообщения
    sent_count = 0
    failed_count = 0
    
    for user_id in user_ids:
        try:
            if message_type == "text":
                await callback.bot.send_message(
                    chat_id=user_id,
                    text=caption,
                    parse_mode="HTML"
                )
            elif message_type == "photo":
                await callback.bot.send_photo(
                    chat_id=user_id,
                    photo=media_file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message_type == "video":
                await callback.bot.send_video(
                    chat_id=user_id,
                    video=media_file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message_type == "document":
                await callback.bot.send_document(
                    chat_id=user_id,
                    document=media_file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif message_type == "animation":
                await callback.bot.send_animation(
                    chat_id=user_id,
                    animation=media_file_id,
                    caption=caption,
                    parse_mode="HTML"
                )
            
            sent_count += 1
            
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
        
        # Небольшая задержка между отправками
        await asyncio.sleep(0.05)
    
    result_text = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent_count}\n"
        f"❌ Ошибок: {failed_count}\n"
        f"📊 Всего: {len(user_ids)}"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
    await state.clear()
    
    logger.info(f"Admin broadcast completed: {sent_count} sent, {failed_count} failed")
    await callback.answer()

@router.callback_query(F.data == "cancel_broadcast")
@handle_errors
async def admin_broadcast_cancelled(callback: types.CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text("❌ Рассылка отменена", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@router.message(Command("user"))
@handle_errors
async def admin_user_info_command(message: types.Message):
    """Информация о пользователе через команду"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    await admin_user_info_handler(message)

async def admin_user_info_handler(message: types.Message):
    """Информация о пользователе"""
    # Парсим команду
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /user <telegram_id>")
        return
    
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат ID пользователя")
        return
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        
        # Статистика пользователя
        campaigns_result = await db.execute(
            select(func.count(Campaign.id)).where(Campaign.user_id == user.id)
        )
        campaigns_count = campaigns_result.scalar()
        
        contacts_result = await db.execute(
            select(func.count(Contact.id)).where(Contact.user_id == user.id)
        )
        contacts_count = contacts_result.scalar()
        
        payments_result = await db.execute(
            select(func.count(Payment.id), func.sum(Payment.amount)).where(
                and_(Payment.user_id == user.id, Payment.status == "paid")
            )
        )
        payments_data = payments_result.first()
        payments_count = payments_data[0] or 0
        total_paid = (payments_data[1] or 0) / 100
    
    user_info_text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 <b>ID:</b> {user.telegram_id}\n"
        f"👨‍💼 <b>Имя:</b> {user.first_name or 'Не указано'}\n"
        f"📝 <b>Username:</b> @{user.username or 'Не указан'}\n"
        f"🌐 <b>Язык:</b> {user.language_code or 'Не указан'}\n"
        f"📅 <b>Регистрация:</b> {user.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"💳 <b>Подписка:</b>\n"
        f"• План: {user.subscription_plan or 'Нет'}\n"
        f"• Статус: {user.subscription_status.value if user.subscription_status else 'Неактивна'}\n"
        f"• Истекает: {user.subscription_expires.strftime('%d.%m.%Y %H:%M') if user.subscription_expires else 'Нет'}\n\n"
        f"📊 <b>Активность:</b>\n"
        f"• Кампаний: {campaigns_count}\n"
        f"• Контактов: {contacts_count}\n"
        f"• Платежей: {payments_count}\n"
        f"• Потрачено: ${total_paid:.2f}"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="💳 Выдать подписку", 
                    callback_data=f"grant_sub_{user.telegram_id}"
                ),
                types.InlineKeyboardButton(
                    text="❌ Отозвать подписку", 
                    callback_data=f"revoke_sub_{user.telegram_id}"
                )
            ],
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await message.answer(user_info_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("grant"))
@handle_errors
async def admin_grant_subscription_command(message: types.Message):
    """Выдача подписки пользователю через команду"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    await admin_grant_subscription_handler(message)

async def admin_grant_subscription_handler(message: types.Message):
    """Выдача подписки пользователю"""
    # Парсим команду: /grant <user_id> <plan> <days>
    args = message.text.split()
    if len(args) < 4:
        await message.answer(
            "❌ Использование: /grant <user_id> <plan> <days>\n"
            f"Доступные планы: {', '.join(SUBSCRIPTION_PLANS.keys())}"
        )
        return
    
    try:
        user_id = int(args[1])
        plan = args[2]
        days = int(args[3])
    except ValueError:
        await message.answer("❌ Неверный формат параметров")
        return
    
    if plan not in SUBSCRIPTION_PLANS:
        await message.answer(f"❌ Неверный план. Доступные: {', '.join(SUBSCRIPTION_PLANS.keys())}")
        return
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        
        # Выдаем подписку
        user.subscription_plan = plan
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_expires = datetime.utcnow() + timedelta(days=days)
        
        await db.commit()
    
    plan_name = SUBSCRIPTION_PLANS[plan]["name"]
    success_text = (
        f"✅ <b>Подписка выдана!</b>\n\n"
        f"👤 Пользователь: {user_id}\n"
        f"💼 План: {plan_name}\n"
        f"📅 На дней: {days}\n"
        f"⏰ До: {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}"
    )
    
    await message.answer(success_text, parse_mode="HTML")
    
    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Вам выдана подписка!</b>\n\n"
                f"💼 План: {plan_name}\n"
                f"📅 Срок: {days} дней\n"
                f"⏰ Действует до: {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Теперь вы можете пользоваться всеми функциями бота!"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about granted subscription: {e}")

@router.message(Command("revoke"))
@handle_errors
async def admin_revoke_subscription_command(message: types.Message):
    """Отзыв подписки у пользователя через команду"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    await admin_revoke_subscription_handler(message)

async def admin_revoke_subscription_handler(message: types.Message):
    """Отзыв подписки у пользователя"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /revoke <user_id>")
        return
    
    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат ID пользователя")
        return
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        
        # Отзываем подписку
        old_plan = user.subscription_plan
        user.subscription_plan = None
        user.subscription_status = SubscriptionStatus.CANCELLED
        user.subscription_expires = datetime.utcnow()
        
        await db.commit()
    
    success_text = (
        f"✅ <b>Подписка отозвана!</b>\n\n"
        f"👤 Пользователь: {user_id}\n"
        f"💼 Был план: {old_plan or 'Нет'}\n"
        f"📅 Отозвано: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}"
    )
    
    await message.answer(success_text, parse_mode="HTML")
    
    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ <b>Ваша подписка была отозвана</b>\n\n"
                f"📅 Дата отзыва: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Для продолжения работы необходимо оформить новую подписку."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about revoked subscription: {e}")

@router.message(Command("cleanup"))
@handle_errors
async def admin_cleanup_command(message: types.Message):
    """Очистка старых данных через команду"""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет прав администратора")
        return
    await admin_cleanup_handler(message)

async def admin_cleanup_handler(message: types.Message):
    """Очистка старых данных"""
    async for db in get_db():
        # Удаляем старые логи кампаний (старше 90 дней)
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        result = await db.execute(
            text("DELETE FROM campaign_logs WHERE sent_at < :cutoff_date"),
            {"cutoff_date": cutoff_date}
        )
        deleted_logs = result.rowcount
        
        # Удаляем неактивированные платежи (старше 24 часов)
        payment_cutoff = datetime.utcnow() - timedelta(hours=24)
        
        result = await db.execute(
            text("DELETE FROM payments WHERE status = 'pending' AND created_at < :cutoff_date"),
            {"cutoff_date": payment_cutoff}
        )
        deleted_payments = result.rowcount
        
        await db.commit()
    
    cleanup_text = (
        f"🧹 <b>Очистка завершена!</b>\n\n"
        f"📝 Удалено логов: {deleted_logs}\n"
        f"💳 Удалено старых платежей: {deleted_payments}\n"
        f"📅 Очищены данные старше 90 дней"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    if hasattr(message, 'edit_text'):
        await message.edit_text(cleanup_text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(cleanup_text, parse_mode="HTML", reply_markup=keyboard)
    
    logger.info(f"Admin cleanup completed: {deleted_logs} logs, {deleted_payments} payments deleted")

@router.message(Command("addadmin"))
@handle_errors
async def admin_add_admin_command(message: types.Message):
    """Добавление админа через команду"""
    if message.from_user.id not in MAIN_ADMIN_IDS:
        await message.answer("🚫 Только основные админы могут добавлять других админов")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /addadmin <telegram_id>")
        return
    
    try:
        new_admin_id = int(args[1])
        
        if new_admin_id in get_all_admin_ids():
            await message.answer("❌ Этот пользователь уже является админом")
            return
        
        ADDITIONAL_ADMIN_IDS.append(new_admin_id)
        
        await message.answer(
            f"✅ <b>Администратор добавлен!</b>\n\n"
            f"👤 ID: {new_admin_id}\n"
            f"📝 Теперь он может использовать админские функции.",
            parse_mode="HTML"
        )
        
        # Уведомляем нового админа
        try:
            await message.bot.send_message(
                new_admin_id,
                "🎉 <b>Вы получили права администратора!</b>\n\n"
                "Используйте команду /admin для доступа к панели управления.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Couldn't notify new admin {new_admin_id}: {e}")
        
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число.")

# Callback обработчики для кнопок управления подпиской

@router.callback_query(F.data.startswith("grant_sub_"))
async def grant_subscription_callback(callback: types.CallbackQuery):
    """Выдача подписки через кнопку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    # Показываем варианты планов
    plans_keyboard = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        price_usd = plan["price"] / 100
        plans_keyboard.append([
            types.InlineKeyboardButton(
                text=f"{plan['name']} - ${price_usd:.2f} (30 дн)",
                callback_data=f"grant_plan_{user_id}_{plan_id}_30"
            )
        ])
    
    plans_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")
    ])
    
    await callback.message.edit_text(
        f"💳 <b>Выдача подписки пользователю {user_id}</b>\n\n"
        "Выберите план:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=plans_keyboard)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("grant_plan_"))
async def grant_plan_callback(callback: types.CallbackQuery):
    """Подтверждение выдачи конкретного плана"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    plan = parts[3]
    days = int(parts[4])
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Выдаем подписку
        user.subscription_plan = plan
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_expires = datetime.utcnow() + timedelta(days=days)
        
        await db.commit()
    
    plan_name = SUBSCRIPTION_PLANS[plan]["name"]
    success_text = (
        f"✅ <b>Подписка выдана!</b>\n\n"
        f"👤 Пользователь: {user_id}\n"
        f"💼 План: {plan_name}\n"
        f"📅 На дней: {days}\n"
        f"⏰ До: {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(success_text, parse_mode="HTML", reply_markup=keyboard)
    
    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Вам выдана подписка!</b>\n\n"
                f"💼 План: {plan_name}\n"
                f"📅 Срок: {days} дней\n"
                f"⏰ Действует до: {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Теперь вы можете пользоваться всеми функциями бота!"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about granted subscription: {e}")
    
    await callback.answer()

@router.callback_query(F.data.startswith("revoke_sub_"))
async def revoke_subscription_callback(callback: types.CallbackQuery):
    """Отзыв подписки через кнопку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    # Подтверждение
    confirm_keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Да, отозвать", callback_data=f"confirm_revoke_{user_id}"),
                types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение отзыва подписки</b>\n\n"
        f"👤 Пользователь: {user_id}\n\n"
        f"Вы уверены что хотите отозвать подписку у этого пользователя?",
        parse_mode="HTML",
        reply_markup=confirm_keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_revoke_"))
async def confirm_revoke_callback(callback: types.CallbackQuery):
    """Подтверждение отзыва подписки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("🚫 У вас нет прав администратора", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Отзываем подписку
        old_plan = user.subscription_plan
        user.subscription_plan = None
        user.subscription_status = SubscriptionStatus.CANCELLED
        user.subscription_expires = datetime.utcnow()
        
        await db.commit()
    
    success_text = (
        f"✅ <b>Подписка отозвана!</b>\n\n"
        f"👤 Пользователь: {user_id}\n"
        f"💼 Был план: {old_plan or 'Нет'}\n"
        f"📅 Отозвано: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(success_text, parse_mode="HTML", reply_markup=keyboard)
    
    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ <b>Ваша подписка была отозвана</b>\n\n"
                f"📅 Дата отзыва: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"Для продолжения работы необходимо оформить новую подписку."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about revoked subscription: {e}")
    
    await callback.answer()