# Distributed Reviews & Ratings Platform Backend

Бекенд-сервіс розподіленої платформи збору та агрегації відгуків і призначених користувачем рейтингів.

## Технологічний стек
- **Python:** 3.12+
- **Фреймворк:** FastAPI (asyncio)
- **ORM & DB:** SQLAlchemy 2.0 (async), Alembic, PostgreSQL 16
- **Кешування та фонові задачі:** Redis 7, ARQ Worker
- **Менеджер пакетів:** uv
- **Лінтер та форматування:** Ruff
- **Типізація:** Mypy (strict)

## Швидкий запуск
```bash
# Встановлення залежностей
uv sync

# Застосування міграцій
uv run alembic upgrade head

# Сідування початкового супер-адміністратора
uv run python scripts/seed_superadmin.py

# Запуск dev-сервера
uv run uvicorn src.main:app --reload --port 8000
```
