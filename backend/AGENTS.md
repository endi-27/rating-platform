# backend/AGENTS.md — Архітектурна конституція бекенду

Цей документ є головним архітектурним та інженерним стандартом для розробки бекенду платформи **Distributed Reviews & Ratings Platform** (`backend/`).
Будь-який код, що додається або модифікується, **зобов'язаний** відповідати цим стандартам та 17 обов'язковим інваріантам.

---

## 1. Архітектурні шари (Clean DDD + Hexagonal)

Кожен бізнес-модуль у `src/modules/<module_name>/` структурований за чіткими шарами:

```
src/modules/<module_name>/
├── domain/                  # Чисті доменні сутності, Value Objects, винятки, доменні події
│   ├── entities.py          # Rich Domain моделі з інкапсульованими методами мутації
│   ├── exceptions.py        # Специфічні доменні помилки
│   └── value_objects.py     # Незмінні Value Objects (наприклад, RatingScore від 1 до 5)
├── application/             # Use Cases / Application Services, DTO, порти репозиторіїв
│   ├── use_cases/           # Командні Use Cases (Write-side, транзакційні мутації)
│   ├── queries/             # Query Services (Read-side, швидкі проекції без агрегатів)
│   └── dto/                 # Внутрішні DTO
├── infrastructure/          # Реалізація портів, ORM-моделі SQLAlchemy, репозиторії
│   ├── models.py            # SQLAlchemy Declarative моделі (lazy="raise", version)
│   └── repositories.py      # Реалізація репозиторіїв через AsyncSession
├── api/                     # HTTP-роутери, схеми Pydantic v2, залежності FastAPI
│   ├── router.py            # Ендпоінти модуля
│   └── schemas.py           # DTO валідації запитів/відповідей (Annotated[T, Field(...)])
└── public.py                # ЄДИНИЙ публічний інтерфейс модуля для інших модулів платформи
```

---

## 2. 17 Обов'язкових архітектурних інваріантів у коді

### Інваріант 1: Заборона міжмодульних імпортів у Write-пайплайні
* ❌ Заборонено імпортувати моделі або репозиторії іншого модуля напряму.
* ✅ Взаємодія між модулями відбувається виключно через `PublicGateway` (`from src.modules.users.public import UsersPublicGateway`).
* *Виняток:* `QueryService` для оптимізованих SQL `SELECT / JOIN` має право імпортувати чужі ORM-моделі на рівні інфраструктури.

### Інваріант 2: Rich Domain сутності
Сутності не є анемічними структурами даних. Валідація та зміна стану інкапсульовані всередині методів агрегатів:

```python
class Review:
    def __init__(self, id: UUID, target_id: UUID, user_id: UUID, score: int, text: str, ...) -> None:
        if not (1 <= score <= 5):
            raise InvalidRatingScoreError("Оцінка повинна бути цілим числом від 1 до 5.")
        self.id = id
        self.target_id = target_id
        self.user_id = user_id
        self.score = score
        self.text = text

    def update_content(self, score: int, text: str) -> None:
        if not (1 <= score <= 5):
            raise InvalidRatingScoreError("Оцінка повинна бути цілим числом від 1 до 5.")
        self.score = score
        self.text = text
```

### Інваріант 3: Обов'язкове `lazy="raise"` у SQLAlchemy
Усі зв'язки `relationship()` зобов'язані явно вказувати `lazy="raise"` для запобігання помилкам `MissingGreenlet` в асинхронному I/O:

```python
class ReviewModel(Base):
    __tablename__ = "reviews"

    target_id: Mapped[UUID] = mapped_column(ForeignKey("targets.id"), nullable=False)
    target: Mapped["TargetModel"] = relationship(lazy="raise")
```

### Інваріант 4: QueryService тільки для читання (CQRS)
Класи `QueryService` використовуються виключно для читання даних, побудови проекцій, DTO та швидкої віддачі в API. Вони не містять методів мутації та не роблять комітів.

### Інваріант 5: Контроль транзакцій (`uow.commit()`)
* Викликати `await uow.commit()` має право **виключно кореневий Use Case**.
* Доменні сутності, репозиторії, допоміжні функції та HTTP-роутери **ніколи** не роблять `commit()`.
* При виклику зовнішніх шлюзів (`PublicGateway`) у шлюз передається `external_uow=uow` для збереження єдиної атомарної транзакції (ACID).

### Інваріант 6: Розподіл подій та шлюзів
* Критичні міжмодульні мутації виконуються синхронно через `PublicGateway` в межах спільної UoW транзакції.
* `AsyncEventBus` використовується тільки для побічних ефектів: інвалідації кешу Redis, постановки задач у воркер ARQ.

### Інваріант 7: Логування тільки через Loguru
```python
from loguru import logger  # ✅ Обов'язково
# ❌ print(...) або import logging заборонені
```

