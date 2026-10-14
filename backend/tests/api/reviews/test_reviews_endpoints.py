from collections.abc import Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from src.core import default_password_hasher
from src.modules.users.infrastructure.models import RoleModel, UserModel


async def _create_user(
    db_session: AsyncSession,
    viewer_role: RoleModel,
    prefix: str = "rev_user",
) -> UserModel:
    user = UserModel(
        id=uuid7(),
        version=1,
        username=f"{prefix}_{uuid7().hex[:6]}",
        name="Reviewer User",
        password_hash=default_password_hasher.hash("TestPass123!"),
        role_id=viewer_role.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def test_create_review_happy_path(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    db_session: AsyncSession,
    viewer_role: RoleModel,
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
) -> None:
    # 1. Створюємо Target
    slug = f"target-{uuid7().hex[:8]}"
    target_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Inception", "category": "movie"},
        cookies=superadmin_cookies,
    )
    assert target_resp.status_code == 201
    target_id = target_resp.json()["id"]

    # 2. Звичайний зареєстрований користувач створює відгук
    user = await _create_user(db_session, viewer_role)
    user_cookies = auth_cookies_factory({"sub": str(user.id), "role": "viewer"})

    review_payload = {
        "score": 5,
        "title": "Mind-bending masterpiece!",
        "content": "One of the best sci-fi movies ever created. Superb direction and acting.",
    }

    resp = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json=review_payload,
        cookies=user_cookies,
    )
    assert resp.status_code == 201
    review_data = resp.json()
    assert review_data["score"] == 5
    assert review_data["title"] == "Mind-bending masterpiece!"
    assert review_data["status"] == "published"
    assert review_data["target_id"] == target_id
    assert review_data["user_id"] == str(user.id)


async def test_create_review_unauthorized(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    slug = f"target-{uuid7().hex[:8]}"
    target_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Target Unauth", "category": "book"},
        cookies=superadmin_cookies,
    )
    target_id = target_resp.json()["id"]

    response = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json={"score": 4, "content": "Attempting to post without auth token header."},
    )
    assert response.status_code == 401


async def test_create_review_target_not_found(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    response = await api_client.post(
        f"/api/v1/targets/{uuid7()}/reviews",
        json={"score": 4, "content": "Review for non-existent target in database."},
        cookies=superadmin_cookies,
    )
    assert response.status_code == 404


async def test_create_review_one_review_rule_conflict(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    db_session: AsyncSession,
    viewer_role: RoleModel,
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
) -> None:
    slug = f"target-{uuid7().hex[:8]}"
    target_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Single Target", "category": "game"},
        cookies=superadmin_cookies,
    )
    target_id = target_resp.json()["id"]

    user = await _create_user(db_session, viewer_role)
    user_cookies = auth_cookies_factory({"sub": str(user.id), "role": "viewer"})
    payload = {"score": 5, "content": "First valid review on the target."}

    # Перший відгук успішний
    resp1 = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json=payload,
        cookies=user_cookies,
    )
    assert resp1.status_code == 201

    # Другий відгук від того самого користувача -> 409 Conflict
    resp2 = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json=payload,
        cookies=user_cookies,
    )
    assert resp2.status_code == 409


async def test_create_review_validation_errors(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
) -> None:
    target_id = uuid7()

    # Invalid score (> 5)
    resp_score = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json={"score": 6, "content": "Valid content length."},
        cookies=superadmin_cookies,
    )
    assert resp_score.status_code == 422

    # Content too short (< 10)
    resp_short = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json={"score": 5, "content": "Short"},
        cookies=superadmin_cookies,
    )
    assert resp_short.status_code == 422


async def test_get_target_reviews_and_rating(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    db_session: AsyncSession,
    viewer_role: RoleModel,
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
) -> None:
    slug = f"target-{uuid7().hex[:8]}"
    target_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Alien Movie", "category": "movie"},
        cookies=superadmin_cookies,
    )
    target_id = target_resp.json()["id"]

    # Post review
    user = await _create_user(db_session, viewer_role)
    user_cookies = auth_cookies_factory({"sub": str(user.id), "role": "viewer"})
    await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json={"score": 5, "content": "Excellent horror atmosphere and sound design."},
        cookies=user_cookies,
    )

    # Public list reviews (no auth)
    reviews_resp = await api_client.get(f"/api/v1/targets/{target_id}/reviews")
    assert reviews_resp.status_code == 200
    rev_data = reviews_resp.json()
    assert rev_data["total"] == 1
    assert len(rev_data["items"]) == 1

    # Public get rating (no auth)
    rating_resp = await api_client.get(f"/api/v1/targets/{target_id}/rating")
    assert rating_resp.status_code == 200
    r_data = rating_resp.json()
    assert r_data["total_reviews"] == 1
    assert float(r_data["average_score"]) == 5.0
    assert r_data["star_5_count"] == 1


