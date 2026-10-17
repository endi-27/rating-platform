import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint_success(api_client: AsyncClient) -> None:
    """Перевірка повернення метаданих сервісу та діагностичних заголовків на GET /."""
    response = await api_client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "Rating Platform Backend"
    assert data["version"] == "0.1.0"
    assert data["docs"] == "/docs"
    assert data["health"] == "/api/v1/health"

    # Перевірка наскрізних заголовків розподіленої системи
    assert "X-Instance-ID" in response.headers
    assert "X-Request-ID" in response.headers
    assert "X-Process-Time-Ms" in response.headers
    assert float(response.headers["X-Process-Time-Ms"]) >= 0.0


@pytest.mark.asyncio
async def test_health_check_endpoint_success(api_client: AsyncClient) -> None:
    """Перевірка повної працездатності залежностей (PostgreSQL, Redis) на GET /api/v1/health."""
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "instance_id" in data
    assert "environment" in data
    assert "version" in data
    assert data["dependencies"]["database"] == "ok"
    assert data["dependencies"]["redis"] == "ok"

    # Діагностичні заголовки
    assert response.headers.get("X-Instance-ID") is not None
    assert response.headers.get("X-Process-Time-Ms") is not None


@pytest.mark.asyncio
async def test_simulate_latency_header(api_client: AsyncClient) -> None:
    """Перевірка симуляції асиметричної затримки через заголовок X-Simulate-Latency-Ms (ЛР №3)."""
    response = await api_client.get(
        "/api/v1/health",
        headers={"X-Simulate-Latency-Ms": "50"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Instance-ID") is not None
    assert response.headers.get("X-Process-Time-Ms") is not None
    # Затримка має бути не менше 40 мс з урахуванням накладних витрат
    assert float(response.headers["X-Process-Time-Ms"]) >= 40.0


@pytest.mark.asyncio
async def test_cached_endpoint_headers(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    """Перевірка розподіленого кешу та заголовка X-Cache (MISS -> HIT) на ендпоінтах з @cache (ЛР №4)."""
    from uuid6 import uuid7

    slug = f"cache-test-{uuid7().hex[:8]}"
    create_res = await api_client.post(
        "/api/v1/targets",
        json={"title": "Cache Test Target", "slug": slug, "category": "books"},
        cookies=superadmin_cookies,
    )
    assert create_res.status_code == 201

    # 1. Перший запит: кеш-промах (MISS)
    res_miss = await api_client.get(f"/api/v1/targets/{slug}")
    assert res_miss.status_code == 200
    assert res_miss.headers.get("X-Cache") == "MISS"

    # 2. Другий запит: потрапляння в кеш (HIT)
    res_hit = await api_client.get(f"/api/v1/targets/{slug}")
    assert res_hit.status_code == 200
    assert res_hit.headers.get("X-Cache") == "HIT"
