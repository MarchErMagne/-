"""
Celery задачи для фоновой обработки
"""

from celery import Celery
from app.config import settings

# Создание Celery приложения
celery_app = Celery(
    'telegram_sender',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'app.tasks.campaigns',
        'app.tasks.notifications', 
        'app.tasks.cleanup'
    ]
)

# Конфигурация
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        'cleanup-old-logs': {
            'task': 'app.tasks.campaigns.cleanup_old_logs',
            'schedule': 24 * 60 * 60,  # Каждый день
        },
        'check-expiring-subscriptions': {
            'task': 'app.tasks.notifications.check_expiring_subscriptions',
            'schedule': 12 * 60 * 60,  # Каждые 12 часов
        },
        'deactivate-expired-subscriptions': {
            'task': 'app.tasks.notifications.deactivate_expired_subscriptions',
            'schedule': 60 * 60,  # Каждый час
        },
    }
)

__all__ = ['celery_app']