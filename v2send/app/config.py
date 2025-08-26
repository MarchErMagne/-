from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Bot
    BOT_TOKEN: str
    BOT_USERNAME: str
    
    # CryptoPay
    CRYPTO_PAY_TOKEN: str
    CRYPTO_WEBHOOK_SECRET: str
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    
    # WhatsApp
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    WHATSAPP_FROM: str = "whatsapp:+14155238886"
    
    # SMS
    SMS_API_KEY: Optional[str] = None
    SMS_API_URL: str = "https://api.sms.ru/sms/send"
    
    # Viber
    VIBER_API_KEY: Optional[str] = None
    VIBER_API_URL: str = "https://chatapi.viber.com/pa/send_message"
    
    # AI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    # DeepSeek
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    # App
    DEBUG: bool = False
    MAX_FILE_SIZE: int = 10485760  # 10MB
    UPLOAD_DIR: str = "uploads"
    WEBHOOK_HOST: Optional[str] = None
    WEBHOOK_PATH: str = "/webhook"
    
    # Subscription prices (USD cents)
    BASIC_PLAN_PRICE: int = 999    # $9.99
    PRO_PLAN_PRICE: int = 2999     # $29.99
    PREMIUM_PLAN_PRICE: int = 9999 # $99.99
    
    # Limits
    BASIC_SENDERS_LIMIT: int = 1
    PRO_SENDERS_LIMIT: int = 5
    PREMIUM_SENDERS_LIMIT: int = 50
    
    BASIC_CONTACTS_LIMIT: int = 1000
    PRO_CONTACTS_LIMIT: int = 10000
    PREMIUM_CONTACTS_LIMIT: int = 100000
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# Subscription plans
SUBSCRIPTION_PLANS = {
    "basic": {
        "name": "Basic",
        "price": settings.BASIC_PLAN_PRICE,
        "duration_days": 30,
        "senders_limit": settings.BASIC_SENDERS_LIMIT,
        "contacts_limit": settings.BASIC_CONTACTS_LIMIT,
        "features": ["1 отправитель", "1,000 контактов", "Базовая аналитика"]
    },
    "pro": {
        "name": "Pro",
        "price": settings.PRO_PLAN_PRICE,
        "duration_days": 30,
        "senders_limit": settings.PRO_SENDERS_LIMIT,
        "contacts_limit": settings.PRO_CONTACTS_LIMIT,
        "features": ["5 отправителей", "10,000 контактов", "Расширенная аналитика", "AI-ассистент"]
    },
    "premium": {
        "name": "Premium",
        "price": settings.PREMIUM_PLAN_PRICE,
        "duration_days": 30,
        "senders_limit": settings.PREMIUM_SENDERS_LIMIT,
        "contacts_limit": settings.PREMIUM_CONTACTS_LIMIT,
        "features": ["50 отправителей", "100,000 контактов", "Полная аналитика", "AI-ассистент", "Приоритетная поддержка"]
    }
}