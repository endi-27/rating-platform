from typing import Any

import pytest
from httpx import AsyncClient

from src.core import settings
from src.modules.users.infrastructure.models import UserModel


@pytest.mark.asyncio
async def test_login_success(
    api_client: AsyncClient,
    superadmin_user: UserModel,
) -> None:
    """Перевірка успішної автентифікації за логіном і паролем (200 OK) з видачею HttpOnly Cookies."""
    payload = {
        "username": settings.seed.superadmin_username,
        "password": settings.seed.superadmin_password,
        "is_remember_me": True,
    }
    response = await api_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(superadmin_user.id)
    assert data["username"] == settings.seed.superadmin_username.lower()
    assert "role" in data
    assert "effective_permissions" in data

    # Перевірка наявності встановлених Cookies
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies

    # Перевірка директив безпеки у заголовках Set-Cookie (HttpOnly, SameSite)
    set_cookie_headers = response.headers.get_list("set-cookie")
    set_cookie_str = " ".join(set_cookie_headers).lower()
    assert "httponly" in set_cookie_str
    assert "samesite=lax" in set_cookie_str


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_401(api_client: AsyncClient) -> None:
    """Перевірка помилки 401 Unauthorized при невірному паролі або неіснуючому логіні."""
    # 1. Невірний пароль для існуючого користувача
    bad_pw_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.seed.superadmin_username,
            "password": "WrongPassword123!",
        },
    )
    assert bad_pw_response.status_code == 401
    assert bad_pw_response.json()["error_code"] in ("UNAUTHORIZED", "INVALID_CREDENTIALS")

    # 2. Неіснуючий користувач
    bad_user_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "non_existent_user_999",
            "password": "SomePassword123!",
        },
    )
    assert bad_user_response.status_code == 401
    assert bad_user_response.json()["error_code"] in ("UNAUTHORIZED", "INVALID_CREDENTIALS")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"username": "ab", "password": "ValidPassword123!"},  # username < 3 chars
        {"username": "valid_user", "password": "short"},  # password < 8 chars
        {"username": "", "password": ""},  # empty fields
        {},  # missing fields
        {
            "username": settings.seed.superadmin_username,
            "password": settings.seed.superadmin_password,
            "extra_forbidden": "unexpected",
        },  # extra fields forbidden
    ],
)
async def test_login_validation_errors_return_422(
    api_client: AsyncClient,
    invalid_payload: dict[str, Any],
) -> None:
    """Перевірка повернення 422 Unprocessable Entity при невалідних вхідних даних логіна."""
    response = await api_client.post("/api/v1/auth/login", json=invalid_payload)
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_refresh_token_success(api_client: AsyncClient) -> None:
    """Перевірка успішної ротації пари токенів через сесійне Cookie refresh_token."""
    # Спочатку виконуємо логін для отримання початкової пари токенів
    login_resp = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.seed.superadmin_username,
            "password": settings.seed.superadmin_password,
        },
    )
    assert login_resp.status_code == 200
    initial_refresh = login_resp.cookies.get("refresh_token")
    assert initial_refresh is not None

    # Викликаємо ротацію токенів
    refresh_resp = await api_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": initial_refresh},
    )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert data["status"] == "refreshed"

    # Перевіряємо, що встановлено нові cookies
    new_refresh = refresh_resp.cookies.get("refresh_token")
    assert new_refresh is not None
    assert new_refresh != initial_refresh
    assert "access_token" in refresh_resp.cookies


@pytest.mark.asyncio
async def test_refresh_token_missing_cookie_returns_401(api_client: AsyncClient) -> None:
    """Перевірка помилки 401 Unauthorized при виклику ротації без refresh_token cookie."""
    response = await api_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_refresh_token_invalid_or_stale_token_returns_401(api_client: AsyncClient) -> None:
    """Перевірка помилки 401 Unauthorized при передачі недійсного чи скомпрометованого refresh токена."""
    response = await api_client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": "a" * 64},  # валідна довжина, але відсутній у БД
    )
    assert response.status_code == 401
    assert response.json()["error_code"] in ("UNAUTHORIZED", "INVALID_TOKEN")


@pytest.mark.asyncio
async def test_logout_success_and_idempotency(api_client: AsyncClient) -> None:
    """Перевірка виходу з системи (видалення cookies) та ідемпотентності endpoint logout."""
    # 1. Логін
    login_resp = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.seed.superadmin_username,
            "password": settings.seed.superadmin_password,
        },
    )
    assert login_resp.status_code == 200

    # 2. Перший вихід із валідними cookies
    logout_resp = await api_client.post(
        "/api/v1/auth/logout",
        cookies={
            "access_token": login_resp.cookies["access_token"],
            "refresh_token": login_resp.cookies["refresh_token"],
        },
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "logged_out"

    # Перевірка очищення cookie (max-age=0 або порожнє значення)
    set_cookies = " ".join(logout_resp.headers.get_list("set-cookie")).lower()
    assert "max-age=0" in set_cookies or 'access_token=""' in set_cookies

    # 3. Ідемпотентний виклик без cookies (повинен повернути 200 OK)
    repeat_logout = await api_client.post("/api/v1/auth/logout")
    assert repeat_logout.status_code == 200
    assert repeat_logout.json()["status"] == "logged_out"


@pytest.mark.asyncio
async def test_get_me_success_with_cookies(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
) -> None:
    """Перевірка отримання профілю поточного автентифікованого користувача (200 OK)."""
    response = await api_client.get("/api/v1/auth/me", cookies=superadmin_cookies)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(superadmin_user.id)
    assert data["username"] == settings.seed.superadmin_username.lower()
    assert "effective_permissions" in data
    assert "users:read" in data["effective_permissions"]


@pytest.mark.asyncio
async def test_get_me_unauthorized_without_cookies(api_client: AsyncClient) -> None:
    """Перевірка повернення 401 при запиті /auth/me без Cookies."""
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_me_unauthorized_with_invalid_token(api_client: AsyncClient) -> None:
    """Перевірка повернення 401 при недійсному токені у Cookie."""
    response = await api_client.get(
        "/api/v1/auth/me",
        cookies={"access_token": "malformed.invalid.jwt.token"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"
