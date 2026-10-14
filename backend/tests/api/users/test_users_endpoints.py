from typing import Any

import pytest
from httpx import AsyncClient
from uuid6 import uuid7

from src.core import settings
from src.modules.users.infrastructure.models import RoleModel, UserModel


@pytest.mark.asyncio
async def test_list_users_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка отримання списку користувачів (GET /users): 200 OK, фільтрація, 401, 403, 422."""
    # 1. 200 OK базовий запит
    response = await api_client.get("/api/v1/users", cookies=superadmin_cookies)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] >= 1
    usernames = [u["username"] for u in data["items"]]
    assert settings.seed.superadmin_username.lower() in usernames

    # 2. Фільтрація за пошуком search
    search_resp = await api_client.get(
        f"/api/v1/users?search={settings.seed.superadmin_username.lower()}",
        cookies=superadmin_cookies,
    )
    assert search_resp.status_code == 200
    search_items = search_resp.json()["items"]
    assert any(u["username"] == settings.seed.superadmin_username.lower() for u in search_items)

    # 3. Виключення поточного користувача зі списку
    exclude_resp = await api_client.get("/api/v1/users?exclude_current_user=true", cookies=superadmin_cookies)
    assert exclude_resp.status_code == 200
    exclude_items = exclude_resp.json()["items"]
    assert all(u["id"] != str(superadmin_user.id) for u in exclude_items)

    # 4. Сортування
    sort_resp = await api_client.get("/api/v1/users?sort=username&page=1&page_size=10", cookies=superadmin_cookies)
    assert sort_resp.status_code == 200
    sorted_unames = [u["username"] for u in sort_resp.json()["items"]]
    assert sorted_unames == sorted(sorted_unames)

    # 5. 401 Unauthorized
    unauth_resp = await api_client.get("/api/v1/users")
    assert unauth_resp.status_code == 401
    assert unauth_resp.json()["error_code"] == "UNAUTHORIZED"

    # 6. 403 Forbidden
    forbid_resp = await api_client.get("/api/v1/users", cookies=no_permissions_cookies)
    assert forbid_resp.status_code == 403
    assert forbid_resp.json()["error_code"] == "FORBIDDEN"

    # 7. 422 Unprocessable Entity
    bad_page_resp = await api_client.get("/api/v1/users?page=0", cookies=superadmin_cookies)
    assert bad_page_resp.status_code == 422


@pytest.mark.asyncio
async def test_get_users_short_list(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка отримання скороченого списку користувачів (GET /users/short)."""
    # 1. 200 OK
    response = await api_client.get("/api/v1/users/short", cookies=superadmin_cookies)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    first = data["items"][0]
    assert "id" in first
    assert "username" in first
    assert "name" in first

    # 2. Фільтр exclude_current_user
    excl_resp = await api_client.get("/api/v1/users/short?exclude_current_user=true", cookies=superadmin_cookies)
    assert excl_resp.status_code == 200
    assert all(u["id"] != str(superadmin_user.id) for u in excl_resp.json()["items"])

    # 3. 401 Unauthorized
    resp_401 = await api_client.get("/api/v1/users/short")
    assert resp_401.status_code == 401

    # 4. 403 Forbidden
    resp_403 = await api_client.get("/api/v1/users/short", cookies=no_permissions_cookies)
    assert resp_403.status_code == 403


