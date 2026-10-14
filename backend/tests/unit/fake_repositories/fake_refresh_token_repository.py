from datetime import datetime
from uuid import UUID

from src.modules.auth.domain import (
    IRefreshTokenRepository,
    RefreshToken,
    RevokedTokenDTO,
)


class FakeRefreshTokenRepository(IRefreshTokenRepository):
    def __init__(self) -> None:
        self.tokens: dict[UUID, RefreshToken] = {}
        self.fail_on_delete: bool = False

    async def create(self, refresh_token: RefreshToken) -> None:
        self.tokens[refresh_token.id] = refresh_token

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        for t in self.tokens.values():
            if t.token_hash == token_hash:
                return t
        return None

    async def save(self, refresh_token: RefreshToken) -> None:
        self.tokens[refresh_token.id] = refresh_token

    async def bulk_revoke_for_users(self, user_ids: set[UUID]) -> list[RevokedTokenDTO]:
        revoked: list[RevokedTokenDTO] = []
        for t in self.tokens.values():
            if t.user_id in user_ids and not t.is_revoked:
                t.revoke()
                revoked.append(RevokedTokenDTO(id=t.id, user_id=t.user_id))
        return revoked

    async def delete_expired_before(self, cutoff: datetime, limit: int | None = None) -> int:
        if self.fail_on_delete:
            raise RuntimeError("Помилка видалення застарілих токенів")
        to_delete = [
            tid for tid, t in self.tokens.items() if t.expires_at < cutoff or t.max_session_expiration < cutoff
        ]
        if limit is not None:
            to_delete = to_delete[:limit]
        for tid in to_delete:
            del self.tokens[tid]
        return len(to_delete)
