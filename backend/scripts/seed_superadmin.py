import asyncio
import sys
from pathlib import Path

# Додаємо корінь бекенду в sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from uuid6 import uuid7  # noqa: E402

from src.core import (  # noqa: E402
    SystemRole,
    default_password_hasher,
    logger,
    set_current_username,
    settings,
)
from src.modules.users.infrastructure.models import RoleModel, UserModel  # noqa: E402


async def get_superadmin_role(session: AsyncSession) -> RoleModel:
    """
    Отримання системної ролі SuperAdmin з бази даних.
    Роль та її права створюються виключно через Alembic-міграції.
    """
    logger.info("Пошук системної ролі SuperAdmin...")
    stmt = select(RoleModel).where(RoleModel.code == SystemRole.SUPER_ADMIN.value)
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()

    if role is None:
        error_msg = (
            "Критична помилка: системну роль 'super_admin' не знайдено в БД! "
            "Переконайтеся, що всі міграції застосовані: uv run alembic upgrade head"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.info("Системну роль SuperAdmin знайдено (ID: {id}).", id=str(role.id))
    return role


async def seed_superadmin_user(session: AsyncSession, role: RoleModel) -> None:
    """
    Ідемпотентне створення облікового запису SuperAdmin.
    Креденшали (логін та пароль) завантажуються виключно з Pydantic Settings.
    """
    logger.info("Перевірка наявності облікового запису SuperAdmin...")
    stmt = select(UserModel).where(UserModel.role_id == role.id)
    result = await session.execute(stmt)
    existing_admin = result.scalar_one_or_none()

    admin_username = settings.seed.superadmin_username.strip().lower()
    admin_name = settings.seed.superadmin_name.strip()
    admin_password = settings.seed.superadmin_password

    if existing_admin:
        logger.info(
            "Обліковий запис SuperAdmin вже присутній у системі: логін='{username}' (ID: {id}). Пропускаємо створення.",
            username=existing_admin.username,
            id=str(existing_admin.id),
        )
        return

    admin_user = UserModel(
        id=uuid7(),
        version=1,
        username=admin_username,
        name=admin_name,
        password_hash=default_password_hasher.hash(admin_password),
        role_id=role.id,
    )
    session.add(admin_user)
    logger.info(
        "Створено обліковий запис SuperAdmin: логін='{username}', ім'я='{name}' "
        "(пароль завантажено з конфігурації APP_CONFIG__SEED__...).",
        username=admin_username,
        name=admin_name,
    )


async def main() -> None:
    """Головна точка входу скрипта ініціалізації суперкористувача."""
    set_current_username("system:seed")

    try:
        engine = create_async_engine(settings.db.url, echo=False)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        logger.info("Запуск сідування SuperAdmin для Rating Platform...")
        async with session_factory() as session, session.begin():
            superadmin_role = await get_superadmin_role(session)
            await seed_superadmin_user(session, superadmin_role)

        await engine.dispose()
        logger.info("Сідування SuperAdmin успішно завершено.")
    finally:
        set_current_username(None)


if __name__ == "__main__":
    asyncio.run(main())
