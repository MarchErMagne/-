from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from app.database.database import get_db
from app.database.models import User, Campaign, CampaignLog, Contact, SenderType, CampaignStatus, SubscriptionStatus
from datetime import datetime, timedelta
from app.utils.keyboards import analytics_keyboard, back_keyboard
from app.utils.decorators import handle_errors, log_user_action, subscription_required
import io
import csv
import json
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == "📈 Аналитика")
@subscription_required()
@handle_errors
@log_user_action("analytics_menu")
async def analytics_menu(message: types.Message, user: User, db: AsyncSession, **kwargs):
    """Главное меню аналитики"""
    
    # Получаем общую статистику
    campaigns_result = await db.execute(
        select(func.count(Campaign.id)).where(Campaign.user_id == user.id)
    )
    total_campaigns = campaigns_result.scalar()
    
    contacts_result = await db.execute(
        select(func.count(Contact.id)).where(
            and_(Contact.user_id == user.id, Contact.is_active == True)
        )
    )
    total_contacts = contacts_result.scalar()
    
    # Статистика за последние 30 дней
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    recent_campaigns_result = await db.execute(
        select(func.count(Campaign.id)).where(
            and_(
                Campaign.user_id == user.id,
                Campaign.created_at >= thirty_days_ago
            )
        )
    )
    recent_campaigns = recent_campaigns_result.scalar()
    
    # Успешные отправки за 30 дней
    sent_result = await db.execute(
        select(func.sum(Campaign.sent_count)).where(
            and_(
                Campaign.user_id == user.id,
                Campaign.started_at >= thirty_days_ago
            )
        )
    )
    total_sent = sent_result.scalar() or 0
    
    # Неудачные отправки за 30 дней
    failed_result = await db.execute(
        select(func.sum(Campaign.failed_count)).where(
            and_(
                Campaign.user_id == user.id,
                Campaign.started_at >= thirty_days_ago
            )
        )
    )
    total_failed = failed_result.scalar() or 0
    
    # Подсчет успешности
    success_rate = 0
    if total_sent + total_failed > 0:
        success_rate = (total_sent / (total_sent + total_failed)) * 100
    
    analytics_text = (
        f"📈 <b>Аналитика и статистика</b>\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"• Всего кампаний: {total_campaigns}\n"
        f"• Всего контактов: {total_contacts:,}\n\n"
        f"📅 <b>За последние 30 дней:</b>\n"
        f"• Кампаний запущено: {recent_campaigns}\n"
        f"• Сообщений отправлено: {total_sent:,}\n"
        f"• Неудачных отправок: {total_failed:,}\n"
        f"• Успешность: {success_rate:.1f}%\n\n"
        f"Выберите раздел для детального анализа:"
    )
    
    await message.answer(
        analytics_text,
        parse_mode="HTML",
        reply_markup=analytics_keyboard()
    )

