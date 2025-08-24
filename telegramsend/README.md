# telegram_mass_sender (skeleton)

Каркас проекта по вашей структуре. Файлы — заглушки, замените их реальной логикой.

## Быстрый старт
```bash
cp .env.example .env  # если нужно
docker compose up --build
```

Структура:

- `app/main.py` — точка входа
- `app/config.py` — конфигурация из env
- `app/database/*` — SQLAlchemy + миграции Alembic
- `app/handlers/*` — хендлеры бота
- `app/services/*` — интеграции и сервисы
- `app/utils/*` — утилиты
- `app/tasks/*` — фоновые задачи (Celery)
- `uploads/` — загруженные файлы
