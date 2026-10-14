from src.infrastructure.db import get_loaded
from src.modules.users.domain.models import Permission, Role
from src.modules.users.infrastructure.mappers.permission_mapper import PermissionMapper
from src.modules.users.infrastructure.models import RoleModel


class RoleMapper:
    """Мапер між Role (Domain) та RoleModel (ORM)."""

    @staticmethod
    def to_domain(model: RoleModel) -> Role:
        raw_perms = get_loaded(model, "permissions") or []
        permissions: set[Permission] = {PermissionMapper.to_domain(p) for p in raw_perms}

        return Role(
            id=model.id,
            version=model.version,
            code=model.code,
            name=model.name,
            description=model.description,
            permissions=permissions,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def to_orm(domain: Role) -> RoleModel:
        return RoleModel(
            id=domain.id,
            version=domain.version,
            code=domain.code,
            name=domain.name,
            description=domain.description,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            deleted_at=domain.deleted_at,
        )

    @staticmethod
    def update_to_orm(orm: RoleModel, domain: Role) -> None:
        """Оновлення полів існуючої ORM моделі зі стану доменного агрегата."""
        orm.name = domain.name
        orm.code = domain.code
        orm.description = domain.description
        orm.version = domain.version
        orm.updated_at = domain.updated_at
        orm.deleted_at = domain.deleted_at
