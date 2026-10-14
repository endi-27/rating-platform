from datetime import UTC, datetime

from src.core import IUnitOfWork, logger
from src.modules.auth.domain import IRefreshTokenRepository


class CleanupExpiredTokensUseCase:
    """
    Use Case для пакетного фізичного очищення протермінованих сесійних refresh-токенів.

    Виконує видалення порціями (батчами) для запобігання lock contention
    та розростанню WAL у базі даних PostgreSQL. Кожна порція фіксується
    окремим комітом Unit of Work.
    """

    def __init__(
        self,
        uow: IUnitOfWork,
        refresh_repo: IRefreshTokenRepository,
    ) -> None:
        self._uow = uow
        self._refresh_repo = refresh_repo

    async def execute(self, cutoff: datetime | None = None, batch_size: int = 1000) -> int:
        if cutoff is None:
            cutoff = datetime.now(UTC)
        elif cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)

        effective_batch_size = max(1, batch_size)
        async with self._uow:
            total_deleted = await self._run_cleanup(cutoff, effective_batch_size)

        logger.info(
            "Очищення застарілих сесійних токенів успішно завершено. Видалено: {count}",
            count=total_deleted,
        )
        return total_deleted

    async def _run_cleanup(self, cutoff: datetime, effective_batch_size: int) -> int:
        total_deleted = 0
        while True:
            deleted_in_batch = await self._refresh_repo.delete_expired_before(
                cutoff=cutoff,
                limit=effective_batch_size,
            )
            if deleted_in_batch == 0:
                break

            await self._uow.commit()
            total_deleted += deleted_in_batch

            if deleted_in_batch < effective_batch_size:
                break
        return total_deleted
