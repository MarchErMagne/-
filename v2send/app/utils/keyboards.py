from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import SUBSCRIPTION_PLANS

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Мои кампании"), KeyboardButton(text="📧 Отправители")],
            [KeyboardButton(text="👥 Контакты"), KeyboardButton(text="📈 Аналитика")],
            [KeyboardButton(text="💳 Подписка"), KeyboardButton(text="🤖 AI-Ассистент")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

def subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора подписки"""
    builder = InlineKeyboardBuilder()
    
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        price_usd = plan["price"] / 100
        builder.add(InlineKeyboardButton(
            text=f"{plan['name']} - ${price_usd:.2f}/мес",
            callback_data=f"subscribe_{plan_id}"
        ))
    
    builder.adjust(1)
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu"))
    return builder.as_markup()

def sender_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа отправителя"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Telegram", callback_data="sender_telegram")],
            [InlineKeyboardButton(text="📧 Email", callback_data="sender_email")],
            [InlineKeyboardButton(text="💬 WhatsApp", callback_data="sender_whatsapp")],
            [InlineKeyboardButton(text="📞 SMS", callback_data="sender_sms")],
            [InlineKeyboardButton(text="🟣 Viber", callback_data="sender_viber")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="senders_menu")]
        ]
    )

def campaign_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа кампании"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Telegram рассылка", callback_data="campaign_telegram")],
            [InlineKeyboardButton(text="📧 Email рассылка", callback_data="campaign_email")],
            [InlineKeyboardButton(text="💬 WhatsApp рассылка", callback_data="campaign_whatsapp")],
            [InlineKeyboardButton(text="📞 SMS рассылка", callback_data="campaign_sms")],
            [InlineKeyboardButton(text="🟣 Viber рассылка", callback_data="campaign_viber")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="campaigns_menu")]
        ]
    )

def campaign_actions_keyboard(campaign_id: int, status: str) -> InlineKeyboardMarkup:
    """Клавиатура управления кампанией"""
    builder = InlineKeyboardBuilder()
    
    if status == "draft":
        builder.add(InlineKeyboardButton(text="▶️ Запустить", callback_data=f"campaign_start_{campaign_id}"))
        builder.add(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"campaign_edit_{campaign_id}"))
    elif status == "running":
        builder.add(InlineKeyboardButton(text="⏸ Приостановить", callback_data=f"campaign_pause_{campaign_id}"))
        builder.add(InlineKeyboardButton(text="⏹ Остановить", callback_data=f"campaign_stop_{campaign_id}"))
    elif status == "paused":
        builder.add(InlineKeyboardButton(text="▶️ Продолжить", callback_data=f"campaign_resume_{campaign_id}"))
        builder.add(InlineKeyboardButton(text="⏹ Остановить", callback_data=f"campaign_stop_{campaign_id}"))
    
    builder.add(InlineKeyboardButton(text="📊 Статистика", callback_data=f"campaign_stats_{campaign_id}"))
    builder.add(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"campaign_delete_{campaign_id}"))
    builder.add(InlineKeyboardButton(text="◀️ Назад", callback_data="campaigns_menu"))
    
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()

def contacts_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления контактами"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📁 Загрузить файл", callback_data="contacts_upload"),
                InlineKeyboardButton(text="👤 Добавить вручную", callback_data="contacts_add_manual")
            ],
            [
                InlineKeyboardButton(text="📋 Мои списки", callback_data="contacts_lists"),
                InlineKeyboardButton(text="🔍 Поиск", callback_data="contacts_search")
            ],
            [
                InlineKeyboardButton(text="🏷 Теги", callback_data="contacts_tags"),
                InlineKeyboardButton(text="🗑 Очистка", callback_data="contacts_cleanup")
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )

def file_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа файла для загрузки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Telegram (username/ID)", callback_data="file_telegram")],
            [InlineKeyboardButton(text="📧 Email адреса", callback_data="file_email")],
            [InlineKeyboardButton(text="📞 Номера телефонов", callback_data="file_phone")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="contacts_upload")]
        ]
    )

def analytics_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура аналитики"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Общая статистика", callback_data="analytics_general")],
            [InlineKeyboardButton(text="📈 По кампаниям", callback_data="analytics_campaigns")],
            [InlineKeyboardButton(text="👥 По контактам", callback_data="analytics_contacts")],
            [InlineKeyboardButton(text="💰 Конверсии", callback_data="analytics_conversions")],
            [InlineKeyboardButton(text="📋 Экспорт отчета", callback_data="analytics_export")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )

def ai_assistant_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура AI-ассистента"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Генерация текста", callback_data="ai_generate")],
            [InlineKeyboardButton(text="🛡 Проверка на спам", callback_data="ai_spam_check")],
            [InlineKeyboardButton(text="🎯 Улучшить CTA", callback_data="ai_improve_cta")],
            [InlineKeyboardButton(text="🔄 A/B тестирование", callback_data="ai_ab_test")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )

def confirm_keyboard(action: str, item_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    callback_confirm = f"confirm_{action}_{item_id}" if item_id else f"confirm_{action}"
    callback_cancel = f"cancel_{action}_{item_id}" if item_id else f"cancel_{action}"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=callback_confirm),
                InlineKeyboardButton(text="❌ Нет", callback_data=callback_cancel)
            ]
        ]
    )

def pagination_keyboard(current_page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура пагинации"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки навигации
    if current_page > 1:
        builder.add(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_page_{current_page - 1}"))
    
    builder.add(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="current_page"))
    
    if current_page < total_pages:
        builder.add(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_page_{current_page + 1}"))
    
    builder.adjust(3)
    return builder.as_markup()

def back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    """Простая кнопка назад"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=callback_data)]
        ]
    )