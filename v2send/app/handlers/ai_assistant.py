from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.services.ai_assistant import AIAssistant
from app.database.models import SubscriptionStatus
from app.utils.keyboards import ai_assistant_keyboard, back_keyboard
from app.utils.decorators import handle_errors, log_user_action, subscription_required
import logging

router = Router()
logger = logging.getLogger(__name__)

class AIStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_text_to_check = State()
    waiting_for_cta_to_improve = State()
    waiting_for_ab_text = State()

@router.message(F.text == "🤖 AI-Ассистент")
@subscription_required(["pro", "premium"])
@handle_errors
@log_user_action("ai_assistant_menu")
async def ai_assistant_menu(message: types.Message, **kwargs):
    """Главное меню AI-ассистента"""
    
    ai = AIAssistant()
    
    if not ai.is_available():
        await message.answer(
            "❌ <b>AI-ассистент недоступен</b>\n\n"
            "Для использования AI-ассистента необходимо настроить DeepSeek API ключ.\n"
            "Обратитесь к администратору для настройки.",
            parse_mode="HTML",
            reply_markup=back_keyboard("back_to_menu")
        )
        return
    
    ai_text = (
        "🤖 <b>AI-Ассистент</b>\n\n"
        "Ваш умный помощник для создания эффективного контента!\n\n"
        "🎯 <b>Возможности:</b>\n"
        "• ✍️ Генерация текстов рассылок\n"
        "• 🛡 Проверка на спам-фильтры\n"
        "• 🎯 Улучшение призывов к действию\n"
        "• 🔄 A/B тестирование вариантов\n"
        "• 📊 Анализ тональности текста\n\n"
        "Выберите нужную функцию:"
    )
    
    await message.answer(
        ai_text,
        parse_mode="HTML",
        reply_markup=ai_assistant_keyboard()
    )

@router.callback_query(F.data == "ai_assistant_menu")
@handle_errors
async def back_to_ai_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Callback для возврата в меню AI-ассистента"""
    await state.clear()
    
    ai = AIAssistant()
    
    if not ai.is_available():
        await callback.message.edit_text(
            "❌ <b>AI-ассистент недоступен</b>\n\n"
            "Для использования AI-ассистента необходимо настроить DeepSeek API ключ.\n"
            "Обратитесь к администратору для настройки.",
            parse_mode="HTML",
            reply_markup=back_keyboard("back_to_menu")
        )
        return
    
    ai_text = (
        "🤖 <b>AI-Ассистент</b>\n\n"
        "Ваш умный помощник для создания эффективного контента!\n\n"
        "🎯 <b>Возможности:</b>\n"
        "• ✍️ Генерация текстов рассылок\n"
        "• 🛡 Проверка на спам-фильтры\n"
        "• 🎯 Улучшение призывов к действию\n"
        "• 🔄 A/B тестирование вариантов\n"
        "• 📊 Анализ тональности текста\n\n"
        "Выберите нужную функцию:"
    )
    
    await callback.message.edit_text(
        ai_text,
        parse_mode="HTML",
        reply_markup=ai_assistant_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "ai_generate")
@handle_errors
async def ai_generate_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало генерации текста"""
    
    await callback.message.edit_text(
        "✍️ <b>Генерация текста</b>\n\n"
        "Опишите тему или цель вашего сообщения:\n\n"
        "📝 <b>Примеры:</b>\n"
        "• Акция на товары со скидкой 50%\n"
        "• Приглашение на вебинар по маркетингу\n"
        "• Новости компании и обновления\n"
        "• Поздравление с праздником",
        parse_mode="HTML",
        reply_markup=back_keyboard("ai_assistant_menu")
    )
    
    await state.set_state(AIStates.waiting_for_topic)
    await callback.answer()

