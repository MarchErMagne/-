#!/bin/bash

# Скрипт для запуска приложения

set -e

echo "🚀 Starting TelegramSender Pro..."

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "📝 Copying .env.example to .env..."
    cp .env.example .env
    echo "✅ Please edit .env file with your configuration before continuing"
    exit 1
fi

# Проверяем Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo "📥 Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed!"
    echo "📥 Please install Docker Compose first: https://docs.docker.com/compose/install/"
    exit 1
fi

# Создаем директории
echo "📁 Creating directories..."
mkdir -p uploads
mkdir -p logs

# Запускаем сервисы
echo "🐳 Starting Docker services..."
docker-compose up -d postgres redis

echo "⏳ Waiting for database to be ready..."
sleep 10

# Проверяем подключение к БД
echo "🔍 Checking database connection..."
docker-compose exec postgres pg_isready -U postgres -d telegram_sender || {
    echo "❌ Database connection failed!"
    exit 1
}

# Применяем миграции
echo "🗄️ Applying database migrations..."
docker-compose run --rm bot alembic upgrade head

# Запускаем все сервисы
echo "🚀 Starting all services..."
docker-compose up -d

echo "✅ TelegramSender Pro started successfully!"
echo ""
echo "📊 Service status:"
docker-compose ps

echo ""
echo "📝 Logs:"
echo "  View all logs: docker-compose logs -f"
echo "  View bot logs: docker-compose logs -f bot"
echo ""
echo "🛠️ Management:"
echo "  Stop: docker-compose down"
echo "  Restart: docker-compose restart"
echo "  Shell: docker-compose exec bot bash"
echo ""
echo "🌐 Bot should be running now. Check your Telegram bot!"