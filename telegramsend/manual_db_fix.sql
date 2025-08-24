-- Ручное исправление базы данных для изменения типа telegram_id

-- Подключитесь к БД через psql:
-- docker exec -it telegramsend-postgres-1 psql -U postgres -d telegram_sender

-- 1. Проверяем текущую структуру таблицы users
\d users;

-- 2. Если таблица существует, изменяем тип поля telegram_id
-- ВНИМАНИЕ: Это безопасно только если нет данных с большими telegram_id
ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT;

-- 3. Если возникает ошибка, нужно пересоздать таблицу:
-- Сначала создаем новую таблицу
CREATE TABLE users_new (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    language_code VARCHAR(10) DEFAULT 'ru',
    is_premium BOOLEAN DEFAULT FALSE,
    subscription_plan VARCHAR(50),
    subscription_expires TIMESTAMP,
    subscription_status subscriptionstatus DEFAULT 'EXPIRED',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Копируем данные (если есть)
INSERT INTO users_new SELECT * FROM users;

-- Удаляем старую таблицу
DROP TABLE users CASCADE;

-- Переименовываем новую таблицу
ALTER TABLE users_new RENAME TO users;

-- Пересоздаем индекс
CREATE UNIQUE INDEX ix_users_telegram_id ON users(telegram_id);

-- 4. Обновляем запись в alembic_version
UPDATE alembic_version SET version_num = '001';

-- 5. Проверяем результат
\d users;
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name = 'users' AND column_name = 'telegram_id';