@router.message(AIStates.waiting_for_topic)
@handle_errors
async def ai_generate_process(message: types.Message, state: FSMContext):
    """Обработка генерации текста"""
    
    topic = message.text.strip()
    
    if len(topic) < 10:
        await message.answer(
            "❌ Опишите тему более подробно (минимум 10 символов)"
        )
        return
    
    # Показываем индикатор загрузки
    loading_msg = await message.answer("🤖 Генерирую текст...")
    
    ai = AIAssistant()
    
    # Генерируем текст
    result = await ai.generate_message(
        topic=topic,
        target_audience="подписчики",
        tone="дружелюбный",
        message_type="рекламное",
        platform="telegram"
    )
    
    await loading_msg.delete()
    
    if result["success"]:
        data = result["result"]
        
        generated_text = (
            f"✅ <b>Текст сгенерирован!</b>\n\n"
            f"📝 <b>Тема:</b> {data.get('subject', 'Без темы')}\n\n"
            f"💬 <b>Сообщение:</b>\n{data.get('message', '')}\n\n"
            f"🎯 <b>Призыв к действию:</b>\n{data.get('cta', '')}\n\n"
            f"💡 <b>Советы:</b>\n"
        )
        
        for tip in data.get('tips', []):
            generated_text += f"• {tip}\n"
        
        generated_text += f"\n📊 Длина: {result['length']}/{result['max_length']} символов"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Генерировать еще", callback_data="ai_generate")],
                [types.InlineKeyboardButton(text="🛡 Проверить на спам", callback_data="check_generated_spam")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="ai_assistant_menu")]
            ]
        )
        
        await state.update_data(last_generated_text=data.get('message', ''))
        
    else:
        generated_text = f"❌ <b>Ошибка генерации:</b>\n{result['error']}"
        keyboard = back_keyboard("ai_assistant_menu")
    
    await message.answer(
        generated_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.clear()

@router.callback_query(F.data == "ai_spam_check")
@handle_errors
async def ai_spam_check_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало проверки на спам"""
    
    await callback.message.edit_text(
        "🛡 <b>Проверка на спам</b>\n\n"
        "Отправьте текст сообщения для анализа на спам-фильтры:\n\n"
        "📋 Система проверит:\n"
        "• Спам-слова и фразы\n"
        "• Избыток заглавных букв\n"
        "• Подозрительные элементы\n"
        "• Общий риск попадания в спам",
        parse_mode="HTML",
        reply_markup=back_keyboard("ai_assistant_menu")
    )
    
    await state.set_state(AIStates.waiting_for_text_to_check)
    await callback.answer()

@router.message(AIStates.waiting_for_text_to_check)
@handle_errors
async def ai_spam_check_process(message: types.Message, state: FSMContext):
    """Обработка проверки на спам"""
    
    text = message.text.strip()
    
    if len(text) < 10:
        await message.answer("❌ Текст слишком короткий для анализа")
        return
    
    loading_msg = await message.answer("🛡 Анализирую на спам...")
    
    ai = AIAssistant()
    result = await ai.check_spam_score(text, "email")
    
    await loading_msg.delete()
    
    if result["success"]:
        data = result["result"]
        spam_score = data.get("spam_score", 0)
        risk_level = data.get("risk_level", "неизвестен")
        
        # Определяем иконку риска
        if spam_score <= 3:
            risk_icon = "🟢"
        elif spam_score <= 6:
            risk_icon = "🟡"
        else:
            risk_icon = "🔴"
        
        spam_text = (
            f"🛡 <b>Анализ на спам завершен</b>\n\n"
            f"{risk_icon} <b>Оценка спама:</b> {spam_score}/10\n"
            f"📊 <b>Уровень риска:</b> {risk_level}\n\n"
        )
        
        if data.get("issues"):
            spam_text += "<b>⚠️ Обнаруженные проблемы:</b>\n"
            for issue in data["issues"]:
                spam_text += f"• {issue}\n"
            spam_text += "\n"
        
        if data.get("suggestions"):
            spam_text += "<b>💡 Рекомендации:</b>\n"
            for suggestion in data["suggestions"]:
                spam_text += f"• {suggestion}\n"
            spam_text += "\n"
        
        if data.get("spam_words"):
            spam_text += "<b>🚫 Найденные спам-слова:</b>\n"
            spam_text += ", ".join(data["spam_words"])
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Проверить другой текст", callback_data="ai_spam_check")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="ai_assistant_menu")]
            ]
        )
        
    else:
        spam_text = f"❌ <b>Ошибка анализа:</b>\n{result['error']}"
        keyboard = back_keyboard("ai_assistant_menu")
    
    await message.answer(
        spam_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.clear()

@router.callback_query(F.data == "ai_improve_cta")
@handle_errors
async def ai_improve_cta_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало улучшения CTA"""
    
    await callback.message.edit_text(
        "🎯 <b>Улучшение призыва к действию</b>\n\n"
        "Отправьте ваш текущий призыв к действию (CTA):\n\n"
        "📝 <b>Примеры CTA:</b>\n"
        "• Купить сейчас\n"
        "• Узнать больше\n"
        "• Зарегистрироваться\n"
        "• Скачать бесплатно\n\n"
        "Я проанализирую и предложу улучшения!",
        parse_mode="HTML",
        reply_markup=back_keyboard("ai_assistant_menu")
    )
    
    await state.set_state(AIStates.waiting_for_cta_to_improve)
    await callback.answer()

@router.message(AIStates.waiting_for_cta_to_improve)
@handle_errors
async def ai_improve_cta_process(message: types.Message, state: FSMContext):
    """Обработка улучшения CTA"""
    
    cta = message.text.strip()
    
    if len(cta) < 3:
        await message.answer("❌ CTA слишком короткий")
        return
    
    loading_msg = await message.answer("🎯 Улучшаю призыв к действию...")
    
    ai = AIAssistant()
    result = await ai.improve_cta(cta, "маркетинговая рассылка")
    
    await loading_msg.delete()
    
    if result["success"]:
        data = result["result"]
        
        cta_text = (
            f"🎯 <b>Улучшение CTA завершено</b>\n\n"
            f"📝 <b>Исходный CTA:</b>\n{result['original_cta']}\n\n"
            f"✨ <b>Улучшенный CTA:</b>\n{data.get('improved_cta', '')}\n\n"
            f"💡 <b>Объяснение:</b>\n{data.get('explanation', '')}\n\n"
        )
        
        if data.get("alternatives"):
            cta_text += "<b>🔄 Альтернативные варианты:</b>\n"
            for i, alt in enumerate(data["alternatives"], 1):
                cta_text += f"{i}. {alt}\n"
            cta_text += "\n"
        
        if data.get("tips"):
            cta_text += "<b>📚 Советы:</b>\n"
            for tip in data["tips"]:
                cta_text += f"• {tip}\n"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Улучшить другой CTA", callback_data="ai_improve_cta")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="ai_assistant_menu")]
            ]
        )
        
    else:
        cta_text = f"❌ <b>Ошибка улучшения:</b>\n{result['error']}"
        keyboard = back_keyboard("ai_assistant_menu")
    
    await message.answer(
        cta_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.clear()

@router.callback_query(F.data == "ai_ab_test")
@handle_errors
async def ai_ab_test_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало A/B тестирования"""
    
    await callback.message.edit_text(
        "🔄 <b>A/B тестирование</b>\n\n"
        "Отправьте ваш исходный текст, и я создам несколько вариантов для A/B тестирования:\n\n"
        "📊 <b>Что будет протестировано:</b>\n"
        "• Разные заголовки\n"
        "• Различная длина текста\n"
        "• Разные эмоциональные подходы\n"
        "• Альтернативные CTA",
        parse_mode="HTML",
        reply_markup=back_keyboard("ai_assistant_menu")
    )
    
    await state.set_state(AIStates.waiting_for_ab_text)
    await callback.answer()

@router.message(AIStates.waiting_for_ab_text)
@handle_errors
async def ai_ab_test_process(message: types.Message, state: FSMContext):
    """Обработка A/B тестирования"""
    
    text = message.text.strip()
    
    if len(text) < 20:
        await message.answer("❌ Текст слишком короткий для создания вариантов")
        return
    
    loading_msg = await message.answer("🔄 Создаю варианты для A/B тестирования...")
    
    ai = AIAssistant()
    result = await ai.generate_ab_variants(text, 3)
    
    await loading_msg.delete()
    
    if result["success"]:
        data = result["result"]
        
        ab_text = (
            f"🔄 <b>Варианты для A/B тестирования</b>\n\n"
            f"📝 <b>Исходный текст:</b>\n{text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        )
        
        for i, variant in enumerate(data.get("variants", []), 1):
            ab_text += (
                f"<b>🅰️ {variant.get('name', f'Вариант {i}')}:</b>\n"
                f"📋 Фокус: {variant.get('focus', 'Не указан')}\n"
                f"💬 Текст: {variant.get('text', '')[:200]}{'...' if len(variant.get('text', '')) > 200 else ''}\n\n"
            )
        
        if data.get("testing_tips"):
            ab_text += "<b>📊 Советы по тестированию:</b>\n"
            for tip in data["testing_tips"]:
                ab_text += f"• {tip}\n"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Создать новые варианты", callback_data="ai_ab_test")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="ai_assistant_menu")]
            ]
        )
        
    else:
        ab_text = f"❌ <b>Ошибка создания вариантов:</b>\n{result['error']}"
        keyboard = back_keyboard("ai_assistant_menu")
    
    await message.answer(
        ab_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.clear()

@router.callback_query(F.data == "check_generated_spam")
@handle_errors
async def check_generated_spam(callback: types.CallbackQuery, state: FSMContext):
    """Проверка сгенерированного текста на спам"""
    
    data = await state.get_data()
    text = data.get("last_generated_text")
    
    if not text:
        await callback.answer("❌ Нет сгенерированного текста для проверки", show_alert=True)
        return
    
    loading_msg = await callback.message.edit_text("🛡 Проверяю сгенерированный текст на спам...")
    
    ai = AIAssistant()
    result = await ai.check_spam_score(text, "telegram")
    
    if result["success"]:
        data = result["result"]
        spam_score = data.get("spam_score", 0)
        
        # Определяем иконку риска
        if spam_score <= 3:
            risk_icon = "🟢"
            risk_text = "Низкий риск"
        elif spam_score <= 6:
            risk_icon = "🟡"
            risk_text = "Средний риск"
        else:
            risk_icon = "🔴"
            risk_text = "Высокий риск"
        
        spam_text = (
            f"🛡 <b>Результат проверки</b>\n\n"
            f"{risk_icon} <b>Спам-оценка:</b> {spam_score}/10\n"
            f"📊 <b>Риск:</b> {risk_text}\n\n"
        )
        
        if data.get("suggestions"):
            spam_text += "<b>💡 Рекомендации:</b>\n"
            for suggestion in data["suggestions"][:3]:
                spam_text += f"• {suggestion}\n"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔄 Генерировать новый текст", callback_data="ai_generate")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="ai_assistant_menu")]
            ]
        )
        
    else:
        spam_text = f"❌ <b>Ошибка проверки:</b>\n{result['error']}"
        keyboard = back_keyboard("ai_assistant_menu")
    
    await loading_msg.edit_text(
        spam_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await callback.answer()