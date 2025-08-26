import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiohttp.web_app import Application

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database.database import init_db, close_db, redis_client
from app.handlers import start, subscription, senders, campaigns, contacts, analytics, admin, ai_assistant
from app.services.crypto_pay import setup_crypto_webhooks

# Настройка логирования
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/bot.log') if os.path.exists('logs') else logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=settings.BOT_TOKEN)
storage = RedisStorage(redis=redis_client)
dp = Dispatcher(storage=storage)

async def on_startup():
    """Запуск бота"""
    logger.info("Starting TelegramSender Pro...")
    
    try:
        # Инициализация БД
        await init_db()
        logger.info("Database initialized")
        
        # Настройка webhook если указан хост
        if settings.WEBHOOK_HOST:
            webhook_url = f"{settings.WEBHOOK_HOST}{settings.WEBHOOK_PATH}"
            await bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to {webhook_url}")
        else:
            await bot.delete_webhook()
            logger.info("Webhook disabled, using polling")
        
        # Проверяем бота
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username} ({bot_info.first_name})")
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

async def on_shutdown():
    """Остановка бота"""
    logger.info("Shutting down TelegramSender Pro...")
    
    try:
        # Закрытие соединений
        await close_db()
        await bot.session.close()
        logger.info("Bot stopped gracefully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    # Подключаем роутеры в правильном порядке
    dp.include_router(admin.router)        # Админ команды первыми
    dp.include_router(start.router)        # Стартовые команды
    dp.include_router(subscription.router) # Подписки
    dp.include_router(senders.router)      # Отправители
    dp.include_router(campaigns.router)    # Кампании
    dp.include_router(contacts.router)     # Контакты
    dp.include_router(analytics.router)    # Аналитика
    dp.include_router(ai_assistant.router) # AI ассистент
    
    logger.info("All handlers registered")

async def create_app() -> Application:
    """Создание web приложения"""
    app = web.Application()
    
    # Настройка webhook для бота
    if settings.WEBHOOK_HOST:
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        ).register(app, path=settings.WEBHOOK_PATH)
        logger.info("Webhook handler registered")
    
    # Настройка CryptoPay webhook
    try:
        setup_crypto_webhooks(app)
        logger.info("CryptoPay webhooks configured")
    except Exception as e:
        logger.warning(f"Failed to setup CryptoPay webhooks: {e}")
    
    # Health check endpoint
    async def health_check(request):
        return web.json_response({
            "status": "ok", 
            "service": "TelegramSender Pro",
            "version": "1.0.0"
        })
    
    app.router.add_get("/health", health_check)
    
    return app

async def main():
    """Главная функция"""
    try:
        # Регистрируем обработчики
        register_handlers(dp)
        
        # Настройка startup/shutdown
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        if settings.WEBHOOK_HOST:
            # Webhook режим
            logger.info("Starting in webhook mode")
            app = await create_app()
            setup_application(app, dp, bot=bot)
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=8000)
            await site.start()
            
            logger.info("Webhook server started on port 8000")
            
            # Ждем завершения
            try:
                await asyncio.Future()  # Run forever
            finally:
                await runner.cleanup()
        else:
            # Polling режим
            logger.info("Starting in polling mode")
            await on_startup()
            try:
                await dp.start_polling(bot, skip_updates=True)
            finally:
                await on_shutdown()
                
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)