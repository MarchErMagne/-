import csv
import json
import openpyxl
from typing import List, Dict, Tuple, Optional
from app.utils.validators import validate_email_address, validate_phone_number, validate_telegram_username
import logging

logger = logging.getLogger(__name__)

class FileParser:
    """Парсер различных форматов файлов с контактами"""
    
    @staticmethod
    def parse_txt_file(content: str, contact_type: str) -> Tuple[List[str], List[str]]:
        """Парсинг TXT файла"""
        valid_contacts = []
        invalid_contacts = []
        
        lines = content.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Пропускаем пустые строки и комментарии
            if not line or line.startswith('#'):
                continue
            
            # Разделяем по запятой, точке с запятой или табуляции
            contacts = [c.strip() for c in line.replace(',', ';').replace('\t', ';').split(';') if c.strip()]
            
            for contact in contacts:
                is_valid, result = FileParser._validate_contact(contact, contact_type)
                
                if is_valid:
                    valid_contacts.append(result)
                else:
                    invalid_contacts.append(f"Строка {line_num}: {contact} - {result}")
        
        return valid_contacts, invalid_contacts
    
    @staticmethod
    def parse_csv_file(content: str, contact_type: str) -> Tuple[List[Dict], List[str]]:
        """Парсинг CSV файла"""
        valid_contacts = []
        invalid_contacts = []
        
        try:
            # Определяем разделитель
            delimiters = [',', ';', '\t']
            delimiter = ','
            
            for delim in delimiters:
                if delim in content:
                    delimiter = delim
                    break
            
            lines = content.strip().split('\n')
            reader = csv.DictReader(lines, delimiter=delimiter)
            
            for row_num, row in enumerate(reader, 2):  # Начинаем с 2 (учитывая заголовок)
                # Ищем колонку с контактами
                contact_value = None
                
                # Возможные названия колонок
                contact_columns = {
                    'email': ['email', 'e-mail', 'mail', 'почта', 'электронная почта'],
                    'phone': ['phone', 'telephone', 'tel', 'mobile', 'телефон', 'номер'],
                    'telegram': ['telegram', 'tg', 'username', 'пользователь']
                }
                
                for key, value in row.items():
                    if not key or not value:
                        continue
                    
                    key_lower = key.lower().strip()
                    
                    # Проверяем соответствие типу контакта
                    if contact_type in contact_columns:
                        if any(col in key_lower for col in contact_columns[contact_type]):
                            contact_value = value.strip()
                            break
                    
                    # Если конкретная колонка не найдена, берем первую непустую
                    if not contact_value and value.strip():
                        contact_value = value.strip()
                
                if contact_value:
                    is_valid, result = FileParser._validate_contact(contact_value, contact_type)
                    
                    if is_valid:
                        contact_data = {
                            'identifier': result,
                            'first_name': row.get('first_name', row.get('имя', '')),
                            'last_name': row.get('last_name', row.get('фамилия', '')),
                            'metadata': {k: v for k, v in row.items() if v}
                        }
                        valid_contacts.append(contact_data)
                    else:
                        invalid_contacts.append(f"Строка {row_num}: {contact_value} - {result}")
        
        except Exception as e:
            logger.error(f"Error parsing CSV: {e}")
            invalid_contacts.append(f"Ошибка парсинга CSV: {str(e)}")
        
        return valid_contacts, invalid_contacts
    
    @staticmethod
    def parse_excel_file(file_path: str, contact_type: str) -> Tuple[List[Dict], List[str]]:
        """Парсинг Excel файла"""
        valid_contacts = []
        invalid_contacts = []
        
        try:
            workbook = openpyxl.load_workbook(file_path)
            sheet = workbook.active
            
            # Получаем заголовки
            headers = []
            for cell in sheet[1]:
                headers.append(cell.value.lower().strip() if cell.value else '')
            
            # Находим индекс колонки с контактами
            contact_col_index = None
            contact_columns = {
                'email': ['email', 'e-mail', 'mail', 'почта'],
                'phone': ['phone', 'telephone', 'tel', 'mobile', 'телефон'],
                'telegram': ['telegram', 'tg', 'username', 'пользователь']
            }
            
            for i, header in enumerate(headers):
                if contact_type in contact_columns:
                    if any(col in header for col in contact_columns[contact_type]):
                        contact_col_index = i
                        break
            
            # Если колонка не найдена, используем первую
            if contact_col_index is None:
                contact_col_index = 0
            
            # Парсим данные
            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
                if row_num > 10000:  # Ограничение на количество строк
                    break
                
                if len(row) > contact_col_index and row[contact_col_index]:
                    contact_value = str(row[contact_col_index]).strip()
                    
                    is_valid, result = FileParser._validate_contact(contact_value, contact_type)
                    
                    if is_valid:
                        contact_data = {
                            'identifier': result,
                            'first_name': str(row[1]).strip() if len(row) > 1 and row[1] else '',
                            'last_name': str(row[2]).strip() if len(row) > 2 and row[2] else '',
                            'metadata': {}
                        }
                        valid_contacts.append(contact_data)
                    else:
                        invalid_contacts.append(f"Строка {row_num}: {contact_value} - {result}")
            
            workbook.close()
        
        except Exception as e:
            logger.error(f"Error parsing Excel: {e}")
            invalid_contacts.append(f"Ошибка парсинга Excel: {str(e)}")
        
        return valid_contacts, invalid_contacts
    
    @staticmethod
    def _validate_contact(contact: str, contact_type: str) -> Tuple[bool, str]:
        """Валидация контакта по типу"""
        if contact_type == "email":
            return validate_email_address(contact)
        elif contact_type == "phone":
            return validate_phone_number(contact)
        elif contact_type == "telegram":
            # Пробуем как username
            is_valid, result = validate_telegram_username(contact)
            if is_valid:
                return True, result
            # Если не username, пробуем как ID
            try:
                user_id = int(contact)
                return True, str(user_id)
            except ValueError:
                return False, "Неверный формат Telegram контакта"
        else:
            return True, contact