#!/usr/bin/env python3
"""
Скрипт для валидации .env файла
"""

import os
import sys
from pathlib import Path

def validate_env():
    """Проверяет наличие и корректность .env файла"""
    
    env_path = Path('.env')
    
    if not env_path.exists():
        print("❌ .env file not found!")
        print("📝 Please copy .env.example to .env and fill in your values")
        return False
    
    # Читаем .env файл
    env_vars = {}
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    
    # Обязательные переменные
    required_vars = [
        'BOT_TOKEN',
        'BOT_USERNAME',
        'DATABASE_URL',
        'REDIS_URL',
        'CELERY_BROKER_URL',
        'CELERY_RESULT_BACKEND'
    ]
    
    missing_vars = []
    invalid_vars = []
    
    print("🔍 Validating environment variables...")
    
    for var in required_vars:
        if var not in env_vars:
            missing_vars.append(var)
        elif not env_vars[var] or env_vars[var] == 'your_value_here':
            invalid_vars.append(var)
    
    # Проверяем формат BOT_TOKEN
    if 'BOT_TOKEN' in env_vars and env_vars['BOT_TOKEN']:
        token = env_vars['BOT_TOKEN']
        if not token.count(':') == 1 or len(token.split(':')[0]) < 8:
            invalid_vars.append('BOT_TOKEN (invalid format)')
    
    # Выводим результаты
    if missing_vars:
        print(f"❌ Missing required variables: {', '.join(missing_vars)}")
    
    if invalid_vars:
        print(f"⚠️  Invalid or placeholder values: {', '.join(invalid_vars)}")
    
    if not missing_vars and not invalid_vars:
        print("✅ All required environment variables are set!")
        return True
    
    print("\n📝 Please update your .env file with valid values")
    return False

def check_optional_services():
    """Проверяет опциональные сервисы"""
    print("\n🔧 Optional services configuration:")
    
    env_vars = {}
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    
    services = {
        'CryptoPay': ['CRYPTO_PAY_TOKEN', 'CRYPTO_WEBHOOK_SECRET'],
        'OpenAI': ['OPENAI_API_KEY'],
        'WhatsApp': ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN'],
        'SMS': ['SMS_API_KEY'],
        'Viber': ['VIBER_API_KEY']
    }
    
    for service, vars_needed in services.items():
        configured = all(
            var in env_vars and env_vars[var] and env_vars[var] != 'your_value_here'
            for var in vars_needed
        )
        
        status = "✅ Configured" if configured else "⚠️  Not configured"
        print(f"  {service}: {status}")
    
    print("\n💡 Optional services can be configured later")

if __name__ == "__main__":
    if validate_env():
        check_optional_services()
        print("\n🚀 Environment validation successful!")
        sys.exit(0)
    else:
        print("\n❌ Environment validation failed!")
        sys.exit(1)