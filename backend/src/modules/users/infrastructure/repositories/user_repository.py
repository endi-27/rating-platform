from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from src.infrastructure.db import SqlAlchemyBaseCrudRepository
from src.modules.users.domain import IUserRepository, User
from src.modules.users.infrastructure.mappers import UserMapper
from src.modules.users.infrastructure.models import RoleModel, UserModel, UserPermissionModel


class SqlAlchemyUserRepository(SqlAlchemyBaseCrudRepository[User, UserModel], IUserRepository):
    """SQLAlchemy реалізація репозиторію користувачів для Write-пайплайну."""

    _model_cls = UserModel
    _mapper = UserMapper

    def _default_options(self) -> Sequence[ExecutableOption]:
        return (
            selectinload(UserModel.role).selectinload(RoleModel.permissions),
            selectinload(UserModel.custom_permissions),
        )

    async def get_by_username(self, username: str) -> User | None:
        """
        Пошук користувача за username без урахування регістру (case-insensitive).
        Використовує функціональний B-Tree індекс `idx_users_username_lower` для високої швидкодії.
        """
        stmt = (
            select(UserModel)
            .options(*self._default_options())
            .where(func.lower(UserModel.username) == username.lower())
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return UserMapper.to_domain(orm) if orm else None

    async def exists_by_username(self, username: str, *, exclude_user_id: UUID | None = None) -> bool:
        """Швидка перевірка зайнятості username через функціональний індекс та SELECT 1."""
        stmt = select(1).where(func.lower(UserModel.username) == username.lower())
        if exclude_user_id is not None:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        stmt = stmt.limit(1)
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)

    async def save(self, user: User, /) -> None:
        """
        Збереження агрегата користувача та синхронізація персональних дозволів.

        Життєвий цикл збереження:
        1. Отримати існуючий ORM-запис із сесії або створити новий (INSERT + flush).
        2. Оновити скалярні поля моделі через UserMapper.update_to_orm.
        3. Синхронізувати M2M-зв'язок user_permissions через UserPermissionModel.
        4. Виконати flush() для спрацювання контролю версій (OCC) та синхронізувати
           інкрементовану версію назад у доменний агрегат.
        """
        orm = await self._session.get(UserModel, user.id)
        if orm is None:
            orm = UserMapper.to_orm(user)
            self._session.add(orm)
            # flush гарантує збереження рядка користувача перед вставкою FK у таблицю user_permissions
            await self._session.flush()
            is_new = True
        else:
            UserMapper.update_to_orm(orm, user)
            is_new = False

        # Синхронізація персональних дозволів користувача через Association Objects
        await self._sync_custom_permissions(orm, {p.id for p in user.custom_permissions}, is_new=is_new)

        # Фіксація змін у сесії для спрацювання механізму Optimistic Locking (OCC)
        await self._session.flush()
        # Синхронізуємо актуальну версію назад у доменний агрегат
        user.version = orm.version

    async def _sync_custom_permissions(
        self,
        user_orm: UserModel,
        target_perm_ids: set[UUID],
        *,
        is_new: bool = False,
    ) -> None:
        """
        Диференціальна синхронізація M2M зв'язку `user_permissions` через Association Objects.

        Чому обрано Association Objects (UserPermissionModel):
        - Сумісність з Audit Hook before_flush (session.new / session.deleted).
        - Автоматичне створення EntityAuditModel записів для INSERT / DELETE.
        - При зміні дозволів існуючого користувача оновлюється updated_at,
          що забезпечує інкремент OCC поля version на корені агрегата (UserModel).
        """
        # 1. Оптимізація: для нового користувача одразу додаємо дозволи без зайвого SELECT
        if is_new:
            for pid in target_perm_ids:
                self._session.add(UserPermissionModel(user_id=user_orm.id, permission_id=pid))
            return

        # 2. Читаємо поточні прив'язані моделі персональних дозволів для існуючого користувача
        stmt = select(UserPermissionModel).where(UserPermissionModel.user_id == user_orm.id)
        current_perms = list((await self._session.execute(stmt)).scalars().all())
        existing_ids = {p.permission_id for p in current_perms}

        # 3. Guard clause: якщо набір прав не змінився, уникаємо зайвих дій
        if existing_ids == target_perm_ids:
            return

        # 4. Обчислюємо різницю множин для точкової мутації
        to_remove = existing_ids - target_perm_ids
        to_add = target_perm_ids - existing_ids

        # 5. Видаляємо лише скасовані дозволи через session.delete для спрацювання аудиту
        if to_remove:
            for p in current_perms:
                if p.permission_id in to_remove:
                    await self._session.delete(p)

        # 6. Додаємо лише нові дозволи через session.add для спрацювання аудиту
        if to_add:
            for pid in to_add:
                self._session.add(UserPermissionModel(user_id=user_orm.id, permission_id=pid))

        # 7. Права існуючого користувача змінилися — оновлюємо updated_at для спрацювання OCC на Aggregate Root
        user_orm.updated_at = datetime.now(UTC)
