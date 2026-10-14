from uuid import UUID

import pytest
from httpx import AsyncClient
from uuid6 import uuid7


@pytest.mark.asyncio
async def test_list_permissions_success(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка отримання списку системних дозволів (200 OK) з пагінацією та фільтрами."""
    # 1. Базовий запит зі значеннями за замовчуванням
    response = await api_client.get("/api/v1/permissions", cookies=superadmin_cookies)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] > 0
    assert len(data["items"]) > 0

    first_item = data["items"][0]
    assert "id" in first_item
    assert "code" in first_item
    assert "name" in first_item

    # 2. Фільтрація за пошуковим словом search
    search_resp = await api_client.get(
        "/api/v1/permissions?search=users",
        cookies=superadmin_cookies,
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] > 0
    for perm in search_data["items"]:
        assert "users" in perm["code"].lower() or "users" in perm["name"].lower()

    # 3. Фільтрація за конкретними кодами
    codes_resp = await api_client.get(
        "/api/v1/permissions?codes=users:read&codes=roles:read",
        cookies=superadmin_cookies,
    )
    assert codes_resp.status_code == 200
    codes_data = codes_resp.json()
    returned_codes = {p["code"] for p in codes_data["items"]}
    assert returned_codes.issubset({"users:read", "roles:read"})

    # 4. Сортування та пагінація
    sort_resp = await api_client.get(
        "/api/v1/permissions?sort=code&page=1&page_size=5",
        cookies=superadmin_cookies,
    )
    assert sort_resp.status_code == 200
    sort_data = sort_resp.json()
    assert len(sort_data["items"]) <= 5
    codes_list = [p["code"] for p in sort_data["items"]]
    assert codes_list == sorted(codes_list)


@pytest.mark.asyncio
async def test_list_permissions_unauthorized_returns_401(api_client: AsyncClient) -> None:
    """Перевірка помилки 401 при спробі отримати список дозволів без автентифікації."""
    response = await api_client.get("/api/v1/permissions")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_list_permissions_forbidden_returns_403(
    api_client: AsyncClient,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка помилки 403 при відсутності системного права PERMISSIONS_READ."""
    response = await api_client.get("/api/v1/permissions", cookies=no_permissions_cookies)
    assert response.status_code == 403
    assert response.json()["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_list_permissions_validation_error_returns_422(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка повернення 422 при некоректних параметрах сортування або пагінації."""
    # Невалідний стовпець сортування
    bad_sort = await api_client.get("/api/v1/permissions?sort=invalid_field", cookies=superadmin_cookies)
    assert bad_sort.status_code == 422
    assert bad_sort.json()["error_code"] in ("VALIDATION_ERROR", "INVALID_SORT_FIELD")

    # Невалідна пагінація (page < 1 або page_size < 1)
    bad_page = await api_client.get("/api/v1/permissions?page=0", cookies=superadmin_cookies)
    assert bad_page.status_code == 422
    assert bad_page.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_permission_by_id_success(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка отримання детальної інформації про дозвіл за його ID (200 OK)."""
    # 1. Отримуємо дозвіл зі списку
    list_resp = await api_client.get("/api/v1/permissions", cookies=superadmin_cookies)
    first_perm = list_resp.json()["items"][0]
    perm_id = first_perm["id"]

    # 2. Запитуємо дозвіл за ID
    response = await api_client.get(f"/api/v1/permissions/{perm_id}", cookies=superadmin_cookies)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == perm_id
    assert data["code"] == first_perm["code"]
    assert data["name"] == first_perm["name"]


@pytest.mark.asyncio
async def test_get_permission_by_id_not_found_returns_404(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка повернення 404 Not Found для неіснуючого permission_id."""
    random_id = uuid7()
    response = await api_client.get(f"/api/v1/permissions/{random_id}", cookies=superadmin_cookies)
    assert response.status_code == 404
    assert response.json()["error_code"] == "PERMISSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_permission_by_id_unauthorized_returns_401(api_client: AsyncClient) -> None:
    """Перевірка повернення 401 при запиті дозволу за ID без Cookies."""
    response = await api_client.get(f"/api/v1/permissions/{uuid7()}")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_permission_by_id_forbidden_returns_403(
    api_client: AsyncClient,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка повернення 403 при запиті дозволу користувачем без права PERMISSIONS_READ."""
    response = await api_client.get(f"/api/v1/permissions/{uuid7()}", cookies=no_permissions_cookies)
    assert response.status_code == 403
    assert response.json()["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_permission_by_id_invalid_uuid_returns_422(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка повернення 422 при передачі невалідного рядка замість UUID."""
    response = await api_client.get("/api/v1/permissions/not-a-valid-uuid", cookies=superadmin_cookies)
    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_permission_by_code_success(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка отримання опису дозволу за його унікальним рядковим кодом (200 OK)."""
    response = await api_client.get("/api/v1/permissions/by-code/users:read", cookies=superadmin_cookies)
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "users:read"
    assert "name" in data
    assert UUID(data["id"]) is not None


@pytest.mark.asyncio
async def test_get_permission_by_code_not_found_returns_404(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка повернення 404 Not Found для неіснуючого коду дозволу."""
    response = await api_client.get(
        "/api/v1/permissions/by-code/non_existent_code_xyz",
        cookies=superadmin_cookies,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "PERMISSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_permission_by_code_unauthorized_returns_401(api_client: AsyncClient) -> None:
    """Перевірка повернення 401 при запиті дозволу за кодом без Cookies."""
    response = await api_client.get("/api/v1/permissions/by-code/users:read")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_permission_by_code_forbidden_returns_403(
    api_client: AsyncClient,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка повернення 403 при запиті дозволу за кодом без права PERMISSIONS_READ."""
    response = await api_client.get(
        "/api/v1/permissions/by-code/users:read",
        cookies=no_permissions_cookies,
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "FORBIDDEN"
