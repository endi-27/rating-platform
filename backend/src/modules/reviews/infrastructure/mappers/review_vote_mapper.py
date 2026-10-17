from src.modules.reviews.domain.models.review_vote import ReviewVote
from src.modules.reviews.infrastructure.models.review_vote_model import ReviewVoteModel


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
