.PHONY: test test-cov lint lint-fix format format-check typecheck pre-commit check up down logs migrate test-docker check-docker help

help:
	@echo "Rating Platform — Доступні команди:"
	@echo "  make up           - Збірка та запуск усіх контейнерів у фоні"
	@echo "  make down         - Зупинка контейнерів"
	@echo "  make logs         - Перегляд логів контейнерів у реальному часі"
	@echo "  make test         - Запуск усіх тестів через uv (pytest)"
	@echo "  make test-docker  - Запуск усіх тестів всередині ізольованого Docker-контейнера"
	@echo "  make test-cov     - Запуск тестів з покриттям коду (coverage)"
	@echo "  make lint         - Перевірка коду лінтером (ruff check)"
	@echo "  make lint-fix     - Автоматичне виправлення помилок лінтера"
	@echo "  make format       - Форматування коду (ruff format)"
	@echo "  make format-check - Перевірка форматування коду"
	@echo "  make typecheck    - Статична типізація (mypy)"
	@echo "  make pre-commit   - Запуск хуків pre-commit"
	@echo "  make check        - Повний прогін локальних перевірок (lint, format, typecheck, test, pre-commit)"
	@echo "  make check-docker - Повний прогін перевірок у чистому Docker-середовищі"
	@echo "  make migrate      - Застосування Alembic міграцій"

test:
	uv run --directory backend pytest -v

test-docker:
	docker run --rm --network rating_rating_network -e APP_CONFIG__DB__HOST=postgres -e APP_CONFIG__REDIS__HOST=redis -e APP_CONFIG__ENVIRONMENT=test -v $(CURDIR)/backend/.env.test:/app/.env.test:ro -v $(CURDIR)/backend/tests:/app/tests:ro -v $(CURDIR)/backend/src:/app/src:ro -v $(CURDIR)/backend/alembic:/app/alembic:ro rating-test pytest -v

test-cov:
	uv run --directory backend pytest --cov=src --cov-report=term-missing

lint:
	uv run --directory backend ruff check .

lint-fix:
	uv run --directory backend ruff check --fix .

format:
	uv run --directory backend ruff format .

format-check:
	uv run --directory backend ruff format --check .

typecheck:
	uv run --directory backend mypy

pre-commit:
	pre-commit run --all-files

check: lint format-check typecheck test pre-commit

check-docker:
	docker run --rm -v $(CURDIR)/backend/tests:/app/tests:ro -v $(CURDIR)/backend/src:/app/src:ro -v $(CURDIR)/backend/alembic:/app/alembic:ro -v $(CURDIR)/backend/scripts:/app/scripts:ro rating-test ruff check .
	docker run --rm -v $(CURDIR)/backend/tests:/app/tests:ro -v $(CURDIR)/backend/src:/app/src:ro -v $(CURDIR)/backend/alembic:/app/alembic:ro -v $(CURDIR)/backend/scripts:/app/scripts:ro rating-test ruff format --check .
	docker run --rm -v $(CURDIR)/backend/pyproject.toml:/app/pyproject.toml:ro -v $(CURDIR)/backend/tests:/app/tests:ro -v $(CURDIR)/backend/src:/app/src:ro -v $(CURDIR)/backend/scripts:/app/scripts:ro rating-test mypy
	$(MAKE) test-docker
	docker run --rm -v $(CURDIR):/workspace:z -w /workspace rating-test sh -c "git config --global --add safe.directory /workspace && pre-commit run --all-files"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec backend python -m alembic upgrade head
