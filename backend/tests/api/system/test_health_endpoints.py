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
