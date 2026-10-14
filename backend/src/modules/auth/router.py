from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.core import CurrentUser, UnauthorizedException
from src.modules.auth.application.dto import (
    LoginDTO,
    LogoutDTO,
    RefreshTokenDTO,
    StatusResponseDTO,
)
from src.modules.auth.application.use_cases import (
    AuthenticateUserUseCase,
    LogoutUseCase,
    RefreshTokenUseCase,
)
from src.modules.auth.cookies import (
    clear_auth_cookies,
    is_secure_request,
    set_access_cookie,
    set_refresh_cookie,
)
from src.modules.auth.dependencies import (
    get_authenticate_user_uc,
    get_current_user,
    get_current_user_optional,
    get_logout_uc,
    get_refresh_token_uc,
    get_users_gateway,
)
from src.modules.auth.domain import AuthOperationStatus, IUserAuthGateway

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/login")
async def login(
    dto: LoginDTO,
    request: Request,
    response: Response,
    auth_uc: Annotated[AuthenticateUserUseCase, Depends(get_authenticate_user_uc)],
    users_gateway: Annotated[IUserAuthGateway, Depends(get_users_gateway)],
) -> CurrentUser:
    """
    Автентифікація користувача за логіном та паролем (Cookie-only).
    Встановлює HttpOnly access_token та refresh_token у браузерні cookies.
    """
    ip_address = request.client.host if request.client else None
    result = await auth_uc.execute(dto, ip_address=ip_address)

    secure = is_secure_request(request)
    set_access_cookie(response, result.access_token, is_remember_me=result.is_remember_me, secure=secure)
    set_refresh_cookie(response, result.refresh_token, is_remember_me=result.is_remember_me, secure=secure)

    user = await users_gateway.get_cached_current_user(result.user_id)
    if not user:
        raise UnauthorizedException("Користувача не знайдено.")
    return user


@auth_router.post("/refresh")
async def refresh_tokens(
    request: Request,
    response: Response,
    refresh_uc: Annotated[RefreshTokenUseCase, Depends(get_refresh_token_uc)],
    current_user: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
) -> StatusResponseDTO:
    """
    Ротація сесійного Refresh токена та оновлення Access токена.
    Читає старий refresh_token з Cookie, анулює його та встановлює нову пару.
    """
    token = request.cookies.get("refresh_token")
    if not token:
        raise UnauthorizedException("Refresh токен відсутній у запиті.")

    user_id = current_user.id if current_user else None
    username = current_user.username if current_user else None
    ip_address = request.client.host if request.client else None

    dto = RefreshTokenDTO(refresh_token=token)
    result = await refresh_uc.execute(
        dto,
        ip_address=ip_address,
        user_id=user_id,
        username=username,
    )

    secure = is_secure_request(request)
    set_access_cookie(response, result.access_token, is_remember_me=result.is_remember_me, secure=secure)
    set_refresh_cookie(response, result.refresh_token, is_remember_me=result.is_remember_me, secure=secure)

    return StatusResponseDTO(status=AuthOperationStatus.REFRESHED)


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    response: Response,
    logout_uc: Annotated[LogoutUseCase, Depends(get_logout_uc)],
    current_user: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
) -> StatusResponseDTO:
    """
    Вихід із системи: анулювання сесійного refresh токена та видалення Cookies.
    """
    token = request.cookies.get("refresh_token")
    user_id = current_user.id if current_user else None
    username = current_user.username if current_user else None
    ip_address = request.client.host if request.client else None

    if token or user_id:
        dto = LogoutDTO(refresh_token=token)
        await logout_uc.execute(
            dto,
            ip_address=ip_address,
            user_id=user_id,
            username=username,
        )

    secure = is_secure_request(request)
    clear_auth_cookies(response, secure=secure)

    return StatusResponseDTO(status=AuthOperationStatus.LOGGED_OUT)


@auth_router.get("/me")
async def get_me(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """
    Отримання актуальних даних профілю поточного автентифікованого користувача.
    """
    return current_user
