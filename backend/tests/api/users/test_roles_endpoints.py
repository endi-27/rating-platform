from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.core import default_password_hasher
from src.modules.users.infrastructure.models import RoleModel, UserModel


@pytest.mark.asyncio
async def test_list_roles_success(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка отримання списку ролей (200 OK) з пагінацією, фільтрацією та сортуванням."""
    # 1. Запит за замовчуванням (super_admin виключений за дизайном, повертається viewer)
    response = await api_client.get("/api/v1/roles", cookies=superadmin_cookies)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] >= 1
    codes = [r["code"] for r in data["items"]]
    assert "viewer" in codes

    # 2. Фільтрація за пошуковим словом search
    search_resp = await api_client.get("/api/v1/roles?search=viewer", cookies=superadmin_cookies)
    assert search_resp.status_code == 200
    search_items = search_resp.json()["items"]
    assert any(r["code"] == "viewer" for r in search_items)

    # 3. Фільтрація за кодами
    codes_resp = await api_client.get("/api/v1/roles?codes=viewer", cookies=superadmin_cookies)
    assert codes_resp.status_code == 200
    assert len(codes_resp.json()["items"]) == 1
    assert codes_resp.json()["items"][0]["code"] == "viewer"

    # 4. Сортування за назвою
    sort_resp = await api_client.get("/api/v1/roles?sort=name&page=1&page_size=10", cookies=superadmin_cookies)
    assert sort_resp.status_code == 200
    names = [r["name"] for r in sort_resp.json()["items"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_roles_unauthorized_and_forbidden(
    api_client: AsyncClient,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка 401 Unauthorized та 403 Forbidden при отриманні списку ролей."""
    # 401 без cookies
    resp_401 = await api_client.get("/api/v1/roles")
    assert resp_401.status_code == 401
    assert resp_401.json()["error_code"] == "UNAUTHORIZED"

    # 403 без права ROLES_READ
    resp_403 = await api_client.get("/api/v1/roles", cookies=no_permissions_cookies)
    assert resp_403.status_code == 403
    assert resp_403.json()["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_role_by_id_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    viewer_role: RoleModel,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка отримання ролі за ID: 200 OK, 404, 401, 403, 422."""
    # 1. 200 OK
    resp_200 = await api_client.get(f"/api/v1/roles/{viewer_role.id}", cookies=superadmin_cookies)
    assert resp_200.status_code == 200
    data = resp_200.json()
    assert data["id"] == str(viewer_role.id)
    assert data["code"] == "viewer"
    assert "permissions" in data

    # 2. 404 Not Found
    random_id = uuid7()
    resp_404 = await api_client.get(f"/api/v1/roles/{random_id}", cookies=superadmin_cookies)
    assert resp_404.status_code == 404
    assert resp_404.json()["error_code"] == "ROLE_NOT_FOUND"

    # 3. 401 Unauthorized
    resp_401 = await api_client.get(f"/api/v1/roles/{viewer_role.id}")
    assert resp_401.status_code == 401

    # 4. 403 Forbidden
    resp_403 = await api_client.get(f"/api/v1/roles/{viewer_role.id}", cookies=no_permissions_cookies)
    assert resp_403.status_code == 403

    # 5. 422 Unprocessable Entity
    resp_422 = await api_client.get("/api/v1/roles/not-a-uuid", cookies=superadmin_cookies)
    assert resp_422.status_code == 422


@pytest.mark.asyncio
async def test_create_role_lifecycle_and_errors(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка створення ролі (201 Created), дублікатів (409), захисту super_admin та валідації (422)."""
    unique_code = f"manager_{uuid7().hex[:6]}"
    payload: dict[str, Any] = {
        "code": unique_code,
        "name": "Менеджер підрозділу",
        "description": "Тестовий опис ролі",
        "permission_ids": [],
    }

    # 1. 201 Created
    create_resp = await api_client.post("/api/v1/roles", json=payload, cookies=superadmin_cookies)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["code"] == unique_code
    assert created_data["name"] == "Менеджер підрозділу"
    assert created_data["version"] == 1

    # 2. 409 Conflict на повторне створення ролі з тим самим кодом
    duplicate_resp = await api_client.post("/api/v1/roles", json=payload, cookies=superadmin_cookies)
    assert duplicate_resp.status_code == 409
    assert duplicate_resp.json()["error_code"] == "ROLE_ALREADY_EXISTS"

    # 3. Захист системного коду super_admin (403/409)
    superadmin_payload = {
        "code": "super_admin",
        "name": "Another Super Admin",
        "permission_ids": [],
    }
    superadmin_resp = await api_client.post("/api/v1/roles", json=superadmin_payload, cookies=superadmin_cookies)
    assert superadmin_resp.status_code in (403, 409)
    assert superadmin_resp.json()["error_code"] in ("SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 4. 422 Unprocessable Entity (невалідний код: snake_case з дефісом або великими літерами)
    bad_code_resp = await api_client.post(
        "/api/v1/roles",
        json={"code": "invalid-code-format", "name": "Bad Role", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert bad_code_resp.status_code == 422
    assert bad_code_resp.json()["error_code"] == "VALIDATION_ERROR"

    # 5. 422 Unprocessable Entity (порожня назва ролі)
    bad_name_resp = await api_client.post(
        "/api/v1/roles",
        json={"code": f"valid_code_{uuid7().hex[:4]}", "name": "", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert bad_name_resp.status_code == 422

    # 6. 401 та 403
    unauth_resp = await api_client.post("/api/v1/roles", json={"code": "auth_test", "name": "Auth Test"})
    assert unauth_resp.status_code == 401

    forbid_resp = await api_client.post(
        "/api/v1/roles",
        json={"code": "forbid_test", "name": "Forbid Test"},
        cookies=no_permissions_cookies,
    )
    assert forbid_resp.status_code == 403


@pytest.mark.asyncio
async def test_update_role_success_and_conflicts(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
) -> None:
    """Перевірка повного оновлення ролі (200 OK, 404, 409 OCC, захист super_admin, 422)."""
    # 1. Створюємо окрему роль для тесту оновлення
    code = f"upd_role_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/roles",
        json={"code": code, "name": "Початкова назва", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert create_resp.status_code == 201
    role_id = create_resp.json()["id"]

    # 2. Успішне оновлення (200 OK)
    upd_payload = {
        "version": 1,
        "name": "Оновлена назва ролі",
        "description": "Новий змістовний опис",
        "permission_ids": [],
    }
    upd_resp = await api_client.put(f"/api/v1/roles/{role_id}", json=upd_payload, cookies=superadmin_cookies)
    assert upd_resp.status_code == 200
    upd_data = upd_resp.json()
    assert upd_data["name"] == "Оновлена назва ролі"
    assert upd_data["version"] == 2

    # 3. Конфлікт версії OCC (409 Conflict): передаємо стару version=1
    occ_resp = await api_client.put(f"/api/v1/roles/{role_id}", json=upd_payload, cookies=superadmin_cookies)
    assert occ_resp.status_code == 409
    assert occ_resp.json()["error_code"] == "OPTIMISTIC_LOCK_CONFLICT"

    # 4. 404 Not Found
    resp_404 = await api_client.put(
        f"/api/v1/roles/{uuid7()}",
        json={"version": 1, "name": "Non existent", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert resp_404.status_code == 404
    assert resp_404.json()["error_code"] == "ROLE_NOT_FOUND"

    # 5. Захист системної ролі super_admin (403/409 Conflict)
    sa_resp = await api_client.put(
        f"/api/v1/roles/{superadmin_user.role_id}",
        json={"version": 1, "name": "Super Admin Hack", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert sa_resp.status_code in (403, 409)
    assert sa_resp.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 6. 422 Unprocessable Entity (відсутнє обов'язкове поле version)
    bad_payload = {"name": "No Version", "permission_ids": []}
    resp_422 = await api_client.put(f"/api/v1/roles/{role_id}", json=bad_payload, cookies=superadmin_cookies)
    assert resp_422.status_code == 422


@pytest.mark.asyncio
async def test_deactivate_and_restore_role_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
) -> None:
    """Перевірка життєвого циклу деактивації та відновлення ролі (PATCH /deactivate, PATCH /restore)."""
    # 1. Створюємо роль
    code = f"lifecycle_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/roles",
        json={"code": code, "name": "Роль для деактивації", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert create_resp.status_code == 201
    role_id = create_resp.json()["id"]

    # 2. Деактивація (200 OK)
    deact_resp = await api_client.patch(
        f"/api/v1/roles/{role_id}/deactivate",
        json={"version": 1},
        cookies=superadmin_cookies,
    )
    assert deact_resp.status_code == 200
    deact_data = deact_resp.json()
    assert deact_data["deleted_at"] is not None
    assert deact_data["version"] == 2

    # 3. 400/409 Conflict при повторній деактивації вже неактивної ролі
    repeat_deact = await api_client.patch(
        f"/api/v1/roles/{role_id}/deactivate",
        json={"version": 2},
        cookies=superadmin_cookies,
    )
    assert repeat_deact.status_code in (400, 409)
    assert repeat_deact.json()["error_code"] in (
        "ALREADY_INACTIVE",
        "BAD_REQUEST",
        "RESOURCE_ALREADY_INACTIVE",
        "CONFLICT",
    )

    # 4. Відновлення ролі (200 OK)
    restore_resp = await api_client.patch(
        f"/api/v1/roles/{role_id}/restore",
        json={"version": 2},
        cookies=superadmin_cookies,
    )
    assert restore_resp.status_code == 200
    restore_data = restore_resp.json()
    assert restore_data["deleted_at"] is None
    assert restore_data["version"] == 3

    # 5. 400/409 Conflict при відновленні вже активної ролі
    repeat_restore = await api_client.patch(
        f"/api/v1/roles/{role_id}/restore",
        json={"version": 3},
        cookies=superadmin_cookies,
    )
    assert repeat_restore.status_code in (400, 409)
    assert repeat_restore.json()["error_code"] in (
        "ALREADY_ACTIVE",
        "BAD_REQUEST",
        "RESOURCE_ALREADY_ACTIVE",
        "CONFLICT",
    )

    # 6. Захист super_admin від деактивації (403/409 Conflict)
    sa_deact = await api_client.patch(
        f"/api/v1/roles/{superadmin_user.role_id}/deactivate",
        json={"version": 1},
        cookies=superadmin_cookies,
    )
    assert sa_deact.status_code in (403, 409)
    assert sa_deact.json()["error_code"] in (
        "SUPER_ADMIN_PROTECTED",
        "CONFLICT",
        "SELF_ROLE_FORBIDDEN",
        "SELF_ACTION_FORBIDDEN",
    )


@pytest.mark.asyncio
async def test_delete_role_and_preview_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    db_session: AsyncSession,
) -> None:
    """Перевірка видалення ролі (DELETE /roles/{id}) та оцінки наслідків (GET /roles/{id}/delete-preview)."""
    # 1. Створюємо роль, не прив'язану до жодних користувачів
    code = f"del_role_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/roles",
        json={"code": code, "name": "Роль для видалення", "permission_ids": []},
        cookies=superadmin_cookies,
    )
    assert create_resp.status_code == 201
    role_id = create_resp.json()["id"]

    # 2. Оцінка наслідків видалення (delete-preview -> HARD_DELETE)
    prev_resp = await api_client.get(f"/api/v1/roles/{role_id}/delete-preview", cookies=superadmin_cookies)
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["action"] == "hard_delete"
    assert len(prev_data["dependencies"]) == 0

    # 3. Фізичне видалення ролі (204 No Content)
    del_resp = await api_client.delete(f"/api/v1/roles/{role_id}", cookies=superadmin_cookies)
    assert del_resp.status_code == 204

    # Переконуємося, що роль більше не існує
    get_after_del = await api_client.get(f"/api/v1/roles/{role_id}", cookies=superadmin_cookies)
    assert get_after_del.status_code == 404

    # 4. Спроба видалити неіснуючу роль (404 Not Found)
    del_404 = await api_client.delete(f"/api/v1/roles/{uuid7()}", cookies=superadmin_cookies)
    assert del_404.status_code == 404

    # 5. Спроба видалити роль super_admin (403/409 Conflict)
    sa_del = await api_client.delete(f"/api/v1/roles/{superadmin_user.role_id}", cookies=superadmin_cookies)
    assert sa_del.status_code in (403, 409)
    assert sa_del.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 6. Конфлікт при спробі видалити роль, призначену користувачам (409 Conflict)
    assigned_role = RoleModel(
        id=uuid7(),
        code=f"assigned_{uuid7().hex[:6]}",
        name="Assigned Role",
        version=1,
    )
    db_session.add(assigned_role)
    user_with_role = UserModel(
        id=uuid7(),
        version=1,
        username=f"assigned_user_{uuid7().hex[:6]}",
        name="Assigned User",
        password_hash=default_password_hasher.hash("TestPass123!"),
        role_id=assigned_role.id,
    )
    db_session.add(user_with_role)
    await db_session.flush()

    # Оцінка видалення для ролі з користувачами
    assigned_prev = await api_client.get(
        f"/api/v1/roles/{assigned_role.id}/delete-preview",
        cookies=superadmin_cookies,
    )
    assert assigned_prev.status_code == 200
    assert assigned_prev.json()["action"] == "deactivate"
    assert assigned_prev.json()["dependencies"][0]["entity_type"] == "users"

    # Спроба видалення повертає 409 Conflict
    assigned_del = await api_client.delete(f"/api/v1/roles/{assigned_role.id}", cookies=superadmin_cookies)
    assert assigned_del.status_code == 409
    assert assigned_del.json()["error_code"] in ("ROLE_ASSIGNED_TO_USERS", "RESOURCE_LOCKED", "CONFLICT")
