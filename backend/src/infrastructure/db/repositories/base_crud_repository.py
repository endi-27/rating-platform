import abc
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.core import ResourceLockedException
from src.infrastructure.db.base import IdentifiableModelProtocol
from src.infrastructure.db.repositories.base_read_repository import SqlAlchemyBaseReadRepository


class SqlAlchemyBaseCrudRepository[TDomain, TModel: IdentifiableModelProtocol](
    SqlAlchemyBaseReadRepository[TDomain, TModel], abc.ABC
):
    """Базовий CRUD репозиторій з обов'язковим методом save та Hard Delete."""

    @abc.abstractmethod
    async def save(self, entity: TDomain, /) -> None:
        """Збереження доменного агрегата в БД."""
        ...

    async def delete_by_id(self, entity_id: UUID, /) -> bool:
        """
        Фізичне видалення (Hard Delete) запису за його id із синхронізацією сесії ORM.

        Чому використовується session.get() + session.delete(orm) замість raw delete():
        1. Завантаження сутності в Identity Map гарантує коректне виконання ORM-каскадів.
        2. Викликає життєві події (lifecycle hooks) SQLAlchemy та виключає появу
           застарілих (stale) об'єктів у поточній сесії транзакції.
        3. flush() негайно транслює DELETE у БД, дозволяючи перевірити наявність помилок/конфліктів.
           При порушенні зовнішніх ключів (ON DELETE RESTRICT, pgcode 23503) викидає ResourceLockedException.
        """
        orm = await self._session.get(self._model_cls, entity_id)
        if orm is not None:
            await self._session.delete(orm)
            try:
                await self._session.flush()
            except IntegrityError as exc:
                pgcode = getattr(exc.orig, "sqlstate", getattr(exc.orig, "pgcode", None))
                if pgcode == "23503" or "foreign key" in str(exc).lower():
                    raise ResourceLockedException(
                        "Неможливо остаточно видалити запис, оскільки він використовується в пов'язаних даних."
                    ) from exc
                raise
            return True
        return False
