from src.modules.reviews.domain.models.target_rating import TargetRating
from src.modules.reviews.infrastructure.models.target_rating_model import TargetRatingModel


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
