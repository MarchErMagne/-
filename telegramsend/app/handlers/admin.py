from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from app.database.database import get_db
from app.database.models import User, Campaign, Contact, Payment, SubscriptionStatus
from app.utils.decorators import handle_errors, admin_required, log_user_action
from app.config import SUBSCRIPTION_PLANS
from datetime import datetime, timedelta
import logging

router = Router()
logger = logging.getLogger(__name__)

# ID администраторов (замените на реальные)
ADMIN_IDS = [123456789, 987654321]  # Добавьте сюда ID админов

class AdminStates(StatesGroup):
    waiting_for_broadcast_message = State()
    waiting_for_user_id = State()
    waiting_for_subscription_days = State()

@router.message(Command("admin"))
@admin_required
@handle_errors
@log_user_action("admin_panel")
async def admin_panel(message: types.Message):
    """Админ панель"""
    
    # Проверяем права
    if message.from_user.id not in ADMIN_IDS:
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
        f"/cleanup - Очистка старых данных"
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
                types.InlineKeyboardButton(text="🧹 Очистка", callback_data="admin_cleanup"),
                types.InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
            ]
        ]
    )
    
    await message.answer(admin_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("stats"))
@admin_required
@handle_errors
async def admin_stats(message: types.Message):
    """Детальная статистика"""
    
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
    
    await message.answer(stats_text, parse_mode="HTML")

@router.message(Command("broadcast"))
@admin_required
@handle_errors
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    """Начало рассылки администратора"""
    
    await message.answer(
        "📢 <b>Рассылка всем пользователям</b>\n\n"
        "Введите текст сообщения для рассылки:\n"
        "⚠️ Сообщение будет отправлено ВСЕМ пользователям бота!",
        parse_mode="HTML"
    )
    
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
@admin_required
@handle_errors
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    """Отправка рассылки"""
    
    broadcast_text = message.text
    
    async for db in get_db():
        # Получаем всех пользователей
        result = await db.execute(select(User.telegram_id))
        user_ids = [row[0] for row in result.all()]
    
    # Подтверждение
    confirm_text = (
        f"📢 <b>Подтверждение рассылки</b>\n\n"
        f"📝 <b>Текст сообщения:</b>\n{broadcast_text}\n\n"
        f"👥 <b>Получателей:</b> {len(user_ids)}\n\n"
        f"⚠️ Вы уверены что хотите отправить это сообщение всем пользователям?"
    )
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Отправить", callback_data=f"confirm_broadcast"),
                types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
            ]
        ]
    )
    
    await state.update_data(broadcast_text=broadcast_text, user_ids=user_ids)
    await message.answer(confirm_text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data == "confirm_broadcast")
@admin_required
@handle_errors
async def admin_broadcast_confirmed(callback: types.CallbackQuery, state: FSMContext):
    """Подтвержденная рассылка"""
    
    data = await state.get_data()
    broadcast_text = data["broadcast_text"]
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
            await callback.bot.send_message(
                chat_id=user_id,
                text=f"📢 <b>Сообщение от администрации</b>\n\n{broadcast_text}",
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
    
    await callback.message.edit_text(result_text, parse_mode="HTML")
    await state.clear()
    
    logger.info(f"Admin broadcast completed: {sent_count} sent, {failed_count} failed")

@router.callback_query(F.data == "cancel_broadcast")
@admin_required
@handle_errors
async def admin_broadcast_cancelled(callback: types.CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    
    await callback.message.edit_text("❌ Рассылка отменена")
    await state.clear()
    await callback.answer()

@router.message(Command("user"))
@admin_required
@handle_errors
async def admin_user_info(message: types.Message):
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
            ]
        ]
    )
    
    await message.answer(user_info_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("grant"))
@admin_required
@handle_errors
async def admin_grant_subscription(message: types.Message):
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
@admin_required
@handle_errors
async def admin_revoke_subscription(message: types.Message):
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
@admin_required
@handle_errors
async def admin_cleanup(message: types.Message):
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
    
    await message.answer(cleanup_text, parse_mode="HTML")
    logger.info(f"Admin cleanup completed: {deleted_logs} logs, {deleted_payments} payments deleted")

# Импорт asyncio для рассылки
import asyncio