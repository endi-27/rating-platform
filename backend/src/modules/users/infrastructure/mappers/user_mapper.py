from src.infrastructure.db import get_loaded
from src.modules.users.domain.models import Permission, Role, User
from src.modules.users.infrastructure.mappers.permission_mapper import PermissionMapper
from src.modules.users.infrastructure.mappers.role_mapper import RoleMapper
from src.modules.users.infrastructure.models import UserModel


class UserMapper:
    """Мапер між User (Domain) та UserModel (ORM)."""

    @staticmethod
    def to_domain(model: UserModel) -> User:
        raw_role = get_loaded(model, "role")
        role: Role | None = RoleMapper.to_domain(raw_role) if raw_role else None

        raw_perms = get_loaded(model, "custom_permissions") or []
        custom_permissions: set[Permission] = {PermissionMapper.to_domain(p) for p in raw_perms}

        return User(
            id=model.id,
            version=model.version,
            username=model.username,
            name=model.name,
            password_hash=model.password_hash,
            role_id=model.role_id,
            role=role,
            custom_permissions=custom_permissions,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def to_orm(domain: User) -> UserModel:
        return UserModel(
            id=domain.id,
            version=domain.version,
            username=domain.username,
            name=domain.name,
            password_hash=domain.password_hash,
            role_id=domain.role_id,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            deleted_at=domain.deleted_at,
        )

    @staticmethod
    def update_to_orm(orm: UserModel, domain: User) -> None:
        """Оновлення полів існуючої ORM моделі зі стану доменного агрегата."""
        orm.name = domain.name
        orm.username = domain.username
        orm.password_hash = domain.password_hash
        orm.role_id = domain.role_id
        orm.version = domain.version
        orm.updated_at = domain.updated_at
        orm.deleted_at = domain.deleted_at
