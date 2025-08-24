from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from app.database.database import get_db
from app.database.models import SubscriptionStatus, User, Contact, FileUpload, SenderType
from app.database.models import User, Contact, FileUpload, SenderType, SubscriptionStatus
from app.utils.keyboards import contacts_keyboard, file_type_keyboard, back_keyboard
from app.utils.decorators import handle_errors, log_user_action, subscription_required
from app.utils.validators import parse_contacts_file
from app.config import settings, SUBSCRIPTION_PLANS
import aiofiles
import os
import uuid
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)

class ContactStates(StatesGroup):
    waiting_for_file = State()
    waiting_for_manual_contact = State()
    waiting_for_contact_name = State()
    waiting_for_search_query = State()
    waiting_for_tag_name = State()

@router.message(F.text == "👥 Контакты")
@subscription_required()
@handle_errors
@log_user_action("contacts_menu")
async def contacts_menu(message: types.Message, user: User, db: AsyncSession, **kwargs):
    """Меню управления контактами"""
    # Получаем статистику контактов
    result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user.id,
            Contact.is_active == True
        )
    )
    total_contacts = result.scalar()
    
    # Статистика по типам
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
        type_stats[sender_type] = result.scalar()
    
    # Получаем последние добавленные контакты
    recent_result = await db.execute(
        select(Contact).where(
            and_(
                Contact.user_id == user.id,
                Contact.is_active == True
            )
        )
        .order_by(Contact.created_at.desc())
        .limit(5)
    )
    recent_contacts = recent_result.scalars().all()
    
    # Проверяем лимиты
    plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
    limit = plan["contacts_limit"]
    usage_percent = (total_contacts / limit) * 100 if limit > 0 else 0
    
    contacts_text = (
        f"👥 <b>Управление контактами</b>\n\n"
        f"📊 <b>Общая статистика:</b>\n"
        f"• Всего контактов: {total_contacts:,}/{limit:,} ({usage_percent:.1f}%)\n"
        f"• Добавлено сегодня: {len([c for c in recent_contacts if c.created_at.date() == datetime.utcnow().date()])}\n\n"
        f"📈 <b>Распределение по типам:</b>\n"
    )
    
    type_icons = {
        SenderType.TELEGRAM: "📱",
        SenderType.EMAIL: "📧",
        SenderType.WHATSAPP: "💬",
        SenderType.SMS: "📞",
        SenderType.VIBER: "🟣"
    }
    
    for sender_type, icon in type_icons.items():
        count = type_stats.get(sender_type, 0)
        if count > 0:
            contacts_text += f"{icon} {sender_type.value.capitalize()}: {count:,}\n"
    
    if recent_contacts:
        contacts_text += f"\n📝 <b>Последние добавленные:</b>\n"
        for contact in recent_contacts[:3]:
            type_icon = type_icons.get(contact.type, "❓")
            identifier = contact.identifier
            if len(identifier) > 20:
                identifier = identifier[:17] + "..."
            contacts_text += f"{type_icon} {identifier}\n"
        
        if len(recent_contacts) > 3:
            contacts_text += f"... и еще {len(recent_contacts) - 3}\n"
    
    contacts_text += "\n"
    
    if total_contacts >= limit:
        contacts_text += f"⚠️ <b>Достигнут лимит контактов!</b>\n"
        contacts_text += f"Обновите план для увеличения лимита."
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="💳 Улучшить план", callback_data="subscription_menu")],
                [types.InlineKeyboardButton(text="🗑 Очистить контакты", callback_data="contacts_cleanup")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
            ]
        )
    else:
        available = limit - total_contacts
        contacts_text += f"✅ Доступно слотов: {available:,}\n"
        contacts_text += "Выберите действие:"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="📁 Загрузить файл", callback_data="contacts_upload"),
                    types.InlineKeyboardButton(text="👤 Добавить вручную", callback_data="contacts_add_manual")
                ],
                [
                    types.InlineKeyboardButton(text="📋 Мои списки", callback_data="contacts_lists"),
                    types.InlineKeyboardButton(text="🔍 Поиск", callback_data="contacts_search")
                ],
                [
                    types.InlineKeyboardButton(text="🏷 Теги", callback_data="contacts_tags"),
                    types.InlineKeyboardButton(text="🗑 Очистка", callback_data="contacts_cleanup")
                ],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
            ]
        )
    
    await message.answer(
        contacts_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "contacts_upload")
