#!/bin/bash

# Скрипт для настройки прав доступа

echo "🔧 Setting up permissions..."

# Создаем необходимые директории
mkdir -p uploads logs scripts

# Устанавливаем права на выполнение для скриптов
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x scripts/*.py 2>/dev/null || true

# Права на директории
chmod 755 uploads logs

# Права на конфигурационные файлы
chmod 644 .env.example 2>/dev/null || true
chmod 644 alembic.ini 2>/dev/null || true
chmod 644 docker-compose.yml 2>/dev/null || true
chmod 644 Dockerfile 2>/dev/null || true
chmod 644 requirements.txt 2>/dev/null || true

# Если .env существует, устанавливаем более строгие права
if [ -f .env ]; then
    chmod 600 .env
    echo "✅ Set secure permissions for .env file"
fi

echo "✅ Permissions setup completed!"