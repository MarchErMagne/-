.PHONY: help build up down logs shell db-migrate db-upgrade clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build Docker containers
	docker-compose build

up: ## Start all services
	docker-compose up -d

down: ## Stop all services
	docker-compose down

logs: ## Show logs
	docker-compose logs -f

shell: ## Open shell in bot container
	docker-compose exec bot bash

db-migrate: ## Create new migration
	docker-compose exec bot alembic revision --autogenerate -m "$(MESSAGE)"

db-upgrade: ## Apply migrations
	docker-compose exec bot alembic upgrade head

clean: ## Clean up Docker resources
	docker-compose down -v
	docker system prune -f

dev-setup: ## Setup development environment
	cp .env.example .env
	echo "Please edit .env file with your configuration"

install: ## Install Python dependencies locally
	pip install -r requirements.txt

test: ## Run tests
	docker-compose exec bot python -m pytest

restart: ## Restart all services
	docker-compose restart

restart-bot: ## Restart only bot service
	docker-compose restart bot

restart-celery: ## Restart celery services
	docker-compose restart celery_worker celery_beat

status: ## Show status of all services
	docker-compose ps

backup: ## Backup database
	docker-compose exec postgres pg_dump -U postgres telegram_sender > backup_$(shell date +%Y%m%d_%H%M%S).sql

restore: ## Restore database from backup (usage: make restore FILE=backup.sql)
	docker-compose exec -T postgres psql -U postgres telegram_sender < $(FILE)