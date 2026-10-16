from httpx import AsyncClient
from uuid6 import uuid7


async def test_create_target_happy_path(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    slug = f"test-movie-{uuid7().hex[:8]}"
    payload = {
        "slug": slug,
        "title": "Interstellar Special Edition",
        "category": "movie",
        "description": "Exploration beyond the stars.",
        "metadata": {"director": "Christopher Nolan", "year": 2014},
    }

    response = await api_client.post(
        "/api/v1/targets",
        json=payload,
        cookies=superadmin_cookies,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["slug"] == slug
    assert data["title"] == "Interstellar Special Edition"
    assert data["category"] == "movie"
    assert data["description"] == "Exploration beyond the stars."
    assert data["metadata"] == {"director": "Christopher Nolan", "year": 2014}
    assert data["is_active"] is True
    assert data["version"] == 1
    assert "id" in data
    assert "created_at" in data


async def test_create_target_unauthorized(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/targets",
        json={"slug": "unauth-slug", "title": "Test", "category": "movie"},
    )
    assert response.status_code == 401


async def test_create_target_forbidden(
    api_client: AsyncClient,
    no_permissions_cookies: dict[str, str],
) -> None:
    response = await api_client.post(
        "/api/v1/targets",
        json={"slug": "forbidden-slug", "title": "Test", "category": "movie"},
        cookies=no_permissions_cookies,
    )
    assert response.status_code == 403


async def test_create_target_slug_conflict(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    slug = f"conflict-{uuid7().hex[:8]}"
    payload = {"slug": slug, "title": "First Target", "category": "book"}

    resp1 = await api_client.post("/api/v1/targets", json=payload, cookies=superadmin_cookies)
    assert resp1.status_code == 201

    resp2 = await api_client.post("/api/v1/targets", json=payload, cookies=superadmin_cookies)
    assert resp2.status_code == 409


async def test_create_target_validation_error(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    # Invalid slug (contains spaces / uppercase / special chars)
    response = await api_client.post(
        "/api/v1/targets",
        json={"slug": "INVALID SLUG!", "title": "Test", "category": "movie"},
        cookies=superadmin_cookies,
    )
    assert response.status_code == 422

    # Empty title
    response_empty = await api_client.post(
        "/api/v1/targets",
        json={"slug": "valid-slug", "title": "", "category": "movie"},
        cookies=superadmin_cookies,
    )
    assert response_empty.status_code == 422


async def test_list_targets_public_access(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    slug = f"target-list-{uuid7().hex[:8]}"
    await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Listing Item", "category": "electronics"},
        cookies=superadmin_cookies,
    )

    # Public GET without cookies
    response = await api_client.get("/api/v1/targets")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1

    # Filter by category
    resp_cat = await api_client.get("/api/v1/targets", params={"category": "electronics"})
    assert resp_cat.status_code == 200
    cat_data = resp_cat.json()
    assert all(item["category"] == "electronics" for item in cat_data["items"])


async def test_get_target_details_by_id_and_slug(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    slug = f"details-{uuid7().hex[:8]}"
    create_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Details Movie", "category": "movie"},
        cookies=superadmin_cookies,
    )
    assert create_resp.status_code == 201
    target_id = create_resp.json()["id"]

    # Get by UUID
    resp_id = await api_client.get(f"/api/v1/targets/{target_id}")
    assert resp_id.status_code == 200
    assert resp_id.json()["id"] == target_id
    assert resp_id.json()["slug"] == slug
    assert "rating" in resp_id.json()

    # Get by slug
    resp_slug = await api_client.get(f"/api/v1/targets/{slug}")
    assert resp_slug.status_code == 200
    assert resp_slug.json()["id"] == target_id

    # Get non-existent
    resp_404 = await api_client.get(f"/api/v1/targets/{uuid7()}")
    assert resp_404.status_code == 404


async def test_list_targets_sorting_and_filters(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    # Створюємо кілька таргетів з різними назвами
    for prefix in ["alpha", "beta", "gamma"]:
        slug = f"{prefix}-{uuid7().hex[:8]}"
        await api_client.post(
            "/api/v1/targets",
            json={"slug": slug, "title": f"Target {prefix.upper()}", "category": "books"},
            cookies=superadmin_cookies,
        )

    # 1. Сортування за назвою (title asc)
    resp_asc = await api_client.get("/api/v1/targets", params={"sort": "title", "category": "books"})
    assert resp_asc.status_code == 200
    titles_asc = [item["title"] for item in resp_asc.json()["items"]]
    assert titles_asc == sorted(titles_asc)

    # 2. Сортування за назвою (title desc)
    resp_desc = await api_client.get("/api/v1/targets", params={"sort": "-title", "category": "books"})
    assert resp_desc.status_code == 200
    titles_desc = [item["title"] for item in resp_desc.json()["items"]]
    assert titles_desc == sorted(titles_desc, reverse=True)

    # 3. Пошук search за префіксом
    resp_search = await api_client.get("/api/v1/targets", params={"search": "alpha"})
    assert resp_search.status_code == 200
    assert all("alpha" in item["slug"] or "alpha" in item["title"].lower() for item in resp_search.json()["items"])

    # 4. Невалідне сортування -> 422 Unprocessable Entity
    resp_inv = await api_client.get("/api/v1/targets", params={"sort": "unsupported_field"})
    assert resp_inv.status_code == 422


async def test_update_target_endpoint(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    no_permissions_cookies: dict[str, str],
) -> None:
    # 1. Створення об'єкта
    slug = f"target-update-{uuid7().hex[:8]}"
    create_res = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Original Title", "category": "movie"},
        cookies=superadmin_cookies,
    )
    assert create_res.status_code == 201
    target_id = create_res.json()["id"]

    # 2. Оновлення об'єкта (200 OK)
    update_payload = {
        "title": "Updated Title",
        "category": "cinema",
        "description": "Updated description.",
        "metadata": {"updated": True},
        "version": 1,
    }
    update_res = await api_client.put(
        f"/api/v1/targets/{target_id}",
        json=update_payload,
        cookies=superadmin_cookies,
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["title"] == "Updated Title"
    assert data["category"] == "cinema"
    assert data["description"] == "Updated description."
    assert data["metadata"] == {"updated": True}
    assert data["version"] == 2

    # 3. OCC Conflict (409 Conflict при передачі застарілої версії)
    conflict_res = await api_client.put(
        f"/api/v1/targets/{target_id}",
        json={**update_payload, "version": 1},
        cookies=superadmin_cookies,
    )
    assert conflict_res.status_code == 409
    assert conflict_res.json()["error_code"] == "OPTIMISTIC_LOCK_CONFLICT"

    # 4. Forbidden без прав TARGETS_UPDATE
    forbidden_res = await api_client.put(
        f"/api/v1/targets/{target_id}",
        json={**update_payload, "version": 2},
        cookies=no_permissions_cookies,
    )
    assert forbidden_res.status_code == 403


async def test_delete_target_endpoint(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    no_permissions_cookies: dict[str, str],
) -> None:
    # 1. Створення об'єкта
    slug = f"target-delete-{uuid7().hex[:8]}"
    create_res = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Target To Delete", "category": "books"},
        cookies=superadmin_cookies,
    )
    assert create_res.status_code == 201
    target_id = create_res.json()["id"]

    # 2. Forbidden без прав TARGETS_DELETE
    forbidden_res = await api_client.delete(
        f"/api/v1/targets/{target_id}",
        cookies=no_permissions_cookies,
    )
    assert forbidden_res.status_code == 403

    # 3. Успішне видалення (204 No Content)
    del_res = await api_client.delete(
        f"/api/v1/targets/{target_id}",
        cookies=superadmin_cookies,
    )
    assert del_res.status_code == 204

    # 4. Перевірка 404 після видалення
    get_res = await api_client.get(f"/api/v1/targets/{target_id}")
    assert get_res.status_code == 404


async def test_update_and_delete_target_unhappy_paths(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    non_existent_id = uuid7()
    update_payload = {"title": "Valid Title", "category": "movie", "version": 1}

    # 1. PUT 401 Unauthorized
    put_unauth = await api_client.put(f"/api/v1/targets/{non_existent_id}", json=update_payload)
    assert put_unauth.status_code == 401

    # 2. PUT 404 Not Found
    put_404 = await api_client.put(
        f"/api/v1/targets/{non_existent_id}",
        json=update_payload,
        cookies=superadmin_cookies,
    )
    assert put_404.status_code == 404

    # 3. PUT 422 Unprocessable Entity (version=0 or empty title)
    put_422 = await api_client.put(
        f"/api/v1/targets/{non_existent_id}",
        json={"title": "", "category": "movie", "version": 0},
        cookies=superadmin_cookies,
    )
    assert put_422.status_code == 422

    # 4. DELETE 401 Unauthorized
    del_unauth = await api_client.delete(f"/api/v1/targets/{non_existent_id}")
    assert del_unauth.status_code == 401

    # 5. DELETE 404 Not Found
    del_404 = await api_client.delete(
        f"/api/v1/targets/{non_existent_id}",
        cookies=superadmin_cookies,
    )
    assert del_404.status_code == 404


async def test_list_targets_filter_min_rating(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    response = await api_client.get("/api/v1/targets", params={"min_rating": 4.0})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    for item in data["items"]:
        if "rating" in item and item["rating"] and "average_score" in item["rating"]:
            assert float(item["rating"]["average_score"]) >= 4.0
