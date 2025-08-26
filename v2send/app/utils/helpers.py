import hashlib
import uuid
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import asyncio
import aiofiles
import os

def generate_unique_id() -> str:
    """Генерация уникального ID"""
    return str(uuid.uuid4())

def hash_string(text: str) -> str:
    """Хеширование строки"""
    return hashlib.sha256(text.encode()).hexdigest()

def format_number(number: int) -> str:
    """Форматирование числа с разделителями"""
    return f"{number:,}".replace(",", " ")

def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезка текста с добавлением многоточия"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def format_datetime(dt: datetime, format_str: str = "%d.%m.%Y %H:%M") -> str:
    """Форматирование даты и времени"""
    return dt.strftime(format_str)

def time_ago(dt: datetime) -> str:
    """Относительное время (например, "2 часа назад")"""
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days} дн. назад"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} ч. назад"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} мин. назад"
    else:
        return "только что"

def clean_phone_number(phone: str) -> str:
    """Очистка номера телефона"""
    # Удаляем все символы кроме цифр и +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Добавляем + если его нет и номер не пустой
    if cleaned and not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    
    return cleaned

def extract_mentions(text: str) -> List[str]:
    """Извлечение упоминаний из текста (@username)"""
    pattern = r'@([a-zA-Z0-9_]+)'
    return re.findall(pattern, text)

def extract_hashtags(text: str) -> List[str]:
    """Извлечение хештегов из текста"""
    pattern = r'#([a-zA-Zа-яА-Я0-9_]+)'
    return re.findall(pattern, text)

def extract_urls(text: str) -> List[str]:
    """Извлечение URL из текста"""
    pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(pattern, text)

def safe_filename(filename: str) -> str:
    """Безопасное имя файла"""
    # Убираем опасные символы
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Ограничиваем длину
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:100-len(ext)] + ext
    return filename

def calculate_reading_time(text: str, words_per_minute: int = 200) -> int:
    """Расчет времени чтения текста в минутах"""
    word_count = len(text.split())
    reading_time = word_count / words_per_minute
    return max(1, round(reading_time))

def mask_email(email: str) -> str:
    """Маскировка email адреса"""
    if '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    
    if len(local) <= 2:
        masked_local = local
    else:
        masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
    
    return f"{masked_local}@{domain}"

def mask_phone(phone: str) -> str:
    """Маскировка номера телефона"""
    if len(phone) <= 4:
        return phone
    
    return phone[:2] + '*' * (len(phone) - 4) + phone[-2:]

def parse_schedule_time(time_str: str) -> Optional[datetime]:
    """Парсинг времени из строки"""
    try:
        # Форматы: "HH:MM", "YYYY-MM-DD HH:MM", "DD.MM.YYYY HH:MM"
        time_formats = [
            "%H:%M",
            "%Y-%m-%d %H:%M",
            "%d.%m.%Y %H:%M",
            "%d/%m/%Y %H:%M"
        ]
        
        for fmt in time_formats:
            try:
                if len(time_str) == 5:  # Только время
                    # Используем сегодняшнюю дату
                    today = datetime.now().date()
                    time_obj = datetime.strptime(time_str, "%H:%M").time()
                    return datetime.combine(today, time_obj)
                else:
                    return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        
        return None
    except Exception:
        return None

def validate_file_size(file_size: int, max_size: int = 10 * 1024 * 1024) -> bool:
    """Проверка размера файла"""
    return file_size <= max_size

def get_file_extension(filename: str) -> str:
    """Получение расширения файла"""
    return os.path.splitext(filename)[1].lower()

def is_supported_file_type(filename: str, allowed_types: List[str]) -> bool:
    """Проверка поддерживаемого типа файла"""
    extension = get_file_extension(filename)
    return extension in allowed_types

async def save_uploaded_file(file_data: bytes, filename: str, upload_dir: str = "uploads") -> str:
    """Сохранение загруженного файла"""
    try:
        # Создаем директорию если не существует
        os.makedirs(upload_dir, exist_ok=True)
        
        # Генерируем безопасное имя файла
        safe_name = safe_filename(filename)
        unique_name = f"{uuid.uuid4()}_{safe_name}"
        file_path = os.path.join(upload_dir, unique_name)
        
        # Сохраняем файл
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_data)
        
        return file_path
    except Exception as e:
        raise Exception(f"Ошибка сохранения файла: {str(e)}")

def create_pagination_info(page: int, per_page: int, total: int) -> Dict[str, Any]:
    """Создание информации о пагинации"""
    total_pages = (total + per_page - 1) // per_page
    
    return {
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }

def format_file_size(size_bytes: int) -> str:
    """Форматирование размера файла"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def generate_random_string(length: int = 8) -> str:
    """Генерация случайной строки"""
    import random
    import string
    
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def batch_list(items: List, batch_size: int) -> List[List]:
    """Разбивка списка на батчи"""
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i:i + batch_size])
    return batches

def merge_dicts(*dicts: Dict) -> Dict:
    """Слияние словарей"""
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result

def get_user_agent() -> str:
    """Получение User-Agent для HTTP запросов"""
    return "TelegramSender/1.0 (Bot; +https://t.me/your_bot)"

def retry_async(max_retries: int = 3, delay: float = 1.0):
    """Декоратор для повторных попыток асинхронных функций"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
                    continue
            
            raise last_exception
        return wrapper
    return decorator