@pytest.mark.asyncio
async def test_get_user_by_id_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка отримання інформації про користувача за ID (GET /users/{id})."""
    # 1. 200 OK
    response = await api_client.get(f"/api/v1/users/{superadmin_user.id}", cookies=superadmin_cookies)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(superadmin_user.id)
    assert data["username"] == settings.seed.superadmin_username.lower()
    assert "role" in data
    assert "custom_permissions" in data

    # 2. 404 Not Found
    resp_404 = await api_client.get(f"/api/v1/users/{uuid7()}", cookies=superadmin_cookies)
    assert resp_404.status_code == 404
    assert resp_404.json()["error_code"] == "USER_NOT_FOUND"

    # 3. 401 Unauthorized
    resp_401 = await api_client.get(f"/api/v1/users/{superadmin_user.id}")
    assert resp_401.status_code == 401

    # 4. 403 Forbidden
    resp_403 = await api_client.get(f"/api/v1/users/{superadmin_user.id}", cookies=no_permissions_cookies)
    assert resp_403.status_code == 403

    # 5. 422 Invalid UUID
    resp_422 = await api_client.get("/api/v1/users/not-a-valid-uuid", cookies=superadmin_cookies)
    assert resp_422.status_code == 422


@pytest.mark.asyncio
async def test_create_user_lifecycle_and_validation(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    viewer_role: RoleModel,
    no_permissions_cookies: dict[str, str],
) -> None:
    """Перевірка реєстрації нового користувача (POST /users), колізій (409) та валідації (422)."""
    uname = f"user_{uuid7().hex[:6]}"
    payload: dict[str, Any] = {
        "username": uname,
        "name": "Новий Співробітник",
        "password": "InitialStrongPassword123!",
        "role_id": str(viewer_role.id),
        "custom_permission_ids": [],
    }

    # 1. 201 Created
    create_resp = await api_client.post("/api/v1/users", json=payload, cookies=superadmin_cookies)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    assert created_data["username"] == uname
    assert created_data["name"] == "Новий Співробітник"
    assert created_data["version"] == 1
    assert "id" in created_data

    # 2. 409 Conflict на повторне створення з тим самим логіном
    duplicate_resp = await api_client.post("/api/v1/users", json=payload, cookies=superadmin_cookies)
    assert duplicate_resp.status_code == 409
    assert duplicate_resp.json()["error_code"] == "USER_ALREADY_EXISTS"

    # 3. 404 Not Found на неіснуючий role_id
    bad_role_payload = {
        "username": f"badrole_{uuid7().hex[-8:]}",
        "name": "Bad Role User",
        "password": "Password123!",
        "role_id": str(uuid7()),
    }
    bad_role_resp = await api_client.post("/api/v1/users", json=bad_role_payload, cookies=superadmin_cookies)
    assert bad_role_resp.status_code == 404
    assert bad_role_resp.json()["error_code"] == "ROLE_NOT_FOUND"

    # 4. 422 Unprocessable Entity (невалідний username: спецсимволи або занадто короткий)
    bad_uname_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": "-bad_uname!",
            "name": "Test User",
            "password": "Password123!",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    assert bad_uname_resp.status_code == 422

    # 5. 422 Unprocessable Entity (занадто короткий пароль)
    bad_pw_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": f"valid_{uuid7().hex[:5]}",
            "name": "Test User",
            "password": "123",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    assert bad_pw_resp.status_code == 422

    # 6. 401 та 403
    unauth_resp = await api_client.post("/api/v1/users", json=payload)
    assert unauth_resp.status_code == 401

    forbid_resp = await api_client.post("/api/v1/users", json=payload, cookies=no_permissions_cookies)
    assert forbid_resp.status_code == 403


@pytest.mark.asyncio
async def test_update_self_profile_me_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
) -> None:
    """Перевірка оновлення власного профілю (PATCH /users/me)."""
    # 1. 200 OK
    upd_payload = {
        "version": superadmin_user.version,
        "name": "Оновлений Головний Адмін",
    }
    response = await api_client.patch("/api/v1/users/me", json=upd_payload, cookies=superadmin_cookies)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Оновлений Головний Адмін"
    new_version = data["version"]
    assert new_version == superadmin_user.version + 1

    # 2. 409 Conflict OCC version mismatch
    occ_payload = {
        "version": 9999,
        "name": "OCC Hack",
    }
    occ_resp = await api_client.patch("/api/v1/users/me", json=occ_payload, cookies=superadmin_cookies)
    assert occ_resp.status_code == 409
    assert occ_resp.json()["error_code"] == "OPTIMISTIC_LOCK_CONFLICT"

    # 3. 401 Unauthorized
    unauth_resp = await api_client.patch("/api/v1/users/me", json=upd_payload)
    assert unauth_resp.status_code == 401

    # 4. 422 Unprocessable Entity
    bad_payload = {"version": 0, "name": ""}
    bad_resp = await api_client.patch("/api/v1/users/me", json=bad_payload, cookies=superadmin_cookies)
    assert bad_resp.status_code == 422


@pytest.mark.asyncio
async def test_change_self_password_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    viewer_role: RoleModel,
    auth_cookies_factory: Any,
) -> None:
    """Перевірка зміни власного пароля (POST /users/me/change-password)."""
    # Отримуємо ID дозволу users:self_password_update
    perms_resp = await api_client.get(
        "/api/v1/permissions?codes=users:self_password_update",
        cookies=superadmin_cookies,
    )
    perm_id = perms_resp.json()["items"][0]["id"]

    # Створюємо виділеного користувача з правом зміни пароля
    uname = f"pw_user_{uuid7().hex[-8:]}"
    old_pw = "OriginalPassword123!"
    create_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": uname,
            "name": "Password Test User",
            "password": old_pw,
            "role_id": str(viewer_role.id),
            "custom_permission_ids": [perm_id],
        },
        cookies=superadmin_cookies,
    )
    user_id = create_resp.json()["id"]
    user_cookies = auth_cookies_factory({"sub": user_id, "role": "viewer"})

    # 1. 200 OK успішна зміна пароля
    new_pw = "BrandNewStrongPassword456!"
    success_resp = await api_client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": old_pw, "new_password": new_pw},
        cookies=user_cookies,
    )
    assert success_resp.status_code == 200
    assert success_resp.json()["status"] == "password_changed"

    # 2. 401 Unauthorized при невірному старому паролі
    bad_pw_resp = await api_client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "WrongOldPassword999!", "new_password": "AnotherNewPassword789!"},
        cookies=user_cookies,
    )
    assert bad_pw_resp.status_code == 401
    assert bad_pw_resp.json()["error_code"] in ("INVALID_CREDENTIALS", "UNAUTHORIZED")

    # 3. 422 Unprocessable Entity: новий пароль збігається зі старим
    same_pw_resp = await api_client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": new_pw, "new_password": new_pw},
        cookies=user_cookies,
    )
    assert same_pw_resp.status_code == 422

    # 4. 401 Unauthorized без auth
    unauth_resp = await api_client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": old_pw, "new_password": new_pw},
    )
    assert unauth_resp.status_code == 401


@pytest.mark.asyncio
async def test_change_self_username_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    viewer_role: RoleModel,
    auth_cookies_factory: Any,
) -> None:
    """Перевірка зміни власного логіна (POST /users/me/change-username)."""
    # Отримуємо ID дозволу users:self_username_update
    perms_resp = await api_client.get(
        "/api/v1/permissions?codes=users:self_username_update",
        cookies=superadmin_cookies,
    )
    perm_id = perms_resp.json()["items"][0]["id"]

    uname = f"uname_test_{uuid7().hex[-8:]}"
    pw = "StrongUserPassword123!"
    create_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": uname,
            "name": "Username Test User",
            "password": pw,
            "role_id": str(viewer_role.id),
            "custom_permission_ids": [perm_id],
        },
        cookies=superadmin_cookies,
    )
    user_id = create_resp.json()["id"]
    user_cookies = auth_cookies_factory({"sub": user_id, "role": "viewer"})

    # 1. 200 OK успішна зміна логіна
    new_uname = f"uname_new_{uuid7().hex[:6]}"
    success_resp = await api_client.post(
        "/api/v1/users/me/change-username",
        json={"version": 1, "current_password": pw, "new_username": new_uname},
        cookies=user_cookies,
    )
    assert success_resp.status_code == 200
    assert success_resp.json()["status"] == "username_changed"

    # 2. 401 Unauthorized невірний поточний пароль
    bad_pw_resp = await api_client.post(
        "/api/v1/users/me/change-username",
        json={"version": 2, "current_password": "WrongPassword!", "new_username": f"another_{uuid7().hex[:5]}"},
        cookies=user_cookies,
    )
    assert bad_pw_resp.status_code == 401

    # 3. 409 Conflict логін вже зайнятий
    conflict_resp = await api_client.post(
        "/api/v1/users/me/change-username",
        json={"version": 2, "current_password": pw, "new_username": settings.seed.superadmin_username.lower()},
        cookies=user_cookies,
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["error_code"] == "USER_ALREADY_EXISTS"

    # 4. 409 Conflict конфлікт версії OCC
    occ_resp = await api_client.post(
        "/api/v1/users/me/change-username",
        json={"version": 999, "current_password": pw, "new_username": f"occ_{uuid7().hex[:5]}"},
        cookies=user_cookies,
    )
    assert occ_resp.status_code == 409
    assert occ_resp.json()["error_code"] == "OPTIMISTIC_LOCK_CONFLICT"

    # 5. 422 Unprocessable Entity
    bad_payload_resp = await api_client.post(
        "/api/v1/users/me/change-username",
        json={"version": 2, "current_password": pw, "new_username": "-invalid!"},
        cookies=user_cookies,
    )
    assert bad_payload_resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_update_user_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    viewer_role: RoleModel,
    admin_cookies: dict[str, str],
) -> None:
    """Перевірка адміністративного оновлення користувача (PUT /users/{id})."""
    # Створюємо цільового користувача
    uname = f"target_upd_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": uname,
            "name": "Target Update User",
            "password": "Password123!",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    target_id = create_resp.json()["id"]

    # 1. 200 OK повне оновлення
    upd_payload = {
        "version": 1,
        "username": f"target_new_{uuid7().hex[:6]}",
        "name": "Повністю Оновлене Ім'я",
        "role_id": str(viewer_role.id),
        "custom_permission_ids": [],
    }
    upd_resp = await api_client.put(f"/api/v1/users/{target_id}", json=upd_payload, cookies=superadmin_cookies)
    assert upd_resp.status_code == 200
    assert upd_resp.json()["name"] == "Повністю Оновлене Ім'я"
    assert upd_resp.json()["version"] == 2

    # 2. 404 Not Found
    resp_404 = await api_client.put(
        f"/api/v1/users/{uuid7()}",
        json=upd_payload,
        cookies=superadmin_cookies,
    )
    assert resp_404.status_code == 404
    assert resp_404.json()["error_code"] == "USER_NOT_FOUND"

    # 3. 409 Conflict конфлікт версії OCC
    occ_resp = await api_client.put(f"/api/v1/users/{target_id}", json=upd_payload, cookies=superadmin_cookies)
    assert occ_resp.status_code == 409
    assert occ_resp.json()["error_code"] == "OPTIMISTIC_LOCK_CONFLICT"

    # 4. 403/409 Заборона адміністративного редагування власного акаунта (self-action)
    self_resp = await api_client.put(
        f"/api/v1/users/{superadmin_user.id}",
        json={
            "version": 1,
            "username": "superadmin_mod",
            "name": "Admin Hack",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    assert self_resp.status_code in (403, 409)
    assert self_resp.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 5. 403/409 Захист super_admin від редагування іншим адміністратором
    sa_resp_by_admin = await api_client.put(
        f"/api/v1/users/{superadmin_user.id}",
        json={
            "version": superadmin_user.version,
            "username": f"sa_hacked_{uuid7().hex[:5]}",
            "name": "Super Admin Hack",
            "role_id": str(viewer_role.id),
        },
        cookies=admin_cookies,
    )
    assert sa_resp_by_admin.status_code in (403, 409)
    assert sa_resp_by_admin.json()["error_code"] in ("SUPER_ADMIN_PROTECTED", "CONFLICT")


@pytest.mark.asyncio
async def test_admin_reset_user_password_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    viewer_role: RoleModel,
    admin_cookies: dict[str, str],
) -> None:
    """Перевірка адміністративного скидання пароля (POST /users/{id}/reset-password)."""
    uname = f"reset_target_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": uname,
            "name": "Reset Password User",
            "password": "InitialPassword123!",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    target_id = create_resp.json()["id"]

    # 1. 200 OK скидання пароля
    reset_resp = await api_client.post(
        f"/api/v1/users/{target_id}/reset-password",
        json={"new_password": "BrandNewAdminResetPassword456!"},
        cookies=superadmin_cookies,
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "password_reset"

    # 2. 404 Not Found
    resp_404 = await api_client.post(
        f"/api/v1/users/{uuid7()}/reset-password",
        json={"new_password": "BrandNewAdminResetPassword456!"},
        cookies=superadmin_cookies,
    )
    assert resp_404.status_code == 404

    # 3. 403/409 Заборона скидання пароля самому собі
    self_reset = await api_client.post(
        f"/api/v1/users/{superadmin_user.id}/reset-password",
        json={"new_password": "NewPasswordSelf123!"},
        cookies=superadmin_cookies,
    )
    assert self_reset.status_code in (403, 409)
    assert self_reset.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 4. 422 Unprocessable Entity (короткий пароль)
    bad_pw = await api_client.post(
        f"/api/v1/users/{target_id}/reset-password",
        json={"new_password": "short"},
        cookies=superadmin_cookies,
    )
    assert bad_pw.status_code == 422

    # 5. 403/409 Захист super_admin від скидання пароля іншим адміністратором
    sa_reset_by_admin = await api_client.post(
        f"/api/v1/users/{superadmin_user.id}/reset-password",
        json={"new_password": "BrandNewAdminResetPassword456!"},
        cookies=admin_cookies,
    )
    assert sa_reset_by_admin.status_code in (403, 409)
    assert sa_reset_by_admin.json()["error_code"] in ("SUPER_ADMIN_PROTECTED", "CONFLICT")


@pytest.mark.asyncio
async def test_deactivate_and_restore_user_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    viewer_role: RoleModel,
    admin_cookies: dict[str, str],
) -> None:
    """Перевірка деактивації та відновлення користувача (PATCH /users/{id}/deactivate та /restore)."""
    uname = f"deact_user_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": uname,
            "name": "Deactivate Target User",
            "password": "Password123!",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    target_id = create_resp.json()["id"]

    # 1. 200 OK деактивація
    deact_resp = await api_client.patch(
        f"/api/v1/users/{target_id}/deactivate",
        json={"version": 1},
        cookies=superadmin_cookies,
    )
    assert deact_resp.status_code == 200
    deact_data = deact_resp.json()
    assert deact_data["deleted_at"] is not None
    assert deact_data["version"] == 2

    # 2. 400/409 Повторна деактивація вже неактивного користувача
    repeat_deact = await api_client.patch(
        f"/api/v1/users/{target_id}/deactivate",
        json={"version": 2},
        cookies=superadmin_cookies,
    )
    assert repeat_deact.status_code in (400, 409)
    assert repeat_deact.json()["error_code"] in (
        "ALREADY_INACTIVE",
        "RESOURCE_ALREADY_INACTIVE",
        "BAD_REQUEST",
        "CONFLICT",
    )

    # 3. 200 OK відновлення
    restore_resp = await api_client.patch(
        f"/api/v1/users/{target_id}/restore",
        json={"version": 2},
        cookies=superadmin_cookies,
    )
    assert restore_resp.status_code == 200
    restore_data = restore_resp.json()
    assert restore_data["deleted_at"] is None
    assert restore_data["version"] == 3

    # 4. 400/409 Повторне відновлення вже активного користувача
    repeat_restore = await api_client.patch(
        f"/api/v1/users/{target_id}/restore",
        json={"version": 3},
        cookies=superadmin_cookies,
    )
    assert repeat_restore.status_code in (400, 409)
    assert repeat_restore.json()["error_code"] in (
        "ALREADY_ACTIVE",
        "RESOURCE_ALREADY_ACTIVE",
        "BAD_REQUEST",
        "CONFLICT",
    )

    # 5. 403/409 Заборона самодеактивації
    self_deact = await api_client.patch(
        f"/api/v1/users/{superadmin_user.id}/deactivate",
        json={"version": 1},
        cookies=superadmin_cookies,
    )
    assert self_deact.status_code in (403, 409)
    assert self_deact.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 6. 403/409 Заборона самовідновлення (self-action)
    self_restore = await api_client.patch(
        f"/api/v1/users/{superadmin_user.id}/restore",
        json={"version": 1},
        cookies=superadmin_cookies,
    )
    assert self_restore.status_code in (403, 409)
    assert self_restore.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "CONFLICT")

    # 7. 403/409 Захист super_admin від деактивації іншим адміністратором
    sa_deact_by_admin = await api_client.patch(
        f"/api/v1/users/{superadmin_user.id}/deactivate",
        json={"version": superadmin_user.version},
        cookies=admin_cookies,
    )
    assert sa_deact_by_admin.status_code in (403, 409)
    assert sa_deact_by_admin.json()["error_code"] in ("SUPER_ADMIN_PROTECTED", "CONFLICT")


@pytest.mark.asyncio
async def test_delete_user_and_preview_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    superadmin_user: UserModel,
    viewer_role: RoleModel,
    admin_cookies: dict[str, str],
) -> None:
    """Перевірка фізичного видалення (DELETE /users/{id}) та оцінки видалення (GET /users/{id}/delete-preview)."""
    uname = f"del_user_{uuid7().hex[:6]}"
    create_resp = await api_client.post(
        "/api/v1/users",
        json={
            "username": uname,
            "name": "Delete Target User",
            "password": "Password123!",
            "role_id": str(viewer_role.id),
        },
        cookies=superadmin_cookies,
    )
    target_id = create_resp.json()["id"]

    # 1. 200 OK delete-preview
    prev_resp = await api_client.get(f"/api/v1/users/{target_id}/delete-preview", cookies=superadmin_cookies)
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["action"] == "hard_delete"

    # 2. 200 OK delete-preview для самого себе (заборонено видалення: action=blocked)
    self_prev = await api_client.get(f"/api/v1/users/{superadmin_user.id}/delete-preview", cookies=superadmin_cookies)
    assert self_prev.status_code == 200
    assert self_prev.json()["action"] == "blocked"

    # 3. 204 No Content фізичне видалення
    del_resp = await api_client.delete(f"/api/v1/users/{target_id}", cookies=superadmin_cookies)
    assert del_resp.status_code == 204

    # Перевірка 404 після видалення
    after_del = await api_client.get(f"/api/v1/users/{target_id}", cookies=superadmin_cookies)
    assert after_del.status_code == 404

    # 4. 404 Not Found на повторне видалення
    del_404 = await api_client.delete(f"/api/v1/users/{target_id}", cookies=superadmin_cookies)
    assert del_404.status_code == 404

    # 5. 403/409 Заборона самовидалення
    self_del = await api_client.delete(f"/api/v1/users/{superadmin_user.id}", cookies=superadmin_cookies)
    assert self_del.status_code in (403, 409)
    assert self_del.json()["error_code"] in ("SELF_ACTION_FORBIDDEN", "SUPER_ADMIN_PROTECTED", "CONFLICT")

    # 6. 403/409 Захист super_admin від видалення іншим адміністратором
    sa_del_by_admin = await api_client.delete(f"/api/v1/users/{superadmin_user.id}", cookies=admin_cookies)
    assert sa_del_by_admin.status_code in (403, 409)
    assert sa_del_by_admin.json()["error_code"] in ("SUPER_ADMIN_PROTECTED", "CONFLICT")
