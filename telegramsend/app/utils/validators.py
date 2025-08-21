"""Валидаторы (заглушка)."""
import re
from typing import Optional, List, Tuple
from email_validator import validate_email, EmailNotValidError

def validate_email_address(email: str) -> Tuple[bool, Optional[str]]:
    """Валидация email адреса"""
    try:
        validated_email = validate_email(email)
        return True, validated_email.email
    except EmailNotValidError as e:
        return False, str(e)

def validate_phone_number(phone: str) -> Tuple[bool, Optional[str]]:
    """Валидация номера телефона"""
    # Убираем все не цифры кроме +
    clean_phone = re.sub(r'[^\d+]', '', phone)
    
    # Проверяем формат
    if re.match(r'^\+?[1-9]\d{6,14}$', clean_phone):
        # Добавляем + если его нет
        if not clean_phone.startswith('+'):
            clean_phone = '+' + clean_phone
        return True, clean_phone
    
    return False, "Неверный формат номера телефона"

def validate_telegram_username(username: str) -> Tuple[bool, Optional[str]]:
    """Валидация Telegram username"""
    # Убираем @
    clean_username = username.lstrip('@')
    
    # Проверяем формат: 5-32 символа, буквы, цифры, подчеркивания
    if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{4,31}$', clean_username):
        return True, clean_username
    
    return False, "Неверный формат username"

def validate_telegram_id(telegram_id: str) -> Tuple[bool, Optional[int]]:
    """Валидация Telegram ID"""
    try:
        user_id = int(telegram_id)
        if user_id > 0:
            return True, user_id
        return False, "ID должен быть положительным числом"
    except ValueError:
        return False, "ID должен быть числом"

def validate_campaign_name(name: str) -> Tuple[bool, Optional[str]]:
    """Валидация названия кампании"""
    name = name.strip()
    if not name:
        return False, "Название не может быть пустым"
    
    if len(name) < 3:
        return False, "Название должно содержать минимум 3 символа"
    
    if len(name) > 100:
        return False, "Название не должно превышать 100 символов"
    
    # Проверяем на недопустимые символы
    if re.search(r'[<>"/\\|?*]', name):
        return False, "Название содержит недопустимые символы"
    
    return True, name

def validate_message_content(content: str, max_length: int = 4000) -> Tuple[bool, Optional[str]]:
    """Валидация содержимого сообщения"""
    content = content.strip()
    
    if not content:
        return False, "Сообщение не может быть пустым"
    
    if len(content) > max_length:
        return False, f"Сообщение не должно превышать {max_length} символов"
    
    return True, content

def validate_delay_settings(min_delay: str, max_delay: str) -> Tuple[bool, Optional[Tuple[int, int]]]:
    """Валидация настроек задержки"""
    try:
        min_val = int(min_delay)
        max_val = int(max_delay)
        
        if min_val < 1:
            return False, "Минимальная задержка должна быть больше 0"
        
        if max_val < min_val:
            return False, "Максимальная задержка должна быть больше минимальной"
        
        if max_val > 3600:  # 1 час
            return False, "Максимальная задержка не должна превышать 3600 секунд"
        
        return True, (min_val, max_val)
    
    except ValueError:
        return False, "Задержки должны быть числами"

def validate_batch_size(batch_size: str) -> Tuple[bool, Optional[int]]:
    """Валидация размера батча"""
    try:
        size = int(batch_size)
        
        if size < 1:
            return False, "Размер батча должен быть больше 0"
        
        if size > 1000:
            return False, "Размер батча не должен превышать 1000"
        
        return True, size
    
    except ValueError:
        return False, "Размер батча должен быть числом"

def parse_contacts_file(content: str, contact_type: str) -> Tuple[List[str], List[str]]:
    """Парсинг файла с контактами"""
    valid_contacts = []
    invalid_contacts = []
    
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Разделяем по запятой, табу или точке с запятой
        contacts = re.split(r'[,;\t]', line)
        
        for contact in contacts:
            contact = contact.strip()
            if not contact:
                continue
            
            if contact_type == "email":
                is_valid, result = validate_email_address(contact)
            elif contact_type == "phone":
                is_valid, result = validate_phone_number(contact)
            elif contact_type == "telegram":
                # Пробуем как username, потом как ID
                is_valid, result = validate_telegram_username(contact)
                if not is_valid:
                    is_valid, result = validate_telegram_id(contact)
                    if is_valid:
                        result = str(result)
            else:
                is_valid, result = True, contact
            
            if is_valid:
                valid_contacts.append(result)
            else:
                invalid_contacts.append(f"{contact}: {result}")
    
    return valid_contacts, invalid_contacts

def validate_smtp_settings(host: str, port: str, email: str, password: str) -> Tuple[bool, Optional[str]]:
    """Валидация SMTP настроек"""
    if not host.strip():
        return False, "SMTP хост не может быть пустым"
    
    try:
        port_int = int(port)
        if port_int < 1 or port_int > 65535:
            return False, "Порт должен быть от 1 до 65535"
    except ValueError:
        return False, "Порт должен быть числом"
    
    is_valid, error = validate_email_address(email)
    if not is_valid:
        return False, f"Неверный email: {error}"
    
    if not password.strip():
        return False, "Пароль не может быть пустым"
    
    return True, None

def validate_telegram_api_settings(api_id: str, api_hash: str) -> Tuple[bool, Optional[str]]:
    """Валидация Telegram API настроек"""
    try:
        api_id_int = int(api_id)
        if api_id_int <= 0:
            return False, "API ID должен быть положительным числом"
    except ValueError:
        return False, "API ID должен быть числом"
    
    if not api_hash.strip():
        return False, "API Hash не может быть пустым"
    
    if len(api_hash) != 32:
        return False, "API Hash должен содержать 32 символа"
    
    return True, None