# Інструкції з внесення змін та стандарти Git (CONTRIBUTING)

Цей документ визначає стандарти Git-комітів, правила найменування гілок та регламент Pull Requests для проекту **Distributed Reviews & Ratings Platform**.

---

## 1. Стандарти Git-комітів (Conventional Commits)

У проекті використовується стандарт **Conventional Commits** англійською мовою.

### 1.1. Формат повідомлення коміту:
```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

* **Мова комітів:** Англійська (`en-US`).
* **Дієслова:** Наказовий спосіб теперішнього часу (`add`, `update`, `fix`, `refactor`, `remove`, `document` замість `added`/`adding`).
* **Регістр:** Повідомлення починається з малої літери, без крапки в кінці заголовка.

---

### 1.2. Дозволені типи (`type`):
* `feat`: Новий функціонал або ендпоінт.
* `fix`: Виправлення бага чи помилки.
* `docs`: Зміни в документації, гайдах або ADR (`docs(adr): ...`, `docs(backend): ...`, `docs(domain): ...`).
* `refactor`: Рефакторинг коду без зміни функціональності чи виправлення багів.
* `test`: Додавання або виправлення автотестів (`test(unit): ...`, `test(api): ...`).
* `chore`: Зміни конфігурацій, оновлення залежностей, налаштування інструментів розробки.
* `perf`: Зміни коду для підвищення швидкодії.
* `ci`: Зміни у пайплайнах CI/CD або GitHub Actions.

---

### 1.3. Скоупи (`scope`):
* `(backend)`, `(core)`, `(tasks)`, `(auth)`, `(users)`, `(targets)`, `(reviews)`, `(ratings)`, `(cache)`, `(db)`, `(deps)`, `(infra)`.

---

### 1.4. Приклади коректних комітів:
* `feat(reviews): add sentiment analysis background task`
* `feat(ratings): calculate bayesian weighted average on review create`
* `fix(auth): handle expired refresh token gracefully`
* `refactor(db): implement primary-replica session routing`
* `test(targets): add unit tests for rating calculation`
* `chore(deps): update fastapi and pydantic settings dependencies`

---

## 2. Правила роботи з гілками та Pull Requests

1. **Кастомні гілки:** Усі нові задачі розробляються в окремих гілках від актуального `main`:
   * `feature/<feature-name>` — для нового функціоналу.
   * `bugfix/<bug-name>` — для виправлення дефектів.
   * `docs/<docs-topic>` — для змін у документації та ADR.
   * `refactor/<refactoring-scope>` — для рефакторингу коду.
2. **Злиття через Pull Request:**
   * Злиття в гілку `main` відбувається виключно через Pull Request.
   * Обов'язкове успішне проходження лінтерів (`ruff`, `mypy`), автоформатування та автоматичних тестів (`pytest`).
   * Обов'язкове рев'ю коду перед злиттям.

---

## 3. Автоматизація якості коду (Pre-commit хуки)

Для запобігання потраплянню невідформатованого коду, помилок типізації або синтаксичних дефектів у репозиторій використовується **pre-commit** ([`.pre-commit-config.yaml`](./.pre-commit-config.yaml)).

### 3.1. Встановлення хуків у локальний Git:
Хуки встановлюються один раз після клонування репозиторію:
```bash
uv run --directory backend pre-commit install
```

### 3.2. Що перевіряється автоматично при кожному `git commit`:
1. **Санітарні перевірки проекту:**
   - Видалення зайвих пробілів (`trailing-whitespace`, за винятком `docs/domain/` та `storage/`).
   - Гарантія наявності порожнього рядка в кінці файлів (`end-of-file-fixer`).
   - Перевірка валідності синтаксису YAML-файлів (`check-yaml`).
   - Захист від випадкового коміту файлів розміром понад 1 МБ (`check-added-large-files`).
   - Захист від коміту невирішених конфліктних маркерів Git (`check-merge-conflict`).
2. **Перевірки бекенду (активуються виключно при модифікації коду в `backend/`):**
   - `ruff check --fix` — лінтинг з авто-виправленням помилок.
   - `ruff format` — форматування коду.
   - `mypy src tests` — сувора перевірка статичної типізації.

### 3.3. Ручний запуск на всіх файлах:
```bash
uv run --directory backend pre-commit run --all-files
```
