from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import DataInconsistencyException
from src.modules.auth.domain import IRefreshTokenRepository, RefreshToken, RevokedTokenDTO
from src.modules.auth.infrastructure.mappers import RefreshTokenMapper
from src.modules.auth.infrastructure.models import RefreshTokenModel


class SqlAlchemyRefreshTokenRepository(IRefreshTokenRepository):
    """SQLAlchemy реалізація репозиторію сесійних токенів оновлення."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, refresh_token: RefreshToken) -> None:
        orm = RefreshTokenMapper.to_orm(refresh_token)
        self._session.add(orm)
        await self._session.flush()

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash).with_for_update()
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return RefreshTokenMapper.to_domain(orm) if orm else None

    async def save(self, refresh_token: RefreshToken, /) -> None:
        orm = await self._session.get(RefreshTokenModel, refresh_token.id)
        if orm is None:
            raise DataInconsistencyException(f"Сесійний токен ID '{refresh_token.id}' не знайдено для збереження.")
        RefreshTokenMapper.update_to_orm(orm, refresh_token)
        await self._session.flush()

    async def bulk_revoke_for_users(self, user_ids: set[UUID]) -> list[RevokedTokenDTO]:
        if not user_ids:
            return []
        stmt = (
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id.in_(user_ids), RefreshTokenModel.is_revoked.is_(False))
            .values(is_revoked=True)
            .returning(RefreshTokenModel.id, RefreshTokenModel.user_id)
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        await self._session.flush()
        return [RevokedTokenDTO(id=row[0], user_id=row[1]) for row in rows]

    async def delete_expired_before(self, cutoff: datetime, limit: int | None = None) -> int:
        """
        Масове або пакетне фізичне видалення протермінованих токенів.

        Використовує прямий DML delete з synchronize_session=False для максимальної
        швидкодії при великих обсягах даних без накладних витрат на Identity Map.
        Якщо вказано limit, видалення виконується порцією (батчем) через підвибірку ID
        з блокуванням з пропуском зайнятих рядків (skip_locked=True) для безпечної паралельної роботи.
        """
        where_clause = or_(
            RefreshTokenModel.expires_at < cutoff,
            RefreshTokenModel.max_session_expiration < cutoff,
        )

        if limit is not None:
            subquery = select(RefreshTokenModel.id).where(where_clause).limit(limit).with_for_update(skip_locked=True)
            stmt = (
                delete(RefreshTokenModel)
                .where(RefreshTokenModel.id.in_(subquery))
                .execution_options(synchronize_session=False)
            )
        else:
            stmt = delete(RefreshTokenModel).where(where_clause).execution_options(synchronize_session=False)

        result = await self._session.execute(stmt)
        return max(getattr(result, "rowcount", 0), 0)