@subscription_required()
@handle_errors
async def contacts_upload_start(callback: types.CallbackQuery, state: FSMContext, user: User, db: AsyncSession):
    """Начало загрузки файла с контактами"""
    # Проверяем лимиты
    result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user.id,
            Contact.is_active == True
        )
    )
    current_contacts = result.scalar()
    
    plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
    if current_contacts >= plan["contacts_limit"]:
        await callback.answer("Достигнут лимит контактов", show_alert=True)
        return
    
    available_slots = plan["contacts_limit"] - current_contacts
    
    await callback.message.edit_text(
        f"📁 <b>Загрузка файла с контактами</b>\n\n"
        f"📊 <b>Доступно слотов:</b> {available_slots:,}\n\n"
        f"📋 <b>Поддерживаемые форматы:</b>\n"
        f"• .txt (один контакт на строку)\n"
        f"• .csv (с заголовками)\n"
        f"• Кодировка: UTF-8\n"
        f"• Размер до {settings.MAX_FILE_SIZE // 1024 // 1024}MB\n\n"
        f"Выберите тип контактов:",
        parse_mode="HTML",
        reply_markup=file_type_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("file_"))
@handle_errors
async def select_file_type(callback: types.CallbackQuery, state: FSMContext):
    """Выбор типа файла"""
    file_type = callback.data.split("_")[1]
    await state.update_data(file_type=file_type)
    
    type_descriptions = {
        "telegram": "username (@user) или ID пользователей",
        "email": "email адреса",
        "phone": "номера телефонов в международном формате"
    }
    
    format_examples = {
        "telegram": (
            "@username1\n"
            "123456789\n"
            "https://t.me/channel\n"
            "@group_name"
        ),
        "email": (
            "user@example.com\n"
            "test@gmail.com\n"
            "support@company.com"
        ),
        "phone": (
            "+1234567890\n"
            "+79123456789\n"
            "+380123456789"
        )
    }
    
    upload_text = (
        f"📄 <b>Загрузка {type_descriptions[file_type]}</b>\n\n"
        f"📋 <b>Поддерживаемые форматы:</b>\n"
        f"• .txt файлы (один контакт на строку)\n"
        f"• .csv файлы (с колонками)\n"
        f"• Максимальный размер: {settings.MAX_FILE_SIZE // 1024 // 1024}MB\n\n"
        f"💡 <b>Примеры содержимого:</b>\n"
        f"<code>{format_examples[file_type]}</code>\n\n"
        f"📎 <b>Отправьте файл:</b>"
    )
    
    await callback.message.edit_text(
        upload_text,
        parse_mode="HTML",
        reply_markup=back_keyboard("contacts_upload")
    )
    
    await state.set_state(ContactStates.waiting_for_file)
    await callback.answer()

