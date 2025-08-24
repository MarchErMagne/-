# Просто экспортируем celery из campaigns
from app.tasks.campaigns import celery

__all__ = ['celery']