async def test_vote_review_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    db_session: AsyncSession,
    viewer_role: RoleModel,
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
) -> None:
    slug = f"target-{uuid7().hex[:8]}"
    target_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Vote Target", "category": "movie"},
        cookies=superadmin_cookies,
    )
    target_id = target_resp.json()["id"]

    author = await _create_user(db_session, viewer_role, prefix="author")
    author_cookies = auth_cookies_factory({"sub": str(author.id), "role": "viewer"})

    rev_resp = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json={"score": 5, "content": "Review that will receive community votes."},
        cookies=author_cookies,
    )
    assert rev_resp.status_code == 201
    review_id = rev_resp.json()["id"]

    # 1. Author votes for own review -> 409 Conflict
    self_vote_resp = await api_client.post(
        f"/api/v1/reviews/{review_id}/vote",
        json={"is_helpful": True},
        cookies=author_cookies,
    )
    assert self_vote_resp.status_code == 409

    # 2. Voter votes helpful -> 200 OK
    voter = await _create_user(db_session, viewer_role, prefix="voter")
    voter_cookies = auth_cookies_factory({"sub": str(voter.id), "role": "viewer"})
    vote_resp = await api_client.post(
        f"/api/v1/reviews/{review_id}/vote",
        json={"is_helpful": True},
        cookies=voter_cookies,
    )
    assert vote_resp.status_code == 200
    assert vote_resp.json()["is_helpful"] is True

    # 3. Duplicate vote -> 409 Conflict
    dup_vote_resp = await api_client.post(
        f"/api/v1/reviews/{review_id}/vote",
        json={"is_helpful": True},
        cookies=voter_cookies,
    )
    assert dup_vote_resp.status_code == 409

    # 4. Vote for non-existent review -> 404 Not Found
    not_found_resp = await api_client.post(
        f"/api/v1/reviews/{uuid7()}/vote",
        json={"is_helpful": True},
        cookies=voter_cookies,
    )
    assert not_found_resp.status_code == 404


async def test_moderate_review_endpoints(
    api_client: AsyncClient,
    superadmin_cookies: dict[str, str],
    no_permissions_cookies: dict[str, str],
    db_session: AsyncSession,
    viewer_role: RoleModel,
    auth_cookies_factory: Callable[[dict[str, Any] | None], dict[str, str]],
) -> None:
    slug = f"target-{uuid7().hex[:8]}"
    target_resp = await api_client.post(
        "/api/v1/targets",
        json={"slug": slug, "title": "Mod Target", "category": "movie"},
        cookies=superadmin_cookies,
    )
    target_id = target_resp.json()["id"]

    user = await _create_user(db_session, viewer_role, prefix="spammer")
    user_cookies = auth_cookies_factory({"sub": str(user.id), "role": "viewer"})
    rev_resp = await api_client.post(
        f"/api/v1/targets/{target_id}/reviews",
        json={"score": 1, "content": "Spam review with malicious links and ads."},
        cookies=user_cookies,
    )
    assert rev_resp.status_code == 201
    review_id = rev_resp.json()["id"]

    # 1. Without permission -> 403 Forbidden
    forb_resp = await api_client.patch(
        f"/api/v1/reviews/{review_id}/moderate",
        json={"action": "hide"},
        cookies=no_permissions_cookies,
    )
    assert forb_resp.status_code == 403

    # 2. SuperAdmin (has REVIEWS_MODERATE) hides review -> 200 OK
    mod_resp = await api_client.patch(
        f"/api/v1/reviews/{review_id}/moderate",
        json={"action": "hide"},
        cookies=superadmin_cookies,
    )
    assert mod_resp.status_code == 200
    assert mod_resp.json()["status"] == "hidden"

    # 3. Invalid action -> 422 Unprocessable Entity
    inv_resp = await api_client.patch(
        f"/api/v1/reviews/{review_id}/moderate",
        json={"action": "destroy"},
        cookies=superadmin_cookies,
    )
    assert inv_resp.status_code == 422
