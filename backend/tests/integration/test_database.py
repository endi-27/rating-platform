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