### Інваріант 8: Повне оновлення через PUT (Full Update)
* Ендпоінти `PUT` замінюють стан ресурсу повністю. Клієнт передає всі обов'язкові поля.
* Заборонено використання `exclude_unset=True` у PUT-запитах.
* Точкові модифікації оформлюються через `PATCH`.

### Інваріант 9: Оптимістичне блокування (OCC) через `version`
Усі змінювані сутності захищені від втрати оновлень (lost updates):

```python
class TargetModel(Base):
    __tablename__ = "targets"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __mapper_args__ = {
        "version_id_col": version,
    }
```
При оновленні клієнт зобов'язаний передати очікувану версію `version`. Якщо версія в базі змінилася іншим запитом, сервіс повертає `HTTP 409 Conflict` (`OPTIMISTIC_LOCK_CONFLICT`).

### Інваріант 10: Системні поля сутностей
Кожна персистентна сутність має стандартний набір полів:
* `id: Mapped[UUID]` — UUIDv7 для збереження порядку за часом у B-Tree індексах.
* `version: Mapped[int]` — версія OCC.
* `created_at: Mapped[datetime]` — час створення (UTC timestamptz).
* `updated_at: Mapped[datetime | None]` — час останнього оновлення (UTC timestamptz | None).
* `deleted_at: Mapped[datetime | None]` — мітка часу для Soft Delete.

### Інваріант 11: Розподіл Soft Delete та Hard Delete
* `DELETE /api/v1/reviews/{id}` — фізичне видалення рядка з БД (Hard Delete).
* `PATCH /api/v1/reviews/{id}/soft-delete` — виставляє `deleted_at = now_utc()`.
* `PATCH /api/v1/reviews/{id}/restore` — повертає `deleted_at = None`.

### Інваріант 12: Стандарти Pydantic v2
Поля описуються виключно через `Annotated[T, Field(...)]`:

```python
class CreateReviewDto(BaseModel):
    score: Annotated[int, Field(ge=1, le=5, description="Оцінка від 1 до 5")]
    text: Annotated[str, Field(min_length=5, max_length=5000, description="Текст відгуку")]
```

### Інваріант 13: Конфігурація через `APP_CONFIG__`
Всі змінні середовища проходять через `Settings` у `src/core/config.py` з префіксом `APP_CONFIG__` та подвійним підкресленням для вкладених структур.

### Інваріант 14: Маршрутизація сесій Primary / Replica (ЛР №6)
* Усі сервіси читання (`QueryService`) зобов'язані отримувати сесію через `operation="read"`:
  ```python
  async with db_router.get_session(operation="read") as session:
      ...
  ```
* Усі сервіси модифікації (`Use Cases`) отримують транзакційну сесію через `operation="write"`.

### Інваріант 15: Шардинг та партиціонування за `target_id` (ЛР №7)
* Усі операції пошуку, створення та агрегації відгуків мають приймати `target_id` (Shard Key).
* Заборонені безфільтрові `SELECT * FROM reviews` по всій таблиці, щоб запобігти деградації запитів при горизонтальному масштабуванні БД.

### Інваріант 16: Розподілений кеш та Circuit Breaker (ЛР №4, ЛР №8)
* Читання рейтингу об'єкта реалізується через Cache-Aside з TTL.
* При недоступності Redis бекенд не повертає HTTP 500, а прозоро читає з бази та виставляє заголовок `X-Cache: FALLBACK`.

### Інваріант 17: Ізоляція тестової бази даних (`rating_test_db`)
* Усі автоматичні тести виконуються виключно в базі `rating_test_db` (`.env.test`).
* Транзакції тестів ізольовані через `create_savepoint` та автоматично відкочуються після кожного тесту.
* Усі консольні команди запускаються виключно через `uv run --directory backend ...`.

---

## 3. Чек-лист перед завершенням роботи над задачею

1. [ ] Усі імпорти між модулями йдуть через `public.py` (крім Read-side SQL JOIN у `QueryService`).
2. [ ] Доменні мутації та правила валідації інкапсульовані в методах агрегатів.
3. [ ] Усі ORM `relationship` мають `lazy="raise"`.
4. [ ] `uow.commit()` викликається виключно в кореневому Use Case.
5. [ ] Змінювані сутності мають поле `version` та коректно обробляють конфлікти OCC (`HTTP 409 Conflict`).
6. [ ] Моделі Pydantic v2 описані через `Annotated[T, Field(...)]`.
7. [ ] Запити до відгуків враховують `target_id` (Shard Key).
8. [ ] Сесії БД розділені: `operation="read"` для QueryService та `operation="write"` для Use Cases.
9. [ ] Лінтер `uv run --directory backend ruff check .` повертає 0 помилок.
10. [ ] Форматер `uv run --directory backend ruff format --check .` повертає 0 помилок.
11. [ ] Перевірка типів `uv run --directory backend mypy src` повертає 0 помилок у строгому режимі.
12. [ ] Автотести `uv run --directory backend pytest` проходять на 100% у виділеній `rating_test_db`.
