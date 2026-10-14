from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
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
from src.modules.auth import (
    clear_auth_cookies,
    is_secure_request,
    require_permission,
)
from src.modules.users.application.dto import (
    ChangeSelfPasswordDTO,
    ChangeSelfUsernameDTO,
    CreateUserDTO,
    ResetUserPasswordDTO,
    RestoreUserDTO,
    SoftDeleteUserDTO,
    UpdateSelfProfileDTO,
    UpdateUserDTO,
    UserActionStatusDTO,
)
from src.modules.users.application.use_cases import (
    ChangeSelfPasswordUseCase,
    ChangeSelfUsernameUseCase,
    HardDeleteUserUseCase,
    RegisterUserUseCase,
    ResetUserPasswordUseCase,
    RestoreUserUseCase,
    SoftDeleteUserUseCase,
    UpdateSelfProfileUseCase,
    UpdateUserUseCase,
)
from src.modules.users.dependencies import (
    get_change_self_password_uc,
    get_change_self_username_uc,
    get_hard_delete_user_uc,
    get_register_user_uc,
    get_reset_user_password_uc,
    get_restore_user_uc,
    get_soft_delete_user_uc,
    get_update_self_profile_uc,
    get_update_user_uc,
    get_user_query_service,
)
from src.modules.users.domain import UserNotFoundError
from src.modules.users.queries import (
    UserDetailDTO,
    UserFilterDTO,
    UserQueryService,
    UserResponseDTO,
    UserShortDTO,
    UserShortSortField,
    UserSortField,
)

users_router = APIRouter(prefix="/users", tags=["Users"])


async def get_user_filters(
    search: Annotated[str | None, Query(description="Пошуковий рядок (username або ПІБ)")] = None,
    ids: Annotated[set[UUID] | None, Query(description="Фільтр за списком ID користувачів")] = None,
    role_ids: Annotated[set[UUID] | None, Query(description="Фільтр за списком ID ролей")] = None,
    roles: Annotated[set[str] | None, Query(description="Фільтр за списком кодів ролей (наприклад, 'admin')")] = None,
    min_created_at: Annotated[date | None, Query(description="Початкова дата створення (РРРР-ММ-ДД)")] = None,
    max_created_at: Annotated[date | None, Query(description="Кінцева дата створення (РРРР-ММ-ДД)")] = None,
    include_inactive: Annotated[bool, Query(description="Включити деактивованих користувачів")] = False,
) -> UserFilterDTO:
    try:
        return UserFilterDTO(
            ids=ids,
            role_ids=role_ids,
            roles=roles,
            search=search,
            min_created_at=min_created_at,
            max_created_at=max_created_at,
            include_inactive=include_inactive,
        )
    except ValidationError as exc:
        raise RequestValidationError(errors=exc.errors()) from exc


@users_router.get("/short", response_model=PaginatedResponse[UserShortDTO])
@cache(namespace=settings.cache.namespace.users, key_builder=default_key_builder)
async def get_users_short_list(
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_READ_SHORT))],
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[
        MultiSort[UserShortSortField],
        Depends(sort_dependency(UserShortSortField, default=("name",), max_fields=2)),
    ],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
    search: Annotated[str | None, Query(description="Пошук за username/name")] = None,
    exclude_current_user: Annotated[bool, Query(description="Виключити поточного користувача зі списку")] = False,
) -> PaginatedResponse[UserShortDTO]:
    """Отримання скороченого списку користувачів (для селектів та швидкого пошуку)."""
    filters = UserFilterDTO(
        search=search,
        include_inactive=False,
        exclude_user_id=current_user.id if exclude_current_user else None,
    )
    return await user_queries.get_short_list(pagination=pagination, sort=sort, filters=filters)


@users_router.patch("/me", response_model=UserDetailDTO)
async def update_self_profile(
    dto: UpdateSelfProfileDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_SELF_UPDATE))],
    update_self_uc: Annotated[UpdateSelfProfileUseCase, Depends(get_update_self_profile_uc)],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserDetailDTO:
    """Оновлення власного профілю поточним автентифікованим користувачем."""
    await update_self_uc.execute(current_user, dto)
    updated_user = await user_queries.get_detail_by_id(current_user.id)
    if not updated_user:
        raise DataInconsistencyException("Помилка отримання даних щойно оновленого профілю.")
    return updated_user


@users_router.post("/me/change-password", response_model=UserActionStatusDTO)
async def change_self_password(
    dto: ChangeSelfPasswordDTO,
    request: Request,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_SELF_PASSWORD_UPDATE))],
    change_pw_uc: Annotated[ChangeSelfPasswordUseCase, Depends(get_change_self_password_uc)],
) -> UserActionStatusDTO:
    """
    Зміна власного пароля автентифікованим користувачем.
    При зміні пароля всі активні сесії користувача анулюються та очищуються Cookies.
    """
    await change_pw_uc.execute(current_user, dto)
    secure = is_secure_request(request)
    clear_auth_cookies(response, secure=secure)
    return UserActionStatusDTO(status="password_changed")


@users_router.post("/me/change-username", response_model=UserActionStatusDTO)
async def change_self_username(
    dto: ChangeSelfUsernameDTO,
    request: Request,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_SELF_USERNAME_UPDATE))],
    change_uname_uc: Annotated[ChangeSelfUsernameUseCase, Depends(get_change_self_username_uc)],
) -> UserActionStatusDTO:
    """
    Зміна власного логіна автентифікованим користувачем.
    При зміні логіна всі активні сесії користувача анулюються та очищуються Cookies.
    """
    await change_uname_uc.execute(current_user, dto)
    secure = is_secure_request(request)
    clear_auth_cookies(response, secure=secure)
    return UserActionStatusDTO(status="username_changed")


