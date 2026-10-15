from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.api import get_read_db_session, get_uow
from src.core import (
    IUnitOfWork,
    SystemRole,
    create_access_token,
    default_password_hasher,
    get_db_session,
    settings,
)
from src.main import app
from src.modules.users.infrastructure.models import (
    PermissionModel,
    RoleModel,
    UserModel,
    UserPermissionModel,
)
from tests.unit.fakes import FakeUnitOfWork


class ApiTestClient(AsyncClient):
    """
    Кастомний AsyncClient для тестів, який запобігає появі DeprecationWarning
    від httpx 0.28+ через передачу per-request аргументу `cookies=<...>`.
    Автоматично транслює `cookies` у стандартний HTTP-заголовок `Cookie`.
    """

    async def request(self, method: str, url: Any, **kwargs: Any) -> Any:
        cookies = kwargs.pop("cookies", None)
        if cookies:
            headers = dict(kwargs.pop("headers", {}) or {})
            items = cookies.items() if hasattr(cookies, "items") else cookies
            cookie_str = "; ".join(f"{k}={v}" for k, v in items)
            for k in list(headers.keys()):
                if k.lower() == "cookie":
                    cookie_str = f"{headers.pop(k)}; {cookie_str}"
                    break
            headers["Cookie"] = cookie_str
            kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP клієнт для API/E2E тестів з автоматичним скиданням
    усіх dependency_overrides після завершення тесту.
    Автоматично підміняє get_db_session та get_read_db_session на транзакційну сесію із savepoint,
    що гарантує повний відкат усіх створених даних після тесту.
    """

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_read_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with ApiTestClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_uow() -> FakeUnitOfWork:
    """
    Підміняє реальний get_uow на FakeUnitOfWork у dependency_overrides.
    Дозволяє перевіряти коміт/відкат транзакцій в ендпоінтах без звернення до БД.
    """
    fake_uow = FakeUnitOfWork()

    async def _override_get_uow() -> AsyncGenerator[IUnitOfWork, None]:
        yield fake_uow

    app.dependency_overrides[get_uow] = _override_get_uow
    return fake_uow


@pytest.fixture
def auth_cookies_factory() -> Callable[[dict[str, Any] | None], dict[str, str]]:
    """
    Фабрика для створення cookies авторизації access_token=<jwt>
    із заданими клеймами (наприклад, sub, role).
    """

    def _factory(payload: dict[str, Any] | None = None) -> dict[str, str]:
        data = payload or {"sub": str(uuid7()), "role": "super_admin"}
        token = create_access_token(data)
        return {"access_token": token}

    return _factory


@pytest.fixture
async def superadmin_user(db_session: AsyncSession) -> UserModel:
    """Отримання сутності системного SuperAdmin із тестової БД."""
    stmt = select(UserModel).where(UserModel.username == settings.seed.superadmin_username.strip().lower())
    res = await db_session.execute(stmt)
    user = res.scalar_one()
    db_session.expunge(user)
    return user


@pytest.fixture
def superadmin_cookies(
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
    superadmin_user: UserModel,
) -> dict[str, str]:
    """Готові валідні Cookies суперкористувача з повними системними правами."""
    return auth_cookies_factory({"sub": str(superadmin_user.id), "role": SystemRole.SUPER_ADMIN.value})


@pytest.fixture
async def user_role(db_session: AsyncSession) -> RoleModel:
    """Отримання базової системної ролі користувача (user)."""
    stmt = select(RoleModel).where(RoleModel.code == SystemRole.USER.value)
    res = await db_session.execute(stmt)
    role = res.scalar_one()
    db_session.expunge(role)
    return role


@pytest.fixture
def viewer_role(user_role: RoleModel) -> RoleModel:
    """Аліас для зворотної сумісності з тестами (viewer_role -> user_role)."""
    return user_role


@pytest.fixture
async def admin_role(db_session: AsyncSession) -> RoleModel:
    """Отримання системної ролі адміністратора (admin)."""
    stmt = select(RoleModel).where(RoleModel.code == SystemRole.ADMIN.value)
    res = await db_session.execute(stmt)
    role = res.scalar_one()
    db_session.expunge(role)
    return role


@pytest.fixture
async def no_permissions_user(db_session: AsyncSession) -> UserModel:
    """Створює користувача з роллю без жодних прав (для перевірки 403 Forbidden)."""
    role = RoleModel(
        id=uuid7(),
        code=f"no_perms_{uuid7().hex[:6]}",
        name="No Permissions Role",
        description="Роль без дозволів для тестів 403",
        version=1,
    )
    db_session.add(role)

    user = UserModel(
        id=uuid7(),
        version=1,
        username=f"noperms_{uuid7().hex[:6]}",
        name="No Perms User",
        password_hash=default_password_hasher.hash("TestPass123!"),
        role_id=role.id,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.expunge(user)
    db_session.expunge(role)
    return user


@pytest.fixture
def no_permissions_cookies(
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
    no_permissions_user: UserModel,
) -> dict[str, str]:
    """Cookies авторизації користувача без жодних прав (для 403 Forbidden)."""
    return auth_cookies_factory({"sub": str(no_permissions_user.id), "role": "no_perms"})


@pytest.fixture
async def admin_user_with_permissions(
    db_session: AsyncSession,
    viewer_role: RoleModel,
) -> UserModel:
    """Створює адміністратора з усіма системними дозволами через custom_permissions (але не super_admin)."""
    stmt = select(PermissionModel)
    res = await db_session.execute(stmt)
    all_perms = res.scalars().all()

    user = UserModel(
        id=uuid7(),
        version=1,
        username=f"admin_sub_{uuid7().hex[:6]}",
        name="Admin Sub User",
        password_hash=default_password_hasher.hash("AdminPass123!"),
        role_id=viewer_role.id,
    )
    db_session.add(user)
    await db_session.flush()

    for p in all_perms:
        db_session.add(UserPermissionModel(user_id=user.id, permission_id=p.id))
    await db_session.flush()
    db_session.expunge(user)
    return user


@pytest.fixture
def admin_cookies(
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
    admin_user_with_permissions: UserModel,
) -> dict[str, str]:
    """Cookies авторизованого користувача з усіма правами (не super_admin)."""
    return auth_cookies_factory({"sub": str(admin_user_with_permissions.id), "role": "admin"})
