from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi_cache.decorator import cache
from pydantic import ValidationError

from src.api import (
    DeletionAssessmentDTO,
    MultiSort,
    PaginatedResponse,
    PaginationParams,
    sort_dependency,
)
from src.core import (
    CurrentUser,
    DataInconsistencyException,
    PermissionCode,
    settings,
)
from src.infrastructure.cache import (
    default_key_builder,
    resource_key_builder,
)
from src.modules.auth import require_permission
from src.modules.users.application.dto import (
    CreateRoleDTO,
    RestoreRoleDTO,
    SoftDeleteRoleDTO,
    UpdateRoleDTO,
)
from src.modules.users.application.use_cases import (
    CreateRoleUseCase,
    HardDeleteRoleUseCase,
    RestoreRoleUseCase,
    SoftDeleteRoleUseCase,
    UpdateRoleUseCase,
)
from src.modules.users.dependencies import (
    get_create_role_uc,
    get_hard_delete_role_uc,
    get_restore_role_uc,
    get_role_query_service,
    get_soft_delete_role_uc,
    get_update_role_uc,
)
from src.modules.users.domain import RoleNotFoundError
from src.modules.users.queries import (
    RoleDetailDTO,
    RoleFilterDTO,
    RoleQueryService,
    RoleSortField,
)

roles_router = APIRouter(prefix="/roles", tags=["Roles"])


async def get_role_filters(
    search: Annotated[str | None, Query(description="Пошук за назвою або кодом ролі")] = None,
    ids: Annotated[set[UUID] | None, Query(description="Фільтр за списком ID ролей")] = None,
    codes: Annotated[set[str] | None, Query(description="Фільтр за списком кодів ролей")] = None,
    include_inactive: Annotated[bool, Query(description="Включити деактивовані ролі")] = False,
) -> RoleFilterDTO:
    try:
        return RoleFilterDTO(
            ids=ids,
            codes=codes,
            search=search,
            include_inactive=include_inactive,
        )
    except ValidationError as exc:
        raise RequestValidationError(errors=exc.errors()) from exc


@roles_router.get("", response_model=PaginatedResponse[RoleDetailDTO])
@cache(namespace=settings.cache.namespace.roles, key_builder=default_key_builder)
async def list_roles(
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_READ))],
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[
        MultiSort[RoleSortField],
        Depends(sort_dependency(RoleSortField, default=("-created_at",), max_fields=3)),
    ],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
    filters: Annotated[RoleFilterDTO, Depends(get_role_filters)],
) -> PaginatedResponse[RoleDetailDTO]:
    """Отримання списку ролей із прив'язаними дозволами та фільтрацією."""
    return await role_queries.get_all_details(pagination=pagination, sort=sort, filters=filters)


@roles_router.get("/{role_id}", response_model=RoleDetailDTO)
@cache(namespace=settings.cache.namespace.roles, key_builder=resource_key_builder)
async def get_role_by_id(
    role_id: UUID,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_READ))],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
) -> RoleDetailDTO:
    """Отримання детальної інформації про роль та її дозволи."""
    role = await role_queries.get_detail_by_id(role_id)
    if not role:
        raise RoleNotFoundError(f"Роль з ID '{role_id}' не знайдено.")
    return role


@roles_router.post("", response_model=RoleDetailDTO, status_code=status.HTTP_201_CREATED)
async def create_role(
    dto: CreateRoleDTO,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_CREATE))],
    create_uc: Annotated[CreateRoleUseCase, Depends(get_create_role_uc)],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
) -> RoleDetailDTO:
    """Створення нової ролі з переліком дозволів."""
    new_role_id = await create_uc.execute(dto)
    created_role = await role_queries.get_detail_by_id(new_role_id)
    if not created_role:
        raise DataInconsistencyException("Помилка отримання даних щойно створеної ролі.")
    return created_role


@roles_router.put("/{role_id}", response_model=RoleDetailDTO)
async def update_role(
    role_id: UUID,
    dto: UpdateRoleDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_UPDATE))],
    update_uc: Annotated[UpdateRoleUseCase, Depends(get_update_role_uc)],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
) -> RoleDetailDTO:
    """
    Повне оновлення ролі (Full PUT).
    Вимагає обов'язкової передачі OCC поля version.
    """
    await update_uc.execute(
        role_id,
        dto,
        actor=current_user,
    )
    updated_role = await role_queries.get_detail_by_id(role_id)
    if not updated_role:
        raise DataInconsistencyException(
            f"Помилка узгодженості даних: роль з ID '{role_id}' не знайдено після оновлення."
        )
    return updated_role


@roles_router.patch("/{role_id}/deactivate", response_model=RoleDetailDTO)
async def deactivate_role(
    role_id: UUID,
    dto: SoftDeleteRoleDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_DEACTIVATE))],
    soft_delete_uc: Annotated[SoftDeleteRoleUseCase, Depends(get_soft_delete_role_uc)],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
) -> RoleDetailDTO:
    """М'яке видалення (деактивація) ролі через PATCH."""
    await soft_delete_uc.execute(role_id, dto, actor=current_user)
    role = await role_queries.get_detail_by_id(role_id)
    if not role:
        raise DataInconsistencyException(
            f"Помилка узгодженості даних: роль з ID '{role_id}' не знайдено після деактивації."
        )
    return role


@roles_router.patch("/{role_id}/restore", response_model=RoleDetailDTO)
async def restore_role(
    role_id: UUID,
    dto: RestoreRoleDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_RESTORE))],
    restore_uc: Annotated[RestoreRoleUseCase, Depends(get_restore_role_uc)],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
) -> RoleDetailDTO:
    """Відновлення раніше деактивованої ролі через PATCH."""
    await restore_uc.execute(role_id, dto, actor=current_user)
    role = await role_queries.get_detail_by_id(role_id)
    if not role:
        raise DataInconsistencyException(
            f"Помилка узгодженості даних: роль з ID '{role_id}' не знайдено після відновлення."
        )
    return role


@roles_router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete_role(
    role_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_DELETE))],
    hard_delete_uc: Annotated[HardDeleteRoleUseCase, Depends(get_hard_delete_role_uc)],
) -> None:
    """Фізичне видалення ролі з БД. Дозволено лише якщо за роллю не закріплено активних користувачів."""
    await hard_delete_uc.execute(role_id, actor=current_user)


@roles_router.get("/{role_id}/delete-preview", response_model=DeletionAssessmentDTO)
async def preview_role_deletion(
    role_id: UUID,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.ROLES_DELETE))],
    role_queries: Annotated[RoleQueryService, Depends(get_role_query_service)],
) -> DeletionAssessmentDTO:
    """Аналіз можливості видалення ролі та кількості прив'язаних користувачів."""
    return await role_queries.assess_deletion(role_id)