@router.message(ContactStates.waiting_for_file, F.document)
@handle_errors
async def process_file_upload(message: types.Message, state: FSMContext):
    """Обработка загруженного файла"""
    document = message.document
    
    # Проверка размера файла
    if document.file_size > settings.MAX_FILE_SIZE:
        await message.answer(
            f"❌ Файл слишком большой. Максимальный размер: {settings.MAX_FILE_SIZE // 1024 // 1024}MB"
        )
        return
    
    # Проверка типа файла
    allowed_extensions = ['.txt', '.csv']
    file_ext = None
    for ext in allowed_extensions:
        if document.file_name.lower().endswith(ext):
            file_ext = ext
            break
    
    if not file_ext:
        await message.answer("❌ Поддерживаются только .txt и .csv файлы")
        return
    
    data = await state.get_data()
    file_type = data["file_type"]
    
    try:
        # Показываем прогресс
        progress_msg = await message.answer("📥 Скачиваем файл...")
        
        # Скачиваем файл
        file_info = await message.bot.get_file(document.file_id)
        file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}{file_ext}")
        
        # Создаем директорию если не существует
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        await message.bot.download_file(file_info.file_path, file_path)
        
        await progress_msg.edit_text("🔍 Анализируем файл...")
        
        # Читаем и парсим файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # Парсим контакты
        if file_ext == '.csv':
            from app.services.file_parser import FileParser
            valid_contacts, invalid_contacts = FileParser.parse_csv_file(content, file_type)
        else:
            valid_contacts, invalid_contacts = parse_contacts_file(content, file_type)
        
        await progress_msg.edit_text("💾 Сохраняем контакты...")
        
        if not valid_contacts:
            await progress_msg.delete()
            await message.answer("❌ В файле не найдено валидных контактов")
            os.remove(file_path)
            return
        
        # Проверяем лимиты и сохраняем
        async for db in get_db():
            result = await db.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
            user = result.scalar_one_or_none()
            
            result = await db.execute(
                select(func.count(Contact.id)).where(
                    Contact.user_id == user.id,
                    Contact.is_active == True
                )
            )
            current_contacts = result.scalar()
            
            plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
            available_slots = plan["contacts_limit"] - current_contacts
            
            if len(valid_contacts) > available_slots:
                await progress_msg.edit_text(
                    f"⚠️ Можно загрузить только {available_slots} контактов из {len(valid_contacts)}\n"
                    f"Достигнут лимит плана {user.subscription_plan.capitalize()}"
                )
                valid_contacts = valid_contacts[:available_slots]
            
            # Определяем тип контакта
            contact_type_map = {
                "telegram": SenderType.TELEGRAM,
                "email": SenderType.EMAIL,
                "phone": SenderType.SMS  # По умолчанию для телефонов
            }
            
            # Если загружаются телефоны, спрашиваем для какой платформы
            if file_type == "phone":
                keyboard = types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(text="💬 WhatsApp", callback_data=f"set_phone_type_whatsapp"),
                            types.InlineKeyboardButton(text="📞 SMS", callback_data=f"set_phone_type_sms")
                        ],
                        [types.InlineKeyboardButton(text="🟣 Viber", callback_data=f"set_phone_type_viber")]
                    ]
                )
                
                await state.update_data(
                    valid_contacts=valid_contacts,
                    invalid_contacts=invalid_contacts,
                    file_path=file_path
                )
                
                await progress_msg.edit_text(
                    f"📞 <b>Найдено {len(valid_contacts)} номеров</b>\n\n"
                    f"Для какой платформы сохранить эти номера?",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return
            
            contact_type = contact_type_map[file_type]
            
            # Сохраняем информацию о файле
            file_upload = FileUpload(
                user_id=user.id,
                filename=os.path.basename(file_path),
                original_filename=document.file_name,
                file_size=document.file_size,
                file_type=file_type,
                upload_path=file_path,
                contacts_count=len(valid_contacts)
            )
            
            db.add(file_upload)
            await db.commit()
            
            # Добавляем контакты
            new_contacts = 0
            duplicate_contacts = 0
            
            for contact_data in valid_contacts:
                if isinstance(contact_data, dict):
                    contact_id = contact_data['identifier']
                    first_name = contact_data.get('first_name', '')
                    last_name = contact_data.get('last_name', '')
                    metadata = contact_data.get('metadata', {})
                else:
                    contact_id = contact_data
                    first_name = ''
                    last_name = ''
                    metadata = {}
                
                # Проверяем на дубликаты
                result = await db.execute(
                    select(Contact).where(
                        and_(
                            Contact.user_id == user.id,
                            Contact.identifier == contact_id,
                            Contact.type == contact_type
                        )
                    )
                )
                existing_contact = result.scalar_one_or_none()
                
                if existing_contact:
                    duplicate_contacts += 1
                    continue
                
                contact = Contact(
                    user_id=user.id,
                    identifier=contact_id,
                    type=contact_type,
                    first_name=first_name,
                    last_name=last_name,
                    metadata=metadata,
                    is_active=True
                )
                
                db.add(contact)
                new_contacts += 1
            
            await db.commit()
            
            # Отчет о загрузке
            result_text = (
                f"✅ <b>Файл успешно обработан!</b>\n\n"
                f"📊 <b>Результаты:</b>\n"
                f"• Новых контактов: {new_contacts:,}\n"
                f"• Дубликатов пропущено: {duplicate_contacts:,}\n"
                f"• Тип: {contact_type.value.capitalize()}\n"
            )
            
            if invalid_contacts:
                result_text += f"• Некорректных записей: {len(invalid_contacts):,}\n"
                
                if len(invalid_contacts) <= 5:
                    result_text += f"\n❌ <b>Некорректные записи:</b>\n"
                    for invalid in invalid_contacts:
                        result_text += f"• {invalid}\n"
            
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="📋 Посмотреть списки", callback_data="contacts_lists")],
                    [types.InlineKeyboardButton(text="◀️ К контактам", callback_data="contacts_menu")]
                ]
            )
            
            await progress_msg.delete()
            await message.answer(
                result_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Удаляем временный файл
            try:
                os.remove(file_path)
            except:
                pass
            
            await state.clear()
            logger.info(f"Contacts uploaded: {new_contacts} new contacts for user {user.telegram_id}")
    
    except Exception as e:
        logger.error(f"Error processing file upload: {e}")
        await message.answer(
            "❌ Ошибка обработки файла. Проверьте формат и попробуйте снова."
        )
        
        try:
            os.remove(file_path)
        except:
            pass

@router.callback_query(F.data.startswith("set_phone_type_"))
@handle_errors
async def set_phone_type(callback: types.CallbackQuery, state: FSMContext):
    """Установка типа для номеров телефонов"""
    phone_type = callback.data.split("_")[-1]
    
    type_mapping = {
        "whatsapp": SenderType.WHATSAPP,
        "sms": SenderType.SMS,
        "viber": SenderType.VIBER
    }
    
    contact_type = type_mapping[phone_type]
    data = await state.get_data()
    
    # Сохраняем контакты с выбранным типом
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        valid_contacts = data["valid_contacts"]
        new_contacts = 0
        duplicate_contacts = 0
        
        for contact_id in valid_contacts:
            # Проверяем на дубликаты
            result = await db.execute(
                select(Contact).where(
                    and_(
                        Contact.user_id == user.id,
                        Contact.identifier == contact_id,
                        Contact.type == contact_type
                    )
                )
            )
            existing_contact = result.scalar_one_or_none()
            
            if existing_contact:
                duplicate_contacts += 1
                continue
            
            contact = Contact(
                user_id=user.id,
                identifier=contact_id,
                type=contact_type,
                is_active=True
            )
            
            db.add(contact)
            new_contacts += 1
        
        await db.commit()
        
        result_text = (
            f"✅ <b>Номера сохранены для {phone_type.upper()}!</b>\n\n"
            f"📊 <b>Результаты:</b>\n"
            f"• Новых контактов: {new_contacts:,}\n"
            f"• Дубликатов пропущено: {duplicate_contacts:,}\n"
        )
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="◀️ К контактам", callback_data="contacts_menu")]
            ]
        )
        
        await callback.message.edit_text(
            result_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    # Удаляем временный файл
    try:
        os.remove(data.get("file_path", ""))
    except:
        pass
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "contacts_search")
@subscription_required()
@handle_errors
async def contacts_search_start(callback: types.CallbackQuery, state: FSMContext, user: User, db: AsyncSession):
    """Начало поиска контактов"""
    await callback.message.edit_text(
        "🔍 <b>Поиск контактов</b>\n\n"
        "Введите поисковый запрос:\n\n"
        "💡 <b>Примеры:</b>\n"
        "• @username - поиск по username\n"
        "• gmail.com - поиск по домену email\n"
        "• +7912 - поиск по началу номера\n"
        "• Иван - поиск по имени",
        parse_mode="HTML",
        reply_markup=back_keyboard("contacts_menu")
    )
    
    await state.set_state(ContactStates.waiting_for_search_query)
    await callback.answer()

