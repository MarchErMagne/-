#!/bin/bash

# Полный установочный скрипт TelegramSender Pro

set -e

echo "🚀 TelegramSender Pro Installation Script"
echo "========================================"

# Проверка системы
check_system() {
    echo "🔍 Checking system requirements..."
    
    # Проверка ОС
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "✅ Linux detected"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "✅ macOS detected"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        echo "✅ Windows detected"
    else
        echo "⚠️  Unknown OS: $OSTYPE"
    fi
    
    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker is not installed!"
        echo "📥 Please install Docker first:"
        echo "   https://docs.docker.com/get-docker/"
        exit 1
    else
        echo "✅ Docker found: $(docker --version)"
    fi
    
    # Проверка Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose is not installed!"
        echo "📥 Please install Docker Compose first:"
        echo "   https://docs.docker.com/compose/install/"
        exit 1
    else
        echo "✅ Docker Compose found: $(docker-compose --version)"
    fi
    
    # Проверка места на диске
    available_space=$(df . | awk 'NR==2 {print $4}')
    if [[ $available_space -lt 5000000 ]]; then
        echo "⚠️  Low disk space. Recommended: 5GB+ available"
    else
        echo "✅ Sufficient disk space"
    fi
}

# Настройка проекта
setup_project() {
    echo ""
    echo "📁 Setting up project structure..."
    
    # Создаем необходимые директории
    mkdir -p uploads logs scripts
    
    # Создаем .gitkeep файлы
    touch uploads/.gitkeep logs/.gitkeep
    
    # Устанавливаем права
    chmod 755 uploads logs scripts
    
    echo "✅ Project structure created"
}

# Настройка конфигурации
setup_config() {
    echo ""
    echo "⚙️  Setting up configuration..."
    
    if [[ ! -f .env ]]; then
        if [[ -f .env.example ]]; then
            cp .env.example .env
            echo "✅ Created .env from .env.example"
        else
            echo "❌ .env.example not found!"
            return 1
        fi
    else
        echo "✅ .env file already exists"
    fi
    
    # Устанавливаем безопасные права для .env
    chmod 600 .env
    
    echo ""
    echo "📝 IMPORTANT: Please edit .env file with your configuration!"
    echo "   Required variables:"
    echo "   - BOT_TOKEN (from @BotFather)"
    echo "   - BOT_USERNAME (your bot username)"
    echo "   - CRYPTO_PAY_TOKEN (from @CryptoBot)"
    echo ""
    
    read -p "Press Enter to continue after editing .env file..."
}

# Валидация конфигурации
validate_config() {
    echo ""
    echo "🔍 Validating configuration..."
    
    if [[ -f scripts/validate_env.py ]]; then
        if python3 scripts/validate_env.py; then
            echo "✅ Configuration validation passed"
        else
            echo "❌ Configuration validation failed!"
            echo "Please check your .env file and try again"
            exit 1
        fi
    else
        echo "⚠️  Validation script not found, skipping..."
    fi
}

# Запуск сервисов
start_services() {
    echo ""
    echo "🐳 Starting Docker services..."
    
    # Останавливаем существующие контейнеры
    echo "Stopping existing containers..."
    docker-compose down 2>/dev/null || true
    
    # Собираем образы
    echo "Building Docker images..."
    docker-compose build
    
    # Запускаем базу данных и Redis
    echo "Starting database and Redis..."
    docker-compose up -d postgres redis
    
    # Ждем готовности БД
    echo "Waiting for database to be ready..."
    for i in {1..30}; do
        if docker-compose exec postgres pg_isready -U postgres -d telegram_sender &>/dev/null; then
            echo "✅ Database is ready"
            break
        fi
        echo "Waiting... ($i/30)"
        sleep 2
    done
    
    # Применяем миграции
    echo "Applying database migrations..."
    docker-compose run --rm bot alembic upgrade head
    
    # Запускаем все сервисы
    echo "Starting all services..."
    docker-compose up -d
    
    echo "✅ All services started!"
}

# Проверка работы
verify_installation() {
    echo ""
    echo "🔍 Verifying installation..."
    
    # Ждем запуска сервисов
    sleep 10
    
    # Проверяем статус контейнеров
    echo "Container status:"
    docker-compose ps
    
    # Проверяем health check
    echo ""
    echo "Checking health endpoint..."
    if curl -s http://localhost:8001/health &>/dev/null; then
        echo "✅ Health check passed"
    else
        echo "⚠️  Health check failed, but services might still be starting..."
    fi
}

# Финальные инструкции
show_final_instructions() {
    echo ""
    echo "🎉 Installation completed!"
    echo "========================"
    echo ""
    echo "📱 Your bot should now be running!"
    echo ""
    echo "🔧 Next steps:"
    echo "1. Find your bot in Telegram by username: @$(grep BOT_USERNAME .env | cut -d'=' -f2)"
    echo "2. Send /start to begin setup"
    echo "3. Configure senders in bot menu"
    echo "4. Upload contacts and create campaigns"
    echo ""
    echo "📊 Management commands:"
    echo "  View logs:    docker-compose logs -f bot"
    echo "  Restart:      docker-compose restart"
    echo "  Stop:         docker-compose down"
    echo "  Update:       git pull && docker-compose build && docker-compose up -d"
    echo ""
    echo "📚 Documentation:"
    echo "  Full guide:   cat INSTALLATION_GUIDE.md"
    echo "  Quick start:  cat QUICK_START.md"
    echo ""
    echo "🆘 Support:"
    echo "  Issues:       https://github.com/your-repo/telegram-sender-pro/issues"
    echo "  Logs:         docker-compose logs"
    echo ""
    echo "Happy sending! 🚀"
}

# Основная логика
main() {
    check_system
    setup_project
    setup_config
    validate_config
    start_services
    verify_installation
    show_final_instructions
}

# Обработка ошибок
handle_error() {
    echo ""
    echo "❌ Installation failed!"
    echo "Check the error messages above and try again."
    echo "For support, visit: https://github.com/your-repo/telegram-sender-pro/issues"
    exit 1
}

# Устанавливаем обработчик ошибок
trap handle_error ERR

# Запуск
main "$@"