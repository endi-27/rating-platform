from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from fastapi_cache.decorator import cache
from pydantic import ValidationError

from src.api import (
    MultiSort,
    PaginatedResponse,
    PaginationParams,
    sort_dependency,
)
from src.core import CurrentUser, PermissionCode, settings
from src.infrastructure.cache import (
    default_key_builder,
    resource_key_builder,
)
from src.modules.auth import require_permission
from src.modules.users.dependencies import get_permission_query_service
from src.modules.users.domain import PermissionNotFoundError
from src.modules.users.queries import (
    PermissionFilterDTO,
    PermissionQueryService,
    PermissionResponseDTO,
    PermissionSortField,
)

permissions_router = APIRouter(prefix="/permissions", tags=["Permissions"])


async def get_permission_filters(
    search: Annotated[str | None, Query(description="Пошук за назвою або кодом дозволу")] = None,
    ids: Annotated[set[UUID] | None, Query(description="Фільтр за списком ID дозволів")] = None,
    codes: Annotated[set[str] | None, Query(description="Фільтр за списком кодів дозволів")] = None,
) -> PermissionFilterDTO:
    try:
        return PermissionFilterDTO(
            ids=ids,
            codes=codes,
            search=search,
        )
    except ValidationError as exc:
        raise RequestValidationError(errors=exc.errors()) from exc


@permissions_router.get("", response_model=PaginatedResponse[PermissionResponseDTO])
@cache(namespace=settings.cache.namespace.permissions, key_builder=default_key_builder)
async def list_permissions(
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.PERMISSIONS_READ))],
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[
        MultiSort[PermissionSortField],
        Depends(sort_dependency(PermissionSortField, default=("-created_at",), max_fields=3)),
    ],
    perm_queries: Annotated[PermissionQueryService, Depends(get_permission_query_service)],
    filters: Annotated[PermissionFilterDTO, Depends(get_permission_filters)],
) -> PaginatedResponse[PermissionResponseDTO]:
    """Отримання системного довідника прав доступу (Permissions). Тільки читання."""
    return await perm_queries.get_all(pagination=pagination, sort=sort, filters=filters)


@permissions_router.get("/{permission_id}", response_model=PermissionResponseDTO)
@cache(namespace=settings.cache.namespace.permissions, key_builder=resource_key_builder)
async def get_permission_by_id(
    permission_id: UUID,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.PERMISSIONS_READ))],
    perm_queries: Annotated[PermissionQueryService, Depends(get_permission_query_service)],
) -> PermissionResponseDTO:
    """Отримання опису дозволу за його ID."""
    perm = await perm_queries.get_by_id(permission_id)
    if not perm:
        raise PermissionNotFoundError(f"Дозвіл з ID '{permission_id}' не знайдено.")
    return perm


@permissions_router.get("/by-code/{code}", response_model=PermissionResponseDTO)
@cache(namespace=settings.cache.namespace.permissions, key_builder=resource_key_builder)
async def get_permission_by_code(
    code: str,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.PERMISSIONS_READ))],
    perm_queries: Annotated[PermissionQueryService, Depends(get_permission_query_service)],
) -> PermissionResponseDTO:
    """Отримання опису дозволу за його унікальним рядковим кодом (наприклад, 'users:read')."""
    perm = await perm_queries.get_by_code(code)
    if not perm:
        raise PermissionNotFoundError(f"Дозвіл з кодом '{code}' не знайдено.")
    return perm
