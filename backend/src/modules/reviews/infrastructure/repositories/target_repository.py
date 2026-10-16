from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from src.infrastructure.db.repositories.base_crud_repository import SqlAlchemyBaseCrudRepository
from src.modules.reviews.domain.interfaces import ITargetRepository
from src.modules.reviews.domain.models.target import Target
from src.modules.reviews.infrastructure.mappers.target_mapper import TargetMapper
from src.modules.reviews.infrastructure.models.target_model import TargetModel


class SqlAlchemyTargetRepository(SqlAlchemyBaseCrudRepository[Target, TargetModel], ITargetRepository):
    """SQLAlchemy реалізація репозиторію об'єктів оцінювання (Target)."""

    _model_cls = TargetModel
    _mapper = TargetMapper

    async def save(self, target: Target, /) -> None:
        orm = await self._session.get(TargetModel, target.id)
        if orm is None:
            orm = TargetMapper.to_orm(target)
            self._session.add(orm)
        else:
            TargetMapper.update_to_orm(orm, target)
        await self._session.flush()
        target.version = orm.version

    async def get_by_slug(self, slug: str, /) -> Target | None:
        stmt = select(TargetModel).where(
            TargetModel.slug == slug.strip().lower(),
            TargetModel.deleted_at.is_(None),
        )
        res = await self._session.execute(stmt)
        orm = res.scalar_one_or_none()
        return TargetMapper.to_domain(orm) if orm is not None else None

    async def exists_by_slug(self, slug: str, /, exclude_id: UUID | None = None) -> bool:
        stmt = select(1).where(
            TargetModel.slug == slug.strip().lower(),
            TargetModel.deleted_at.is_(None),
        )
        if exclude_id is not None:
            stmt = stmt.where(TargetModel.id != exclude_id)
        stmt = stmt.limit(1)
        res = await self._session.execute(stmt)
        return bool(res.scalar() is not None)

    async def list_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Target]:
        stmt = select(TargetModel).where(TargetModel.deleted_at.is_(None))

        if category:
            stmt = stmt.where(TargetModel.category == category.strip().lower())
        if search:
            clean_search = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                (func.lower(TargetModel.title).ilike(clean_search)) | (func.lower(TargetModel.slug).ilike(clean_search))
            )

        stmt = stmt.order_by(TargetModel.created_at.desc()).limit(limit).offset(offset)
        res = await self._session.execute(stmt)
        return [TargetMapper.to_domain(orm) for orm in res.scalars().all()]

    async def count_targets(
        self,
        *,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(TargetModel).where(TargetModel.deleted_at.is_(None))

        if category:
            stmt = stmt.where(TargetModel.category == category.strip().lower())
        if search:
            clean_search = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                (func.lower(TargetModel.title).ilike(clean_search)) | (func.lower(TargetModel.slug).ilike(clean_search))
            )

        res = await self._session.execute(stmt)
        return res.scalar_one() or 0
