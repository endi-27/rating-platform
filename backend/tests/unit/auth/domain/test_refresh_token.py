from datetime import UTC, datetime, timedelta

import pytest
from uuid6 import uuid7

from src.modules.auth.domain import RefreshToken


def test_refresh_token_create_defaults() -> None:
    user_id = uuid7()
    token_hash = "abc123hash"
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=7)
    max_session = now + timedelta(days=30)

    token = RefreshToken.create(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        max_session_expiration=max_session,
    )

    assert token.user_id == user_id
    assert token.token_hash == token_hash
    assert token.expires_at == expires_at
    assert token.max_session_expiration == max_session
    assert token.is_revoked is False
    assert token.is_remember_me is False
    assert isinstance(token.id, type(uuid7()))
    assert isinstance(token.issued_at, datetime)
    assert token.issued_at.tzinfo == UTC


def test_refresh_token_create_custom_options() -> None:
    user_id = uuid7()
    token_id = uuid7()
    token_hash = "custom_hash"
    custom_issued = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
    expires_at = custom_issued + timedelta(days=14)
    max_session = custom_issued + timedelta(days=60)

    token = RefreshToken.create(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        max_session_expiration=max_session,
        is_remember_me=True,
        issued_at=custom_issued,
        token_id=token_id,
    )

    assert token.id == token_id
    assert token.issued_at == custom_issued
    assert token.is_remember_me is True


@pytest.mark.parametrize("empty_hash", ["", "   ", "\t\n"])
def test_refresh_token_empty_hash_raises_value_error(empty_hash: str) -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="Хеш токена .* не може бути порожнім"):
        RefreshToken(
            id=uuid7(),
            user_id=uuid7(),
            token_hash=empty_hash,
            issued_at=now,
            expires_at=now + timedelta(days=7),
            max_session_expiration=now + timedelta(days=30),
        )


def test_refresh_token_expires_at_before_issued_at_raises() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="expires_at.*не може бути меншою за дату видачі"):
        RefreshToken(
            id=uuid7(),
            user_id=uuid7(),
            token_hash="hash",
            issued_at=now,
            expires_at=now - timedelta(seconds=1),
            max_session_expiration=now + timedelta(days=30),
        )


def test_refresh_token_max_session_before_issued_at_raises() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="max_session_expiration.*не може бути меншим за дату видачі"):
        RefreshToken(
            id=uuid7(),
            user_id=uuid7(),
            token_hash="hash",
            issued_at=now,
            expires_at=now + timedelta(days=7),
            max_session_expiration=now - timedelta(seconds=1),
        )


def test_refresh_token_naive_datetimes_converted_to_utc() -> None:
    naive_issued = datetime(2025, 5, 1, 12, 0)
    naive_expires = datetime(2025, 5, 8, 12, 0)
    naive_max = datetime(2025, 5, 31, 12, 0)

    token = RefreshToken(
        id=uuid7(),
        user_id=uuid7(),
        token_hash="hash",
        issued_at=naive_issued,
        expires_at=naive_expires,
        max_session_expiration=naive_max,
    )

    assert token.issued_at.tzinfo == UTC
    assert token.expires_at.tzinfo == UTC
    assert token.max_session_expiration.tzinfo == UTC


def test_refresh_token_rotate_within_session() -> None:
    now = datetime.now(UTC)
    token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="old_hash",
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
        is_remember_me=True,
        issued_at=now,
    )

    rotated_at = now + timedelta(days=2)
    new_expires = rotated_at + timedelta(days=7)
    new_token = token.rotate(
        new_token_hash="new_hash",
        new_expires_at=new_expires,
        rotated_at=rotated_at,
    )

    # Old token must be revoked
    assert token.is_revoked is True

    # New token checks
    assert new_token.id != token.id
    assert new_token.user_id == token.user_id
    assert new_token.token_hash == "new_hash"
    assert new_token.is_revoked is False
    assert new_token.is_remember_me is True
    assert new_token.issued_at == rotated_at
    assert new_token.expires_at == new_expires
    assert new_token.max_session_expiration == token.max_session_expiration


def test_refresh_token_rotate_caps_at_max_session_expiration() -> None:
    now = datetime.now(UTC)
    max_session = now + timedelta(days=10)
    token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="old_hash",
        expires_at=now + timedelta(days=7),
        max_session_expiration=max_session,
        issued_at=now,
    )

    # Rotate at day 8, asking for +7 days (which would be day 15 > day 10 max_session)
    rotated_at = now + timedelta(days=8)
    requested_new_expires = rotated_at + timedelta(days=7)
    new_token = token.rotate(
        new_token_hash="capped_hash",
        new_expires_at=requested_new_expires,
        rotated_at=rotated_at,
    )

    assert token.is_revoked is True
    assert new_token.expires_at == max_session
    assert new_token.expires_at < requested_new_expires


def test_refresh_token_is_expired() -> None:
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=1)
    token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="hash",
        expires_at=expires_at,
        max_session_expiration=now + timedelta(days=1),
        issued_at=now,
    )

    assert token.is_expired(now) is False
    assert token.is_expired(expires_at) is False
    assert token.is_expired(expires_at + timedelta(seconds=1)) is True


def test_refresh_token_is_session_expired() -> None:
    now = datetime.now(UTC)
    max_session = now + timedelta(days=7)
    token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="hash",
        expires_at=now + timedelta(days=3),
        max_session_expiration=max_session,
        issued_at=now,
    )

    assert token.is_session_expired(now) is False
    assert token.is_session_expired(max_session) is False
    assert token.is_session_expired(max_session + timedelta(seconds=1)) is True


def test_refresh_token_is_valid_and_revoke() -> None:
    now = datetime.now(UTC)
    token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="hash",
        expires_at=now + timedelta(days=7),
        max_session_expiration=now + timedelta(days=30),
        issued_at=now,
    )

    # Active token
    assert token.is_valid(now) is True

    # Revoking
    token.revoke()
    assert token.is_revoked is True
    assert token.is_valid(now) is False

    # Second revoke should be idempotent
    token.revoke()
    assert token.is_revoked is True


def test_refresh_token_is_valid_when_expired_or_session_expired() -> None:
    now = datetime.now(UTC)
    # Expired token
    expired_token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="hash",
        expires_at=now + timedelta(hours=1),
        max_session_expiration=now + timedelta(days=1),
        issued_at=now,
    )
    assert expired_token.is_valid(now + timedelta(hours=2)) is False

    # Session expired token
    session_expired_token = RefreshToken.create(
        user_id=uuid7(),
        token_hash="hash",
        expires_at=now + timedelta(days=10),
        max_session_expiration=now + timedelta(days=2),
        issued_at=now,
    )
    assert session_expired_token.is_valid(now + timedelta(days=3)) is False
