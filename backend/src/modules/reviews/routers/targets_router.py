from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi_cache.decorator import cache

from src.api.schemas.pagination import PaginatedResponse, PaginationParams
from src.api.schemas.sorting import MultiSort, sort_dependency
from src.core import CurrentUser, PermissionCode, settings
from src.modules.auth.dependencies import require_permission
from src.modules.reviews.application.dto import (
    CreateTargetDTO,
    TargetRatingResponseDTO,
    TargetResponseDTO,
)
from src.modules.reviews.application.use_cases import CreateTargetUseCase
from src.modules.reviews.dependencies import (
    get_create_target_uc,
    get_target_query_service,
)
from src.modules.reviews.domain.exceptions import TargetNotFoundException
from src.modules.reviews.domain.models import Target, TargetRating
from src.modules.reviews.queries import (
    TargetFilterDTO,
    TargetQueryService,
    TargetSortField,
)

router = APIRouter(prefix="/targets", tags=["Об'єкти оцінювання (Targets)"])


def _to_target_dto(target: Target, rating: TargetRating | None) -> TargetResponseDTO:
    rating_dto: TargetRatingResponseDTO | None = None
    if rating is not None:
        rating_dto = TargetRatingResponseDTO(
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

    return TargetResponseDTO(
        id=target.id,
        slug=target.slug,
        title=target.title,
        category=target.category,
        description=target.description,
        metadata=dict(target.metadata),
        is_active=target.is_active,
        version=target.version,
        rating=rating_dto,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


@router.post(
    "",
    response_model=TargetResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Створення об'єкта оцінювання",
    description="Створює новий Target та ініціалізує порожній знімок рейтингу. Вимагає дозволу TARGETS_CREATE.",
)
async def create_target(
    payload: CreateTargetDTO,
    use_case: Annotated[CreateTargetUseCase, Depends(get_create_target_uc)],
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.TARGETS_CREATE))],
) -> TargetResponseDTO:
    target = await use_case.execute(payload, created_by_id=current_user.id)
    empty_rating = TargetRating.create_empty(target.id)
    return _to_target_dto(target, empty_rating)


@router.get(
    "",
    response_model=PaginatedResponse[TargetResponseDTO],
    summary="Каталог об'єктів оцінювання",
    description="Публічний перегляд списку об'єктів із фільтрацією, мульти-сортуванням та пагінацією (CQRS Read).",
)
async def list_targets(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[
        MultiSort[TargetSortField],
        Depends(sort_dependency(TargetSortField, default=("-created_at",), max_fields=2)),
    ],
    query_service: Annotated[TargetQueryService, Depends(get_target_query_service)],
    category: Annotated[str | None, Query(description="Фільтр за категорією")] = None,
    search: Annotated[str | None, Query(description="Пошук за назвою або слагом")] = None,
    min_rating: Annotated[Decimal | None, Query(ge=0, le=5, description="Мінімальний середній бал")] = None,
) -> PaginatedResponse[TargetResponseDTO]:
    filters = TargetFilterDTO(
        category=category,
        search=search,
        min_rating=min_rating,
        include_inactive=False,
    )
    return await query_service.get_all(pagination=pagination, sort=sort, filters=filters)


@router.get(
    "/{id_or_slug}",
    response_model=TargetResponseDTO,
    summary="Картка об'єкта оцінювання",
    description="Отримання детальної інформації про об'єкт за UUID або текстовим slug із кешуванням Redis.",
)
@cache(expire=3600, namespace=settings.cache.namespace.targets)
async def get_target_details(
    id_or_slug: str,
    query_service: Annotated[TargetQueryService, Depends(get_target_query_service)],
) -> TargetResponseDTO:
    target = await query_service.get_by_id_or_slug(id_or_slug)
    if target is None:
        raise TargetNotFoundException(id_or_slug)
    return target
