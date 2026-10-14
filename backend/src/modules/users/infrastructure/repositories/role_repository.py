from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from src.infrastructure.db import SqlAlchemyBaseCrudRepository
from src.modules.users.domain import IRoleRepository, Role
from src.modules.users.infrastructure.mappers import RoleMapper
from src.modules.users.infrastructure.models import RoleModel, RolePermissionModel


class SqlAlchemyRoleRepository(SqlAlchemyBaseCrudRepository[Role, RoleModel], IRoleRepository):
    """SQLAlchemy реалізація репозиторію ролей для Write-пайплайну."""

    _model_cls = RoleModel
    _mapper = RoleMapper

    def _default_options(self) -> Sequence[ExecutableOption]:
        return (selectinload(RoleModel.permissions),)

    async def get_by_code(self, code: str) -> Role | None:
        """Пошук ролі за унікальним символьним кодом (case-insensitive)."""
        stmt = select(RoleModel).options(*self._default_options()).where(func.lower(RoleModel.code) == code.lower())
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return RoleMapper.to_domain(orm) if orm else None

    async def exists_by_code(self, code: str) -> bool:
        """Швидка перевірка наявності ролі за кодом через SELECT 1."""
        stmt = select(1).where(func.lower(RoleModel.code) == code.lower())
        stmt = stmt.limit(1)
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)

    async def save(self, role: Role, /) -> None:
        """
        Збереження агрегата ролі та диференціальна синхронізація її дозволів.

        Життєвий цикл збереження:
        1. Отримати існуючий ORM-запис із сесії або створити новий (INSERT + flush).
        2. Оновити скалярні поля моделі через RoleMapper.update_to_orm.
        3. Синхронізувати M2M-зв'язок role_permissions через RolePermissionModel.
        4. Виконати flush() для спрацювання контролю версій (OCC) та синхронізувати
           інкрементовану версію назад у доменний агрегат.
        """
        orm = await self._session.get(RoleModel, role.id)
        if orm is None:
            orm = RoleMapper.to_orm(role)
            self._session.add(orm)
            await self._session.flush()
            is_new = True
        else:
            RoleMapper.update_to_orm(orm, role)
            is_new = False

        # Синхронізація дозволів через Association Objects
        await self._sync_permissions(orm, {p.id for p in role.permissions}, is_new=is_new)

        # Фіксація змін у сесії для спрацювання механізму Optimistic Locking (OCC)
        await self._session.flush()
        # Синхронізуємо згенеровану або інкрементовану БД версію назад у доменну модель
        role.version = orm.version

    async def _sync_permissions(
        self,
        role_orm: RoleModel,
        target_perm_ids: set[UUID],
        *,
        is_new: bool = False,
    ) -> None:
        """
        Диференціальна синхронізація M2M зв'язку `role_permissions` через Association Objects.

        Чому обрано Association Objects (RolePermissionModel):
        - Сумісність з Audit Hook before_flush (session.new / session.deleted).
        - Автоматичне створення EntityAuditModel записів для INSERT / DELETE.
        - При зміні дозволів існуючої ролі оновлюється updated_at,
          що забезпечує інкремент OCC поля version на корені агрегата (RoleModel).
        """
        # 1. Оптимізація: для нової ролі одразу додаємо дозволи без зайвого SELECT
        if is_new:
            for pid in target_perm_ids:
                self._session.add(RolePermissionModel(role_id=role_orm.id, permission_id=pid))
            return

        # 2. Читаємо поточні прив'язані моделі дозволів для даної ролі
        stmt = select(RolePermissionModel).where(RolePermissionModel.role_id == role_orm.id)
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
                self._session.add(RolePermissionModel(role_id=role_orm.id, permission_id=pid))

        # 7. Права існуючої ролі змінилися — оновлюємо updated_at для спрацювання OCC на Aggregate Root
        role_orm.updated_at = datetime.now(UTC)
