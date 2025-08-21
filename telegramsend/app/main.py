import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web, web_middlewares
from aiohttp.web_app import Application
from app.config import settings
from app.database.database import init_db, close_db, redis_client
from app.handlers import start, subscription, senders, campaigns, contacts, analytics, admin, ai_assistant
from app.services.crypto_pay import setup_crypto_webhooks
import structlog

# Настройка логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Инициализация бота и диспетчера
bot = Bot(token=settings.BOT_TOKEN)
storage = RedisStorage(redis=redis_client)
dp = Dispatcher(storage=storage)

async def on_startup():
    """Запуск бота"""
    logger.info("Starting bot...")
    
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
        logger.info("Webhook disabled")
    
    logger.info("Bot started successfully")

async def on_shutdown():
    """Остановка бота"""
    logger.info("Shutting down bot...")
    
    # Закрытие соединений
    await close_db()
    await bot.session.close()
    
    logger.info("Bot stopped")

def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    # Подключаем роутеры
    dp.include_router(start.router)
    dp.include_router(subscription.router)
    dp.include_router(senders.router)
    dp.include_router(campaigns.router)
    dp.include_router(contacts.router)
    dp.include_router(analytics.router)
    dp.include_router(admin.router)
    dp.include_router(ai_assistant.router)

async def create_app() -> Application:
    """Создание web приложения"""
    app = web.Application()
    
    # Настройка webhook для бота
    if settings.WEBHOOK_HOST:
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        ).register(app, path=settings.WEBHOOK_PATH)
    
    # Настройка CryptoPay webhook
    setup_crypto_webhooks(app)
    
    # Health check endpoint
    async def health_check(request):
        return web.json_response({"status": "ok"})
    
    app.router.add_get("/health", health_check)
    
    return app

async def main():
    """Главная функция"""
    # Регистрируем обработчики
    register_handlers(dp)
    
    # Настройка startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    if settings.WEBHOOK_HOST:
        # Webhook режим
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
        await on_startup()
        try:
            await dp.start_polling(bot)
        finally:
            await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())