from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_cache.decorator import cache

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.core import CurrentUser, PermissionCode, settings
from src.modules.auth.dependencies import get_current_user, require_permission
from src.modules.reviews.application.dto import (
    CreateReviewDTO,
    ModerateReviewDTO,
    ReviewResponseDTO,
    TargetRatingResponseDTO,
    VoteReviewDTO,
)
from src.modules.reviews.application.use_cases import (
    CreateReviewUseCase,
    GetTargetDetailsUseCase,
    ListTargetReviewsUseCase,
    ModerateReviewUseCase,
    VoteReviewUseCase,
)
from src.modules.reviews.dependencies import (
    get_create_review_uc,
    get_list_target_reviews_uc,
    get_moderate_review_uc,
    get_target_details_uc,
    get_vote_review_uc,
)
from src.modules.reviews.domain.exceptions import TargetNotFoundException
from src.modules.reviews.domain.models import Review

router = APIRouter(tags=["Відгуки та рейтинги (Reviews & Ratings)"])


def _to_review_dto(review: Review) -> ReviewResponseDTO:
    return ReviewResponseDTO(
        id=review.id,
        target_id=review.target_id,
        user_id=review.user_id,
        score=review.score,
        title=review.title,
        content=review.content,
        status=review.status,
        helpful_count=review.helpful_count,
        unhelpful_count=review.unhelpful_count,
        version=review.version,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.post(
    "/targets/{target_id}/reviews",
    response_model=ReviewResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Публікація відгуку",
    description="Публікація відгуку користувачем. Застосовує правило One Review та атомарно оновлює рейтинг.",
)
async def create_review(
    target_id: UUID,
    payload: CreateReviewDTO,
    use_case: Annotated[CreateReviewUseCase, Depends(get_create_review_uc)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ReviewResponseDTO:
    review = await use_case.execute(
        target_id=target_id,
        user_id=current_user.id,
        dto=payload,
    )
    return _to_review_dto(review)


@router.get(
    "/targets/{target_id}/reviews",
    response_model=PaginatedResponse[ReviewResponseDTO],
    summary="Стрічка відгуків об'єкта",
    description="Публічний перегляд опублікованих відгуків об'єкта з пагінацією (фільтрація за target_id).",
)
async def list_target_reviews(
    target_id: UUID,
    use_case: Annotated[ListTargetReviewsUseCase, Depends(get_list_target_reviews_uc)],
    page: Annotated[int, Query(ge=1, description="Номер сторінки")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Розмір сторінки")] = 20,
) -> PaginatedResponse[ReviewResponseDTO]:
    pagination = PaginationParams(page=page, page_size=page_size)
    reviews, total = await use_case.execute(
        target_id=target_id,
        status="published",
        page=page,
        page_size=page_size,
    )
    dto_items = [_to_review_dto(r) for r in reviews]
    return PaginatedResponse.create(items=dto_items, total=total, pagination=pagination)


@router.get(
    "/targets/{target_id}/rating",
    response_model=TargetRatingResponseDTO,
    summary="Агрегований знімок рейтингу об'єкта",
    description="Миттєва видача лічильників, середнього та байєсівського рейтингу з кешу Redis.",
)
@cache(expire=3600, namespace=settings.cache.namespace.reviews)
async def get_target_rating(
    target_id: UUID,
    use_case: Annotated[GetTargetDetailsUseCase, Depends(get_target_details_uc)],
) -> TargetRatingResponseDTO:
    target, rating = await use_case.execute(target_id)
    if rating is None:
        raise TargetNotFoundException(target_id)

    return TargetRatingResponseDTO(
        total_reviews=rating.total_reviews,
        average_score=rating.average_score,
        bayesian_score=rating.bayesian_score,
        star_1_count=rating.star_1_count,
        star_2_count=rating.star_2_count,
        star_3_count=rating.star_3_count,
        star_4_count=rating.star_4_count,
        star_5_count=rating.star_5_count,
        last_calculated_at=rating.last_calculated_at,
    )


@router.post(
    "/reviews/{review_id}/vote",
    response_model=dict[str, Any],
    summary="Голосування за корисність відгуку",
    description="Оцінка корисності. Заборонено голосувати за власний відгук або двічі з тим самим значенням.",
)
async def vote_review(
    review_id: UUID,
    payload: VoteReviewDTO,
    use_case: Annotated[VoteReviewUseCase, Depends(get_vote_review_uc)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    vote = await use_case.execute(
        review_id=review_id,
        user_id=current_user.id,
        is_helpful=payload.is_helpful,
    )
    return {
        "vote_id": str(vote.id),
        "review_id": str(vote.review_id),
        "is_helpful": vote.is_helpful,
    }


@router.patch(
    "/reviews/{review_id}/moderate",
    response_model=ReviewResponseDTO,
    summary="Модерація відгуку",
    description="Модерація відгуку (hide/publish/flag). Вимагає дозволу REVIEWS_MODERATE.",
)
async def moderate_review(
    review_id: UUID,
    payload: ModerateReviewDTO,
    use_case: Annotated[ModerateReviewUseCase, Depends(get_moderate_review_uc)],
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.REVIEWS_MODERATE))],
) -> ReviewResponseDTO:
    review = await use_case.execute(
        review_id=review_id,
        action=payload.action,
    )
    return _to_review_dto(review)