@router.callback_query(F.data == "analytics_menu")
@handle_errors  
async def analytics_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Callback для меню аналитики"""
    await state.clear()
    
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        if user.subscription_status != SubscriptionStatus.ACTIVE:
            await callback.answer("🔒 Нужна активная подписка!", show_alert=True)
            return
        
        # Получаем общую статистику
        campaigns_result = await db.execute(
            select(func.count(Campaign.id)).where(Campaign.user_id == user.id)
        )
        total_campaigns = campaigns_result.scalar()
        
        contacts_result = await db.execute(
            select(func.count(Contact.id)).where(
                and_(Contact.user_id == user.id, Contact.is_active == True)
            )
        )
        total_contacts = contacts_result.scalar()
        
        # Статистика за последние 30 дней
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        recent_campaigns_result = await db.execute(
            select(func.count(Campaign.id)).where(
                and_(
                    Campaign.user_id == user.id,
                    Campaign.created_at >= thirty_days_ago
                )
            )
        )
        recent_campaigns = recent_campaigns_result.scalar()
        
        # Успешные отправки за 30 дней
        sent_result = await db.execute(
            select(func.sum(Campaign.sent_count)).where(
                and_(
                    Campaign.user_id == user.id,
                    Campaign.started_at >= thirty_days_ago
                )
            )
        )
        total_sent = sent_result.scalar() or 0
        
        # Неудачные отправки за 30 дней
        failed_result = await db.execute(
            select(func.sum(Campaign.failed_count)).where(
                and_(
                    Campaign.user_id == user.id,
                    Campaign.started_at >= thirty_days_ago
                )
            )
        )
        total_failed = failed_result.scalar() or 0
        
        # Подсчет успешности
        success_rate = 0
        if total_sent + total_failed > 0:
            success_rate = (total_sent / (total_sent + total_failed)) * 100
        
        analytics_text = (
            f"📈 <b>Аналитика и статистика</b>\n\n"
            f"📊 <b>Общая статистика:</b>\n"
            f"• Всего кампаний: {total_campaigns}\n"
            f"• Всего контактов: {total_contacts:,}\n\n"
            f"📅 <b>За последние 30 дней:</b>\n"
            f"• Кампаний запущено: {recent_campaigns}\n"
            f"• Сообщений отправлено: {total_sent:,}\n"
            f"• Неудачных отправок: {total_failed:,}\n"
            f"• Успешность: {success_rate:.1f}%\n\n"
            f"Выберите раздел для детального анализа:"
        )
        
        await callback.message.edit_text(
            analytics_text,
            parse_mode="HTML",
            reply_markup=analytics_keyboard()
        )
    
    await callback.answer()

@router.callback_query(F.data == "analytics_general")
@handle_errors
async def analytics_general(callback: types.CallbackQuery):
    """Общая статистика"""
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Статистика по типам кампаний
        type_stats = {}
        for sender_type in SenderType:
            campaigns_result = await db.execute(
                select(func.count(Campaign.id)).where(
                    and_(
                        Campaign.user_id == user.id,
                        Campaign.type == sender_type
                    )
                )
            )
            campaigns_count = campaigns_result.scalar()
            
            sent_result = await db.execute(
                select(func.sum(Campaign.sent_count)).where(
                    and_(
                        Campaign.user_id == user.id,
                        Campaign.type == sender_type
                    )
                )
            )
            sent_count = sent_result.scalar() or 0
            
            if campaigns_count > 0:
                type_stats[sender_type] = {
                    'campaigns': campaigns_count,
                    'sent': sent_count
                }
        
        # Статистика по статусам
        status_stats = {}
        for status in CampaignStatus:
            result = await db.execute(
                select(func.count(Campaign.id)).where(
                    and_(
                        Campaign.user_id == user.id,
                        Campaign.status == status
                    )
                )
            )
            count = result.scalar()
            if count > 0:
                status_stats[status] = count
        
        general_text = "📊 <b>Общая статистика</b>\n\n"
        
        if type_stats:
            general_text += "<b>По типам рассылок:</b>\n"
            type_icons = {
                SenderType.TELEGRAM: "📱",
                SenderType.EMAIL: "📧",
                SenderType.WHATSAPP: "💬",
                SenderType.SMS: "📞",
                SenderType.VIBER: "🟣"
            }
            
            for sender_type, stats in type_stats.items():
                icon = type_icons.get(sender_type, "❓")
                general_text += f"{icon} {sender_type.value.capitalize()}: {stats['campaigns']} кампаний, {stats['sent']:,} отправок\n"
            
            general_text += "\n"
        
        if status_stats:
            general_text += "<b>По статусам кампаний:</b>\n"
            status_icons = {
                CampaignStatus.COMPLETED: "✅",
                CampaignStatus.RUNNING: "🔄",
                CampaignStatus.DRAFT: "📝",
                CampaignStatus.PAUSED: "⏸",
                CampaignStatus.FAILED: "❌"
            }
            
            for status, count in status_stats.items():
                icon = status_icons.get(status, "❓")
                general_text += f"{icon} {status.value.capitalize()}: {count}\n"
        
        await callback.message.edit_text(
            general_text,
            parse_mode="HTML",
            reply_markup=back_keyboard("analytics_menu")
        )
    
    await callback.answer()

@router.callback_query(F.data == "analytics_campaigns")
@handle_errors
async def analytics_campaigns(callback: types.CallbackQuery):
    """Аналитика по кампаниям"""
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Топ 5 самых успешных кампаний
        result = await db.execute(
            select(Campaign).where(Campaign.user_id == user.id)
            .order_by(desc(Campaign.sent_count))
            .limit(5)
        )
        top_campaigns = result.scalars().all()
        
        # Недавние кампании
        result = await db.execute(
            select(Campaign).where(Campaign.user_id == user.id)
            .order_by(desc(Campaign.created_at))
            .limit(5)
        )
        recent_campaigns = result.scalars().all()
        
        campaigns_text = "📊 <b>Аналитика кампаний</b>\n\n"
        
        if top_campaigns:
            campaigns_text += "<b>🏆 Топ-5 по отправкам:</b>\n"
            for i, campaign in enumerate(top_campaigns, 1):
                success_rate = 0
                if campaign.total_contacts and campaign.total_contacts > 0:
                    success_rate = (campaign.sent_count / campaign.total_contacts) * 100
                
                campaigns_text += (
                    f"{i}. {campaign.name}\n"
                    f"   📤 {campaign.sent_count or 0:,} отправок ({success_rate:.1f}%)\n"
                    f"   📅 {campaign.created_at.strftime('%d.%m.%Y')}\n\n"
                )
        
        if recent_campaigns:
            campaigns_text += "<b>🕒 Последние кампании:</b>\n"
            
            status_icons = {
                CampaignStatus.COMPLETED: "✅",
                CampaignStatus.RUNNING: "🔄", 
                CampaignStatus.DRAFT: "📝",
                CampaignStatus.PAUSED: "⏸",
                CampaignStatus.FAILED: "❌"
            }
            
            for campaign in recent_campaigns:
                status_icon = status_icons.get(campaign.status, "❓")
                campaigns_text += (
                    f"{status_icon} {campaign.name}\n"
                    f"   📊 {campaign.sent_count or 0}/{campaign.total_contacts or 0}\n"
                    f"   📅 {campaign.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                )
        
        if not top_campaigns and not recent_campaigns:
            campaigns_text += "📭 У вас пока нет кампаний для анализа"
        
        await callback.message.edit_text(
            campaigns_text,
            parse_mode="HTML",
            reply_markup=back_keyboard("analytics_menu")
        )
    
    await callback.answer()

@router.callback_query(F.data == "analytics_contacts")
@handle_errors
async def analytics_contacts(callback: types.CallbackQuery):
    """Аналитика по контактам"""
    user_id = callback.from_user.id
    
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Статистика по типам контактов
        type_stats = {}
        for sender_type in SenderType:
            result = await db.execute(
                select(func.count(Contact.id)).where(
                    and_(
                        Contact.user_id == user.id,
                        Contact.type == sender_type,
                        Contact.is_active == True
                    )
                )
            )
            count = result.scalar()
            if count > 0:
                type_stats[sender_type] = count
        
        # Недавно добавленные контакты
        recent_result = await db.execute(
            select(func.count(Contact.id)).where(
                and_(
                    Contact.user_id == user.id,
                    Contact.created_at >= datetime.utcnow() - timedelta(days=7),
                    Contact.is_active == True
                )
            )
        )
        recent_contacts = recent_result.scalar()
        
        # Общее количество
        total_result = await db.execute(
            select(func.count(Contact.id)).where(
                and_(Contact.user_id == user.id, Contact.is_active == True)
            )
        )
        total_contacts = total_result.scalar()
        
        contacts_text = (
            f"👥 <b>Аналитика контактов</b>\n\n"
            f"📊 <b>Общая статистика:</b>\n"
            f"• Всего активных: {total_contacts:,}\n"
            f"• Добавлено за неделю: {recent_contacts:,}\n\n"
        )
        
        if type_stats:
            contacts_text += "<b>По типам:</b>\n"
            type_icons = {
                SenderType.TELEGRAM: "📱",
                SenderType.EMAIL: "📧",
                SenderType.WHATSAPP: "💬", 
                SenderType.SMS: "📞",
                SenderType.VIBER: "🟣"
            }
            
            for sender_type, count in type_stats.items():
                icon = type_icons.get(sender_type, "❓")
                percentage = (count / total_contacts) * 100 if total_contacts > 0 else 0
                contacts_text += f"{icon} {sender_type.value.capitalize()}: {count:,} ({percentage:.1f}%)\n"
        else:
            contacts_text += "📭 У вас пока нет контактов"
        
        await callback.message.edit_text(
            contacts_text,
            parse_mode="HTML",
            reply_markup=back_keyboard("analytics_menu")
        )
    
    await callback.answer()

@router.callback_query(F.data == "analytics_export")
@handle_errors  
async def analytics_export(callback: types.CallbackQuery):
    """Экспорт отчета"""
    user_id = callback.from_user.id
    
    # Проверяем план пользователя
    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        if user.subscription_plan not in ["pro", "premium"]:
            await callback.answer("Экспорт доступен только в планах Pro и Premium", show_alert=True)
            return
        
        try:
            # Получаем данные для экспорта
            campaigns_result = await db.execute(
                select(Campaign).where(Campaign.user_id == user.id)
                .order_by(desc(Campaign.created_at))
            )
            campaigns = campaigns_result.scalars().all()
            
            # Создаем CSV отчет
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Заголовки
            writer.writerow([
                'Название кампании',
                'Тип',
                'Статус', 
                'Отправлено',
                'Ошибок',
                'Всего контактов',
                'Успешность (%)',
                'Дата создания',
                'Дата запуска',
                'Дата завершения'
            ])
            
            # Данные кампаний
            for campaign in campaigns:
                success_rate = 0
                if campaign.total_contacts and campaign.total_contacts > 0:
                    success_rate = (campaign.sent_count / campaign.total_contacts) * 100
                
                writer.writerow([
                    campaign.name,
                    campaign.type.value,
                    campaign.status.value,
                    campaign.sent_count or 0,
                    campaign.failed_count or 0,
                    campaign.total_contacts or 0,
                    f"{success_rate:.1f}",
                    campaign.created_at.strftime('%d.%m.%Y %H:%M'),
                    campaign.started_at.strftime('%d.%m.%Y %H:%M') if campaign.started_at else '',
                    campaign.completed_at.strftime('%d.%m.%Y %H:%M') if campaign.completed_at else ''
                ])
            
            # Создаем файл
            csv_data = output.getvalue().encode('utf-8')
            output.close()
            
            file = types.BufferedInputFile(
                csv_data,
                filename=f"analytics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            
            await callback.message.answer_document(
                document=file,
                caption=(
                    f"📋 <b>Отчет по аналитике</b>\n\n"
                    f"📊 Кампаний в отчете: {len(campaigns)}\n"
                    f"📅 Сгенерирован: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                ),
                parse_mode="HTML"
            )
            
            await callback.answer("✅ Отчет экспортирован!")
            
        except Exception as e:
            logger.error(f"Error exporting analytics: {e}")
            await callback.answer("❌ Ошибка экспорта отчета", show_alert=True)