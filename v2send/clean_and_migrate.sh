#!/bin/bash

echo "🗑️ Очистка базы данных и применение миграций..."

# Останавливаем контейнеры
echo "⏹️ Остановка контейнеров..."
docker-compose down --remove-orphans

# Удаляем volumes с данными БД
echo "🗑️ Удаление данных БД..."
docker volume rm telegramsend_postgres_data 2>/dev/null || true
docker volume rm telegramsend_redis_data 2>/dev/null || true

# Запускаем только БД
echo "🚀 Запуск БД..."
docker-compose up -d postgres redis

# Ждем инициализации БД
echo "⏳ Ожидание готовности БД..."
sleep 10

# Применяем миграции
echo "🔄 Применение миграций..."
docker-compose run --rm bot alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✅ Миграции успешно применены!"
    
    # Запускаем все сервисы
    echo "🚀 Запуск всех сервисов..."
    docker-compose up -d
    
    echo "📋 Проверка статуса..."
    docker-compose ps
    
    echo "✅ Готово! Проверьте логи бота:"
    echo "docker-compose logs -f bot"
else
    echo "❌ Ошибка при применении миграций!"
    exit 1
fi