@router.message(ContactStates.waiting_for_search_query)
@handle_errors
async def process_search_query(message: types.Message, state: FSMContext):
    """Обработка поискового запроса"""
    query = message.text.strip()
    
    if len(query) < 2:
        await message.answer("❌ Запрос должен содержать минимум 2 символа")
        return
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        # Поиск контактов
        search_result = await db.execute(
            select(Contact).where(
                and_(
                    Contact.user_id == user.id,
                    Contact.is_active == True,
                    or_(
                        Contact.identifier.contains(query),
                        Contact.first_name.contains(query),
                        Contact.last_name.contains(query)
                    )
                )
            ).order_by(Contact.created_at.desc()).limit(20)
        )
        
        contacts = search_result.scalars().all()
        
        if not contacts:
            await message.answer(
                f"🔍 <b>Поиск: '{query}'</b>\n\n"
                f"❌ Контакты не найдены",
                parse_mode="HTML",
                reply_markup=back_keyboard("contacts_menu")
            )
            await state.clear()
            return
        
        search_text = f"🔍 <b>Результаты поиска: '{query}'</b>\n\n"
        search_text += f"📊 Найдено контактов: {len(contacts)}\n\n"
        
        type_icons = {
            SenderType.TELEGRAM: "📱",
            SenderType.EMAIL: "📧",
            SenderType.WHATSAPP: "💬",
            SenderType.SMS: "📞",
            SenderType.VIBER: "🟣"
        }
        
        for i, contact in enumerate(contacts[:10], 1):
            type_icon = type_icons.get(contact.type, "❓")
            name = ""
            if contact.first_name or contact.last_name:
                name = f" ({contact.first_name} {contact.last_name})".strip()
            
            search_text += f"{i}. {type_icon} {contact.identifier}{name}\n"
        
        if len(contacts) > 10:
            search_text += f"\n... и еще {len(contacts) - 10} контактов"
        
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="🔍 Новый поиск", callback_data="contacts_search")],
                [types.InlineKeyboardButton(text="◀️ К контактам", callback_data="contacts_menu")]
            ]
        )
        
        await message.answer(
            search_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        await state.clear()

@router.callback_query(F.data == "contacts_cleanup")
@subscription_required()
@handle_errors
async def contacts_cleanup_start(callback: types.CallbackQuery, user: User, db: AsyncSession):
    """Очистка контактов"""
    # Получаем статистику
    result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user.id,
            Contact.is_active == True
        )
    )
    active_contacts = result.scalar()
    
    result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.user_id == user.id,
            Contact.is_active == False
        )
    )
    inactive_contacts = result.scalar()
    
    cleanup_text = (
        f"🗑 <b>Очистка контактов</b>\n\n"
        f"📊 <b>Текущее состояние:</b>\n"
        f"• Активных контактов: {active_contacts:,}\n"
        f"• Неактивных контактов: {inactive_contacts:,}\n\n"
        f"Выберите действие:"
    )
    
    keyboard_buttons = []
    
    if inactive_contacts > 0:
        keyboard_buttons.append([
            types.InlineKeyboardButton(
                text=f"🗑 Удалить неактивные ({inactive_contacts:,})",
                callback_data="cleanup_inactive"
            )
        ])
    
    if active_contacts > 0:
        keyboard_buttons.append([
            types.InlineKeyboardButton(
                text="🗑 Удалить дубликаты",
                callback_data="cleanup_duplicates"
            )
        ])
        keyboard_buttons.append([
            types.InlineKeyboardButton(
                text="⚠️ Удалить ВСЕ контакты",
                callback_data="cleanup_all"
            )
        ])
    
    keyboard_buttons.append([
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="contacts_menu")
    ])
    
    await callback.message.edit_text(
        cleanup_text,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await callback.answer()

@router.callback_query(F.data == "cleanup_duplicates")
@subscription_required()
@handle_errors
async def cleanup_duplicates(callback: types.CallbackQuery, user: User, db: AsyncSession):
    """Удаление дубликатов"""
    progress_msg = await callback.message.edit_text("🔍 Ищем дубликаты...")
    
    # Находим дубликаты
    duplicates_result = await db.execute(
        select(
            Contact.identifier,
            Contact.type,
            func.count(Contact.id).label('count'),
            func.min(Contact.id).label('keep_id')
        ).where(
            and_(
                Contact.user_id == user.id,
                Contact.is_active == True
            )
        ).group_by(Contact.identifier, Contact.type).having(func.count(Contact.id) > 1)
    )
    
    duplicates = duplicates_result.all()
    
    if not duplicates:
        await progress_msg.edit_text(
            "✅ <b>Дубликаты не найдены</b>\n\n"
            "Все ваши контакты уникальны!",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text="◀️ Назад", callback_data="contacts_cleanup")]]
            )
        )
        return
    
    await progress_msg.edit_text("🗑 Удаляем дубликаты...")
    
    deleted_count = 0
    for duplicate in duplicates:
        # Удаляем все кроме самого старого
        result = await db.execute(
            select(Contact.id).where(
                and_(
                    Contact.user_id == user.id,
                    Contact.identifier == duplicate.identifier,
                    Contact.type == duplicate.type,
                    Contact.id != duplicate.keep_id
                )
            )
        )
        
        ids_to_delete = [row[0] for row in result.all()]
        
        for contact_id in ids_to_delete:
            contact = await db.get(Contact, contact_id)
            if contact:
                await db.delete(contact)
                deleted_count += 1
    
    await db.commit()
    
    await progress_msg.edit_text(
        f"✅ <b>Очистка завершена!</b>\n\n"
        f"🗑 Удалено дубликатов: {deleted_count:,}\n"
        f"📊 Найдено групп дубликатов: {len(duplicates)}",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="◀️ К контактам", callback_data="contacts_menu")]]
        )
    )

# Back handler
@router.callback_query(F.data == "contacts_menu")
@handle_errors
async def back_to_contacts_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в меню контактов"""
    await state.clear()
    
    user_id = callback.from_user.id
    
    async for db in get_db():
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден. Используйте /start", show_alert=True)
            return
        
        if user.subscription_status != SubscriptionStatus.ACTIVE:
            await callback.answer("🔒 Нужна активная подписка!", show_alert=True)
            return
        
        await contacts_menu(callback.message, user, db)
    
    await callback.answer()