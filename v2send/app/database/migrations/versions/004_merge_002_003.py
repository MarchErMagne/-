# app/database/migrations/versions/004_merge_002_003.py
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# Уникальный ID новой ревизии
revision = "004_merge_002_003"
# Схлопываем ДВЕ головы (ровно как в вашем выводе heads)
down_revision = ("002", "003")
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Ничего не меняем схематически — просто объединяем ветки
    pass

def downgrade() -> None:
    # Откат merge необязателен
    pass
