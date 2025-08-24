"""
Celery задачи для фоновой обработки
"""

from .campaigns import celery as celery_app

__all__ = ['celery_app']