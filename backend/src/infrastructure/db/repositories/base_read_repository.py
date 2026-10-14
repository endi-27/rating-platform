import abc
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from src.infrastructure.db.base import IdentifiableModelProtocol
from src.infrastructure.db.mappers.base import BaseMapper


class SqlAlchemyBaseReadRepository[TDomain, TModel: IdentifiableModelProtocol](abc.ABC):
    """Базовий репозиторій для операцій читання через SQLAlchemy 2.0."""

    _model_cls: type[TModel]
    _mapper: type[BaseMapper[TDomain, TModel]]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, model: TModel) -> TDomain:
        """Конвертація ORM-моделі в доменну сутність через зареєстрований Data Mapper."""
        return self._mapper.to_domain(model)

    def _default_options(self) -> Sequence[ExecutableOption]:
        """Опції завантаження зв'язків (selectinload тощо). Перевизначається за потреби."""
        return ()

    async def get_by_id(self, entity_id: UUID, /) -> TDomain | None:
        """Отримання сутності за первинним ключем (UUIDv7)."""
        stmt = select(self._model_cls).options(*self._default_options()).where(self._model_cls.id == entity_id)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_domain(orm) if orm is not None else None

    async def exists_by_id(self, entity_id: UUID, /) -> bool:
        """Швидка оптимізована перевірка наявності запису за id через SELECT 1."""
        stmt = select(1).where(self._model_cls.id == entity_id).limit(1)
        result = await self._session.execute(stmt)
        return bool(result.scalar() is not None)
