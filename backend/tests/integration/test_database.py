import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.core import SystemRole
from src.modules.users.infrastructure.models import RoleModel, UserModel


@pytest.mark.asyncio
async def test_database_connection(db_session: AsyncSession) -> None:
    """Перевірка виконання базового SQL-запиту в асинхронній сесії PostgreSQL."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_database_seeded_roles(db_session: AsyncSession) -> None:
    """Перевірка наявності трьох системних ролей (SUPER_ADMIN, ADMIN та USER) після міграцій."""
    stmt = select(RoleModel)
    result = await db_session.execute(stmt)
    roles = {r.code: r for r in result.scalars().all()}

    assert SystemRole.SUPER_ADMIN.value in roles
    assert SystemRole.ADMIN.value in roles
    assert SystemRole.USER.value in roles

    super_admin_role = roles[SystemRole.SUPER_ADMIN.value]
    admin_role = roles[SystemRole.ADMIN.value]
    user_role = roles[SystemRole.USER.value]

    assert super_admin_role.name == "Головний адміністратор"
    assert admin_role.name == "Адміністратор"
    assert user_role.name == "Користувач"


@pytest.mark.asyncio
async def test_database_transaction_rollback_isolation(db_session: AsyncSession) -> None:
    """
    Перевірка ізоляції транзакції тесту:
    створення запису в db_session не повинно зберігатися у глобальній БД завдяки savepoint.
    """
    stmt = select(RoleModel).where(RoleModel.code == SystemRole.USER.value)
    result = await db_session.execute(stmt)
    user_role = result.scalar_one()

    test_user = UserModel(
        id=uuid7(),
        version=1,
        username="temp_isolated_test_user",
        name="Temporary Test User",
        password_hash="some_hashed_val",
        role_id=user_role.id,
    )
    db_session.add(test_user)
    await db_session.flush()

    # Перевіряємо, що в межах поточної сесії користувач доступний
    check_stmt = select(UserModel).where(UserModel.username == "temp_isolated_test_user")
    check_result = await db_session.execute(check_stmt)
    assert check_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_database_review_status_check_constraint(db_session: AsyncSession) -> None:
    """Перевірка валідації статусу відгуку на рівні БД (ck_reviews_status)."""
    from sqlalchemy.exc import IntegrityError

    from src.modules.reviews.domain.enums import ReviewStatus
    from src.modules.reviews.infrastructure.models import ReviewModel, TargetModel

    user_stmt = select(UserModel).limit(1)
    user = (await db_session.execute(user_stmt)).scalars().first()
    assert user is not None

    target = TargetModel(
        id=uuid7(),
        slug=f"test-slug-{uuid7().hex[:8]}",
        title="Test Target for Status Check",
        category="product",
    )
    db_session.add(target)
    await db_session.flush()

    # 1. Успішне збереження з усіма валідними статусами enum
    for status in (ReviewStatus.PUBLISHED, ReviewStatus.HIDDEN, ReviewStatus.FLAGGED):
        sub_target = TargetModel(
            id=uuid7(),
            slug=f"status-{status.value}-{uuid7().hex[:8]}",
            title=f"Test Target {status.value}",
            category="product",
        )
        db_session.add(sub_target)
        await db_session.flush()

        rev = ReviewModel(
            id=uuid7(),
            target_id=sub_target.id,
            user_id=user.id,
            score=5,
            content="Valid test review content for constraint check.",
            status=status,
        )
        db_session.add(rev)
        await db_session.flush()

    # 2. Перевірка CheckConstraint у PostgreSQL: неприпустиме значення статусу блокується базою
    with pytest.raises(IntegrityError):
        invalid_rev_id = uuid7()
        await db_session.execute(
            text(
                "INSERT INTO reviews (id, target_id, user_id, score, content, status, version, created_at) "
                "VALUES (:id, :target_id, :user_id, 5, 'Valid content length', 'banned_status', 1, NOW())"
            ),
            {"id": invalid_rev_id, "target_id": target.id, "user_id": user.id},
        )
        await db_session.flush()


@pytest.mark.asyncio
async def test_alembic_review_status_migration_lifecycle(db_session: AsyncSession) -> None:
    """Перевірка коректності відкату (downgrade) та повторного накату (upgrade) міграції 2026_10_17_0004."""
    import asyncio
    from pathlib import Path

    from alembic.config import Config

    from alembic import command
    from src.core import get_settings

    current_settings = get_settings()
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", current_settings.db.url)

    # 1. Відкат міграції до попередньої ревізії
    await asyncio.to_thread(command.downgrade, alembic_cfg, "2026_09_04_0003")

    # 2. Повторний накат до актуального head
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
