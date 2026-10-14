# AGENTS.md — Інструкції для AI-агентів (Distributed Reviews & Ratings Platform)

Цей документ є верховним регламентом (конституцією) репозиторію **Distributed Reviews & Ratings Platform**: глобальні інваріанти, розподілені контракти та стандарти для AI-асистентів. Деталі розробки бекенду — у [`backend/AGENTS.md`](./backend/AGENTS.md).

---

## 1. Структура проєкту

* `backend/` — Python 3.12+ / FastAPI / PostgreSQL 16 / SQLAlchemy 2.0 async / Redis 7 / ARQ → [`backend/AGENTS.md`](./backend/AGENTS.md).
* `nginx/` — Реверс-проксі та конфігурація балансування навантаження для розподіленої системи (ЛР №3).
* Інфраструктура кореня: `logs/`, `storage/`, `backups/`, `scripts/`, `docker-compose.yaml`, `.env*`.
* `labs/` — Вимоги та завдання до 10 лабораторних робіт курсу «Інженерія високонавантажених систем».

---

## 2. Guardrails (Захисні бар'єри)

1. **Термінологія** — суворе дотримання єдиної мови домену (Ubiquitous Language):
   * `Target` — об'єкт рейтингування (товар, послуга, заклад, фільм тощо).
   * `Review` — текстовий відгук користувача з оцінкою від 1 до 5 зірок.
   * `Rating` — агреговані статистичні показники об'єкта (середній бал, кількість відгуків, розподіл оцінок).
   * `User`, `Role`, `Permission` — сутності автентифікації та RBAC.
2. **Діаграми** — виключно Mermaid (`flowchart`, `sequenceDiagram`, `erDiagram`); ASCII-псевдографіка заборонена.
3. **Strict No-Proxy / SSOT:** при переносі або винесенні коду старі файли-прошарки та транзитні реекспорти повністю видаляються; споживачі одразу імпортують з нового канонічного місця.
4. **Ізоляція БД:** Робоча база даних `rating_db` ніколи не використовується для автоматичних тестів; тести запускаються виключно проти виділеної тестової бази `rating_test_db`.

---

## 3. Наскрізні контракти розподіленої платформи

* **OpenAPI 3.1 & Schema First:** Ендпоінти описуються з явними моделями Pydantic v2 `Annotated[T, Field(...)]`, метаданими безпеки `x-requires-auth`, `x-required-permission` та повною типізацією помилок.
* **Cookie-only Auth:** HttpOnly `access_token` та `refresh_token` з прапорцем `SameSite=Lax/Strict`; сувора заборона зберігання токенів у `localStorage` / `sessionStorage`. На `HTTP 401 Unauthorized` — авто-ротація через `POST /api/v1/auth/refresh`.
* **Діагностика розподіленої системи (ЛР №2, ЛР №3):** Кожна HTTP-відповідь супроводжується заголовками:
  * `X-Instance-ID` — ідентифікатор екземпляра бекенду, який обробив запит.
  * `X-Process-Time-Ms` — точний час обробки запиту у мілісекундах.
  * Підтримка симуляції асиметричної затримки через заголовок `X-Simulate-Latency-Ms` або конфігурацію `APP_CONFIG__SIMULATE_LATENCY_MS` для тестування алгоритмів балансування.
* **Розподілений кеш та Circuit Breaker (ЛР №4, ЛР №8):**
  * Заголовок `X-Cache` зі значеннями `HIT`, `MISS`, або `FALLBACK`.
  * При збої або недоступності Redis бекенд не падає з 500 помилкою, а прозоро читає дані з БД із заголовком `X-Cache: FALLBACK`.
* **Маршрутизація Read/Write сесій БД (ЛР №6):**
  * `QueryService` (читання) отримує сесію через `operation="read"` (підготовка до читання з Read Replica).
  * Командні Use Cases (запис) отримують сесію через `operation="write"` (Primary node).
* **Шардинг та партиціонування (ЛР №7):**
  * Будь-які запити до відгуків або рейтингів мають враховувати `shard_key=target_id`. Заборонено безфільтрові вибірки по всій таблиці відгуків.
* **Оптимістичне блокування (OCC) (ЛР №8):**
  * Усі змінювані ресурси мають поле `version` та перевіряють його при оновленні; конфлікт версій повертає `HTTP 409 Conflict` (`OPTIMISTIC_LOCK_CONFLICT`).
* **Сортування та фільтрація:** Стандартизований синтаксис `?sort=-created_at,score` тільки за дозволеними полями через `sort_dependency`.

---

## 4. Делегування та виконання регламентів

* **Backend:** Детальна конституція бекенду — [`backend/AGENTS.md`](./backend/AGENTS.md); регламент [`.agents/rules/backend.md`](./.agents/rules/backend.md) застосовується автоматично до всіх змін у `backend/**`.

---

## 5. Регламент Git та версіонування

Conventional Commits (`<type>(<scope>): <subject>`) англійською мовою згідно з [`CONTRIBUTING.md`](./CONTRIBUTING.md):
* `feat(reviews): add sentiment analysis background task`
* `feat(ratings): calculate bayesian weighted average on review create`
* `fix(auth): handle expired refresh token gracefully`
* `refactor(db): implement primary-replica session routing`
* `test(targets): add unit tests for rating calculation`

---

## 6. Graphify

Для навігації по кодовій базі та аналізу впливу змін (impact analysis) використовувати `graphify`. Будь-які неавторизовані сторонні інструменти індексування заборонені.
