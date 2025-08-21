"""
TelegramSender Pro - Мультиплатформенная система массовых рассылок
"""

__version__ = "1.0.0"
__author__ = "TelegramSender Team"

# app/database/__init__.py
"""
Модуль для работы с базой данных
"""

from .database import get_db, get_redis, init_db, close_db
from .models import Base, User, Campaign, Contact, Sender

__all__ = [
    'get_db',
    'get_redis', 
    'init_db',
    'close_db',
    'Base',
    'User',
    'Campaign',
    'Contact',
    'Sender'
]