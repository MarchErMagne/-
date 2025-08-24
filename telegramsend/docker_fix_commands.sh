#!/bin/bash

# Команды для исправления проблемы с telegram_id

echo "🔧 Исправление проблемы с telegram_id..."

# 1. Остановка сервисов
echo "⏹️ Остановка сервисов..."
docker-compose down

# 2. Создание миграции (если еще не создана)
echo "📝 Создание миграции..."
docker-compose run --rm bot alembic revision --autogenerate -m "Fix telegram_id field type"

# 3. Применение миграции
echo "🔄 Применение миграции..."
docker-compose run --rm bot alembic upgrade head

# 4. Запуск сервисов
echo "🚀 Запуск сервисов..."
docker-compose up -d

# 5. Проверка логов
echo "📋 Проверка логов бота..."
docker-compose logs -f bot

echo "✅ Исправление завершено!"
echo ""
echo "📌 Что было исправлено:"
echo "   - Поле telegram_id изменено с INTEGER на BIGINT"
echo "   - Теперь поддерживаются большие Telegram ID (больше 2^31)"
echo "   - Исправлены декораторы для корректной работы с БД"
echo ""
echo "🔍 Для проверки статуса:"
echo "   docker-compose ps"
echo "   docker-compose logs bot"