from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_cache.decorator import cache

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.api.schemas.sorting import MultiSort, sort_dependency
from src.core import CurrentUser, PermissionCode, settings
from src.modules.auth import require_permission
from src.modules.reviews.application.dto import (
    CreateReviewDTO,
    ModerateReviewDTO,
    ReviewResponseDTO,
    TargetRatingResponseDTO,
    UpdateReviewDTO,
    VoteReviewDTO,
)
from src.modules.reviews.application.use_cases import (
    CreateReviewUseCase,
    DeleteReviewUseCase,
    ModerateReviewUseCase,
    UpdateReviewUseCase,
    VoteReviewUseCase,
)
from src.modules.reviews.dependencies import (
    get_create_review_uc,
    get_delete_review_uc,
    get_moderate_review_uc,
    get_review_query_service,
    get_target_query_service,
    get_update_review_uc,
    get_vote_review_uc,
)
from src.modules.reviews.domain.exceptions import (
    ReviewNotFoundException,
    TargetNotFoundException,
)
from src.modules.reviews.queries import (
    ReviewFilterDTO,
    ReviewQueryService,
    ReviewSortField,
    TargetQueryService,
)

router = APIRouter(tags=["Reviews & Ratings"])


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
    review_queries: Annotated[ReviewQueryService, Depends(get_review_query_service)],
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.REVIEWS_CREATE))],
) -> ReviewResponseDTO:
    review_id = await use_case.execute(
        target_id=target_id,
        user_id=current_user.id,
        dto=payload,
    )
    review = await review_queries.get_by_id(review_id)
    if review is None:
        raise ReviewNotFoundException(review_id)
    return review


@router.get(
    "/targets/{target_id}/reviews",
    response_model=PaginatedResponse[ReviewResponseDTO],
    summary="Стрічка відгуків об'єкта",
    description="Публічний перегляд опублікованих відгуків об'єкта (CQRS Read з шардингом за target_id).",
)
async def list_target_reviews(
    target_id: UUID,
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[
        MultiSort[ReviewSortField],
        Depends(sort_dependency(ReviewSortField, default=("-created_at",), max_fields=2)),
    ],
    review_queries: Annotated[ReviewQueryService, Depends(get_review_query_service)],
    target_queries: Annotated[TargetQueryService, Depends(get_target_query_service)],
    score: Annotated[int | None, Query(ge=1, le=5, description="Фільтр за оцінкою")] = None,
    status_filter: Annotated[str, Query(alias="status", description="Статус модерації")] = "published",
    author_id: Annotated[UUID | None, Query(description="Фільтр за автором відгуку")] = None,
) -> PaginatedResponse[ReviewResponseDTO]:
    # 1. Перевірка існування об'єкта
    target = await target_queries.get_by_id(target_id)
    if target is None:
        raise TargetNotFoundException(target_id)

    # 2. Вибірка відгуків через Query Service
    filters = ReviewFilterDTO(
        target_id=target_id,
        status=status_filter,
        score=score,
        author_id=author_id,
    )
    return await review_queries.list_by_target(
        target_id=target_id,
        pagination=pagination,
        sort=sort,
        filters=filters,
    )


@router.get(
    "/targets/{target_id}/rating",
    response_model=TargetRatingResponseDTO,
    summary="Агрегований знімок рейтингу об'єкта",
    description="Миттєва видача лічильників, середнього та байєсівського рейтингу з кешу Redis.",
)
@cache(expire=3600, namespace=settings.cache.namespace.reviews)
async def get_target_rating(
    target_id: UUID,
    target_queries: Annotated[TargetQueryService, Depends(get_target_query_service)],
) -> TargetRatingResponseDTO:
    rating = await target_queries.get_target_rating(target_id)
    if rating is None:
        raise TargetNotFoundException(target_id)
    return rating


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
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.REVIEWS_VOTE))],
) -> dict[str, Any]:
    vote_id = await use_case.execute(
        review_id=review_id,
        user_id=current_user.id,
        is_helpful=payload.is_helpful,
    )
    return {
        "vote_id": str(vote_id),
        "review_id": str(review_id),
        "is_helpful": payload.is_helpful,
    }


@router.put(
    "/targets/{target_id}/reviews/{review_id}",
    response_model=ReviewResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Оновлення власного відгуку",
    description="Повне оновлення оцінки та змісту відгуку з перевіркою версії (OCC). Вимагає дозволу REVIEWS_UPDATE.",
)
async def update_review(
    target_id: UUID,
    review_id: UUID,
    payload: UpdateReviewDTO,
    use_case: Annotated[UpdateReviewUseCase, Depends(get_update_review_uc)],
    review_queries: Annotated[ReviewQueryService, Depends(get_review_query_service)],
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.REVIEWS_UPDATE))],
) -> ReviewResponseDTO:
    await use_case.execute(
        target_id=target_id,
        review_id=review_id,
        user_id=current_user.id,
        dto=payload,
    )
    review = await review_queries.get_by_id(review_id)
    if review is None:
        raise ReviewNotFoundException(review_id)
    return review


@router.delete(
    "/targets/{target_id}/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Видалення відгуку",
    description="Видаляє (деактивує) відгук. Доступно автору або модератору. Вимагає дозволу REVIEWS_DELETE.",
)
async def delete_review(
    target_id: UUID,
    review_id: UUID,
    use_case: Annotated[DeleteReviewUseCase, Depends(get_delete_review_uc)],
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.REVIEWS_DELETE))],
) -> None:
    has_moderate_permission = PermissionCode.REVIEWS_MODERATE.value in current_user.effective_permissions
    await use_case.execute(
        target_id=target_id,
        review_id=review_id,
        user_id=current_user.id,
        has_moderate_permission=has_moderate_permission,
    )


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
    review_queries: Annotated[ReviewQueryService, Depends(get_review_query_service)],
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.REVIEWS_MODERATE))],
) -> ReviewResponseDTO:
    await use_case.execute(
        review_id=review_id,
        action=payload.action,
        version=payload.version,
    )
    review = await review_queries.get_by_id(review_id)
    if review is None:
        raise ReviewNotFoundException(review_id)
    return review
