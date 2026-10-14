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
