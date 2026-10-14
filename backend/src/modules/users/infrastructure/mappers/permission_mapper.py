from src.core import PermissionCode
from src.modules.users.domain.models import Permission
from src.modules.users.infrastructure.models import PermissionModel


class PermissionMapper:
    """Мапер між Permission (Domain) та PermissionModel (ORM)."""

    @staticmethod
    def to_domain(model: PermissionModel) -> Permission:
        return Permission(
            id=model.id,
            code=PermissionCode(model.code),
            name=model.name,
            description=model.description,
            created_at=model.created_at,
        )

    @staticmethod
    def to_orm(domain: Permission) -> PermissionModel:
        return PermissionModel(
            id=domain.id,
            code=domain.code.value,
            name=domain.name,
            description=domain.description,
            created_at=domain.created_at,
        )
