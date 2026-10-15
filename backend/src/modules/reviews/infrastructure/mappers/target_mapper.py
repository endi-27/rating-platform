from src.modules.reviews.domain.models.target import Target
from src.modules.reviews.infrastructure.models.target_model import TargetModel


class TargetMapper:
    """Мапер між Target (Domain) та TargetModel (ORM)."""

    @staticmethod
    def to_domain(model: TargetModel) -> Target:
        return Target(
            id=model.id,
            version=model.version,
            slug=model.slug,
            title=model.title,
            category=model.category,
            description=model.description,
            metadata=dict(model.metadata_ or {}),
            created_by_id=model.created_by_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def to_orm(domain: Target) -> TargetModel:
        return TargetModel(
            id=domain.id,
            version=domain.version,
            slug=domain.slug,
            title=domain.title,
            category=domain.category,
            description=domain.description,
            metadata_=dict(domain.metadata),
            created_by_id=domain.created_by_id,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            deleted_at=domain.deleted_at,
        )

    @staticmethod
    def update_to_orm(orm: TargetModel, domain: Target) -> None:
        orm.slug = domain.slug
        orm.title = domain.title
        orm.category = domain.category
        orm.description = domain.description
        orm.metadata_ = dict(domain.metadata)
        orm.version = domain.version
        orm.updated_at = domain.updated_at
        orm.deleted_at = domain.deleted_at
