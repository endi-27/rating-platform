from src.modules.reviews.domain.models.review import Review
from src.modules.reviews.infrastructure.models.review_model import ReviewModel


class ReviewMapper:
    """Мапер між Review (Domain) та ReviewModel (ORM)."""

    @staticmethod
    def to_domain(model: ReviewModel) -> Review:
        return Review(
            id=model.id,
            version=model.version,
            target_id=model.target_id,
            user_id=model.user_id,
            score=model.score,
            title=model.title,
            content=model.content,
            status=model.status,
            helpful_count=model.helpful_count,
            unhelpful_count=model.unhelpful_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def to_orm(domain: Review) -> ReviewModel:
        return ReviewModel(
            id=domain.id,
            version=domain.version,
            target_id=domain.target_id,
            user_id=domain.user_id,
            score=domain.score,
            title=domain.title,
            content=domain.content,
            status=domain.status,
            helpful_count=domain.helpful_count,
            unhelpful_count=domain.unhelpful_count,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            deleted_at=domain.deleted_at,
        )

    @staticmethod
    def update_to_orm(orm: ReviewModel, domain: Review) -> None:
        orm.score = domain.score
        orm.title = domain.title
        orm.content = domain.content
        orm.status = domain.status
        orm.helpful_count = domain.helpful_count
        orm.unhelpful_count = domain.unhelpful_count
        orm.version = domain.version
        orm.updated_at = domain.updated_at
        orm.deleted_at = domain.deleted_at
