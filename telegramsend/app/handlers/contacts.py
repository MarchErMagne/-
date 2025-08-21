from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database.database import get_db
from app.database.models import User, Contact, FileUpload, SenderType
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

@router.message(F.text == "👥 Контакты")
@subscription_required()
@handle_errors
@log_user_action("contacts_menu")
async def contacts_menu(message: types.Message, user: User, db: AsyncSession):
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
    
    # Проверяем лимиты
    plan = SUBSCRIPTION_PLANS.get(user.subscription_plan, SUBSCRIPTION_PLANS["basic"])
    limit = plan["contacts_limit"]
    
    contacts_text = (
        f"👥 <b>Управление контактами</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего контактов: {total_contacts:,}/{limit:,}\n\n"
        f"📈 <b>По типам:</b>\n"
        f"📱 Telegram: {type_stats.get(SenderType.TELEGRAM, 0):,}\n"
        f"📧 Email: {type_stats.get(SenderType.EMAIL, 0):,}\n"
        f"💬 WhatsApp: {type_stats.get(SenderType.WHATSAPP, 0):,}\n"
        f"📞 SMS: {type_stats.get(SenderType.SMS, 0):,}\n"
        f"🟣 Viber: {type_stats.get(SenderType.VIBER, 0):,}\n\n"
    )
    
    if total_contacts >= limit:
        contacts_text += f"⚠️ Достигнут лимит контактов для плана {user.subscription_plan.capitalize()}"
        keyboard = back_keyboard("back_to_menu")
    else:
        contacts_text += "Выберите действие:"
        keyboard = contacts_keyboard()
    
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
    
    await callback.message.edit_text(
        "📁 <b>Загрузка файла с контактами</b>\n\n"
        "Выберите тип контактов для загрузки:",
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
        "telegram": "username или ID пользователей Telegram",
        "email": "email адреса",
        "phone": "номера телефонов (для SMS/WhatsApp/Viber)"
    }
    
    format_examples = {
        "telegram": "@username\n123456789\nuser2\n@another_user",
        "email": "user@example.com\ntest@gmail.com\nsupport@company.com",
        "phone": "+79123456789\n+1234567890\n+380123456789"
    }
    
    upload_text = (
        f"📄 <b>Загрузка {type_descriptions[file_type]}</b>\n\n"
        f"📋 <b>Формат файла:</b>\n"
        f"• Текстовый файл (.txt)\n"
        f"• Один контакт на строку\n"
        f"• Максимальный размер: {settings.MAX_FILE_SIZE // 1024 // 1024}MB\n\n"
        f"💡 <b>Пример содержимого:</b>\n"
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
    if not document.file_name.endswith('.txt'):
        await message.answer("❌ Поддерживаются только .txt файлы")
        return
    
    data = await state.get_data()
    file_type = data["file_type"]
    
    try:
        # Скачиваем файл
        file_info = await message.bot.get_file(document.file_id)
        file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}.txt")
        
        # Создаем директорию если не существует
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        
        await message.bot.download_file(file_info.file_path, file_path)
        
        # Читаем и парсим файл
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # Парсим контакты
        valid_contacts, invalid_contacts = parse_contacts_file(content, file_type)
        
        if not valid_contacts:
            await message.answer("❌ В файле не найдено валидных контактов")
            os.remove(file_path)
            return
        
        # Проверяем лимиты
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
                await message.answer(
                    f"⚠️ Можно загрузить только {available_slots} контактов из {len(valid_contacts)}\n"
                    f"Достигнут лимит плана {user.subscription_plan.capitalize()}"
                )
                valid_contacts = valid_contacts[:available_slots]
            
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
            
            # Определяем тип контакта
            contact_type_map = {
                "telegram": SenderType.TELEGRAM,
                "email": SenderType.EMAIL,
                "phone": SenderType.SMS  # По умолчанию для телефонов
            }
            contact_type = contact_type_map[file_type]
            
            # Добавляем контакты
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
            
            # Отчет о загрузке
            result_text = (
                f"✅ <b>Файл успешно обработан!</b>\n\n"
                f"📊 <b>Результаты:</b>\n"
                f"• Новых контактов: {new_contacts}\n"
                f"• Дубликатов пропущено: {duplicate_contacts}\n"
            )
            
            if invalid_contacts:
                result_text += f"• Некорректных записей: {len(invalid_contacts)}\n"
                
                if len(invalid_contacts) <= 10:
                    result_text += f"\n❌ <b>Некорректные записи:</b>\n"
                    for invalid in invalid_contacts:
                        result_text += f"• {invalid}\n"
                else:
                    result_text += f"\n❌ Показано первые 10 некорректных записей из {len(invalid_contacts)}\n"
                    for invalid in invalid_contacts[:10]:
                        result_text += f"• {invalid}\n"
            
            await message.answer(
                result_text,
                parse_mode="HTML",
                reply_markup=back_keyboard("contacts_menu")
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
        
        # Удаляем файл при ошибке
        try:
            os.remove(file_path)
        except:
            pass

@router.callback_query(F.data == "contacts_add_manual")
@subscription_required()
@handle_errors
async def contacts_add_manual_start(callback: types.CallbackQuery, state: FSMContext, user: User, db: AsyncSession):
    """Ручное добавление контакта"""
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
    
    await callback.message.edit_text(
        "👤 <b>Ручное добавление контакта</b>\n\n"
        "Выберите тип контакта:",
        parse_mode="HTML",
        reply_markup=file_type_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "contacts_lists")
@subscription_required()
@handle_errors
async def contacts_lists(callback: types.CallbackQuery, user: User, db: AsyncSession):
    """Просмотр списков контактов"""
    # Получаем статистику по типам
    stats_by_type = {}
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
            stats_by_type[sender_type] = count
    
    if not stats_by_type:
        await callback.message.edit_text(
            "📭 <b>У вас пока нет контактов</b>\n\n"
            "Загрузите файл или добавьте контакты вручную.",
            parse_mode="HTML",
            reply_markup=back_keyboard("contacts_menu")
        )
        return
    
    lists_text = "📋 <b>Мои списки контактов</b>\n\n"
    
    type_icons = {
        SenderType.TELEGRAM: "📱",
        SenderType.EMAIL: "📧",
        SenderType.WHATSAPP: "💬",
        SenderType.SMS: "📞",
        SenderType.VIBER: "🟣"
    }
    
    keyboard_buttons = []
    for sender_type, count in stats_by_type.items():
        icon = type_icons.get(sender_type, "❓")
        lists_text += f"{icon} {sender_type.value.capitalize()}: {count:,} контактов\n"
        
        keyboard_buttons.append([
            types.InlineKeyboardButton(
                text=f"{icon} {sender_type.value.capitalize()} ({count:,})",
                callback_data=f"view_contacts_{sender_type.value}"
            )
        ])
    
    keyboard_buttons.append([
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="contacts_menu")
    ])
    
    await callback.message.edit_text(
        lists_text,
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    )
    await callback.answer()

@router.callback_query(F.data == "contacts_menu")
@handle_errors
async def back_to_contacts_menu(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в меню контактов"""
    await state.clear()
    await contacts_menu(callback.message)