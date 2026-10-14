from src.modules.reviews.domain.models import Review, ReviewVote, Target, TargetRating
from src.modules.reviews.infrastructure.models import (
    ReviewModel,
    ReviewVoteModel,
    TargetModel,
    TargetRatingModel,
)


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


class TargetRatingMapper:
    """Мапер між TargetRating (Domain) та TargetRatingModel (ORM)."""

    @staticmethod
    def to_domain(model: TargetRatingModel) -> TargetRating:
        return TargetRating(
            target_id=model.target_id,
            total_reviews=model.total_reviews,
            average_score=model.average_score,
            bayesian_score=model.bayesian_score,
            star_1_count=model.star_1_count,
            star_2_count=model.star_2_count,
            star_3_count=model.star_3_count,
            star_4_count=model.star_4_count,
            star_5_count=model.star_5_count,
            last_calculated_at=model.last_calculated_at,
            version=model.version,
        )

    @staticmethod
    def to_orm(domain: TargetRating) -> TargetRatingModel:
        return TargetRatingModel(
            target_id=domain.target_id,
            total_reviews=domain.total_reviews,
            average_score=domain.average_score,
            bayesian_score=domain.bayesian_score,
            star_1_count=domain.star_1_count,
            star_2_count=domain.star_2_count,
            star_3_count=domain.star_3_count,
            star_4_count=domain.star_4_count,
            star_5_count=domain.star_5_count,
            last_calculated_at=domain.last_calculated_at,
            version=domain.version,
        )

    @staticmethod
    def update_to_orm(orm: TargetRatingModel, domain: TargetRating) -> None:
        orm.total_reviews = domain.total_reviews
        orm.average_score = domain.average_score
        orm.bayesian_score = domain.bayesian_score
        orm.star_1_count = domain.star_1_count
        orm.star_2_count = domain.star_2_count
        orm.star_3_count = domain.star_3_count
        orm.star_4_count = domain.star_4_count
        orm.star_5_count = domain.star_5_count
        orm.last_calculated_at = domain.last_calculated_at
        orm.version = domain.version


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


class ReviewVoteMapper:
    """Мапер між ReviewVote (Domain) та ReviewVoteModel (ORM)."""

    @staticmethod
    def to_domain(model: ReviewVoteModel) -> ReviewVote:
        return ReviewVote(
            id=model.id,
            review_id=model.review_id,
            user_id=model.user_id,
            is_helpful=model.is_helpful,
            created_at=model.created_at,
        )

    @staticmethod
    def to_orm(domain: ReviewVote) -> ReviewVoteModel:
        return ReviewVoteModel(
            id=domain.id,
            review_id=domain.review_id,
            user_id=domain.user_id,
            is_helpful=domain.is_helpful,
            created_at=domain.created_at,
        )

    @staticmethod
    def update_to_orm(orm: ReviewVoteModel, domain: ReviewVote) -> None:
        orm.is_helpful = domain.is_helpful
