from typing import Annotated
from uuid import UUID

from fastapi import Depends

from src.api import get_uow
from src.core import IUnitOfWork
from src.modules.auth.dependencies import (
    get_refresh_token_repo,
)
from src.modules.auth.domain import IRefreshTokenRepository


class AuthPublicGateway:
    """
    Публічний шлюз модуля auth для міжмодульної взаємодії.
    Дозволяє іншим модулям (зокрема users) анулювати активні сесії користувачів.
    """

    def __init__(
        self,
        refresh_repo: IRefreshTokenRepository,
        uow: IUnitOfWork | None = None,
    ) -> None:
        self._refresh_repo = refresh_repo
        self._uow = uow

    async def revoke_all_user_sessions(
        self,
        user_id: UUID,
        *,
        actor_id: UUID | None = None,
        actor_username: str | None = None,
        external_uow: IUnitOfWork | None = None,
    ) -> None:
        """Анулювання всіх сесій користувача (наприклад, при деактивації або зміні облікових даних)."""
        await self._refresh_repo.bulk_revoke_for_users({user_id})


def get_auth_public_gateway(
    refresh_repo: Annotated[IRefreshTokenRepository, Depends(get_refresh_token_repo)],
    uow: Annotated[IUnitOfWork, Depends(get_uow)],
) -> AuthPublicGateway:
    return AuthPublicGateway(refresh_repo=refresh_repo, uow=uow)


__all__ = [
    "AuthPublicGateway",
    "get_auth_public_gateway",
]