@users_router.get("", response_model=PaginatedResponse[UserResponseDTO])
@cache(namespace=settings.cache.namespace.users, key_builder=default_key_builder)
async def list_users(
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_READ))],
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[
        MultiSort[UserSortField],
        Depends(sort_dependency(UserSortField, default=("-created_at",), max_fields=3)),
    ],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
    filters: Annotated[UserFilterDTO, Depends(get_user_filters)],
    exclude_current_user: Annotated[
        bool, Query(description="Виключити поточного авторизованого користувача зі списку")
    ] = False,
) -> PaginatedResponse[UserResponseDTO]:
    """Отримання пагінованого списку користувачів із фільтрацією та сортуванням."""
    if exclude_current_user:
        filters.exclude_user_id = current_user.id
    return await user_queries.get_all(pagination=pagination, sort=sort, filters=filters)


@users_router.get("/{user_id}", response_model=UserDetailDTO)
@cache(namespace=settings.cache.namespace.users, key_builder=resource_key_builder)
async def get_user_by_id(
    user_id: UUID,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_READ))],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserDetailDTO:
    """Отримання детальної інформації про користувача, включаючи персональні права."""
    user = await user_queries.get_detail_by_id(user_id)
    if not user:
        raise UserNotFoundError(f"Користувача з ID '{user_id}' не знайдено.")
    return user


@users_router.post("", response_model=UserDetailDTO, status_code=status.HTTP_201_CREATED)
async def register_user(
    dto: CreateUserDTO,
    _: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_CREATE))],
    register_uc: Annotated[RegisterUserUseCase, Depends(get_register_user_uc)],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserDetailDTO:
    """Реєстрація нового користувача системи."""
    new_user_id = await register_uc.execute(dto)
    created_user = await user_queries.get_detail_by_id(new_user_id)
    if not created_user:
        raise DataInconsistencyException("Помилка отримання даних щойно зареєстрованого користувача.")
    return created_user


@users_router.put("/{user_id}", response_model=UserDetailDTO)
async def update_user(
    user_id: UUID,
    dto: UpdateUserDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_UPDATE))],
    update_uc: Annotated[UpdateUserUseCase, Depends(get_update_user_uc)],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserDetailDTO:
    """
    Повне оновлення даних користувача (Full PUT).
    Вимагає обов'язкової передачі OCC поля version.
    """
    await update_uc.execute(
        user_id,
        dto,
        actor=current_user,
    )
    updated_user = await user_queries.get_detail_by_id(user_id)
    if not updated_user:
        raise DataInconsistencyException(
            f"Помилка узгодженості даних: користувача з ID '{user_id}' не знайдено після оновлення."
        )
    return updated_user


@users_router.post("/{user_id}/reset-password", response_model=UserActionStatusDTO)
async def reset_user_password(
    user_id: UUID,
    dto: ResetUserPasswordDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_PASSWORD_UPDATE))],
    reset_pw_uc: Annotated[ResetUserPasswordUseCase, Depends(get_reset_user_password_uc)],
) -> UserActionStatusDTO:
    """Примусове скидання пароля користувача адміністратором."""
    await reset_pw_uc.execute(
        user_id,
        dto,
        actor=current_user,
    )
    return UserActionStatusDTO(status="password_reset")


@users_router.patch("/{user_id}/deactivate", response_model=UserDetailDTO)
async def deactivate_user(
    user_id: UUID,
    dto: SoftDeleteUserDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_DEACTIVATE))],
    soft_delete_uc: Annotated[SoftDeleteUserUseCase, Depends(get_soft_delete_user_uc)],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserDetailDTO:
    """М'яке видалення (деактивація) користувача через PATCH (встановлює deleted_at)."""
    await soft_delete_uc.execute(user_id, dto, actor=current_user)
    user = await user_queries.get_detail_by_id(user_id)
    if not user:
        raise DataInconsistencyException(
            f"Помилка узгодженості даних: користувача з ID '{user_id}' не знайдено після деактивації."
        )
    return user


@users_router.patch("/{user_id}/restore", response_model=UserDetailDTO)
async def restore_user(
    user_id: UUID,
    dto: RestoreUserDTO,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_RESTORE))],
    restore_uc: Annotated[RestoreUserUseCase, Depends(get_restore_user_uc)],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> UserDetailDTO:
    """Відновлення раніше деактивованого користувача через PATCH (скидає deleted_at)."""
    await restore_uc.execute(
        user_id,
        dto,
        actor=current_user,
    )
    user = await user_queries.get_detail_by_id(user_id)
    if not user:
        raise DataInconsistencyException(
            f"Помилка узгодженості даних: користувача з ID '{user_id}' не знайдено після відновлення."
        )
    return user


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete_user(
    user_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_DELETE))],
    hard_delete_uc: Annotated[HardDeleteUserUseCase, Depends(get_hard_delete_user_uc)],
) -> None:
    """
    Фізичне видалення користувача з БД (Hard Delete).
    Дозволено для будь-яких користувачів (активних або деактивованих), крім системного SuperAdmin.
    """
    await hard_delete_uc.execute(user_id, actor=current_user)


@users_router.get("/{user_id}/delete-preview", response_model=DeletionAssessmentDTO)
async def preview_user_deletion(
    user_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission(PermissionCode.USERS_DELETE))],
    user_queries: Annotated[UserQueryService, Depends(get_user_query_service)],
) -> DeletionAssessmentDTO:
    """Аналіз можливості видалення користувача (Hard vs Soft delete vs Blocked)."""
    return await user_queries.assess_deletion(user_id, current_user_id=current_user.id)
