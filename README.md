# Distributed Reviews & Ratings Platform

**Distributed Reviews & Ratings Platform** — розподілена високонавантажена платформа для збору, обробки та агрегації відгуків і призначених користувачем рейтингів.

Розроблено в рамках курсу **«Інженерія високонавантажених систем»**.

---

## 🏗 Архітектура проекту
- **Бекенд:** FastAPI, Clean Architecture / DDD, PostgreSQL 16 (UUIDv7, OCC), Redis 7, ARQ Worker
- **Інфраструктура:** Docker Compose, Nginx, automated PostgreSQL backup rotation
- **Менеджмент залежностей:** `uv`
- **Якість коду:** Ruff (linter/formatter), Mypy (strict type checking)

---

## 🚀 Швидкий старт (Docker Compose)

### 1. Налаштування оточення
```bash
cp .env.example .env
```

### 2. Запуск всієї інфраструктури
```bash
docker compose up -d --build
```
Після старту будуть запущені наступні сервіси:
- `rating_postgres` — реляційна база даних PostgreSQL 16
- `rating_redis` — розподілене кешування та черга фонових задач
- `rating_migrator` — автоматичне застосування міграцій Alembic та сідування SuperAdmin
- `rating_backend` — REST API сервіс на базі FastAPI (порт 8000)
- `rating_worker` — асинхронний фоновий воркер ARQ
- `rating_db_backup` — щоденне резервне копіювання БД з ротацією

### 3. Перевірка статусу
- Swagger UI документація: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Перевірка працездатності: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

---

## 💻 Локальна розробка (Backend)
```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python scripts/seed_superadmin.py
uv run uvicorn src.main:app --reload
```

---

## 🛡 Перевірка якості коду (Pre-commit)
```bash
uv run --directory backend pre-commit run --all-files
```
