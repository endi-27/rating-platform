from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from uuid6 import uuid7

POSTGRES_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовий клас для всіх ORM моделей SQLAlchemy з конвенцією найменування."""

    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """
    Міксин первинного ключа UUIDv7 (RFC 9562).
    Часово-впорядкований (time-ordered), що гарантує послідовну вставку
    у B-Tree індекси PostgreSQL без фрагментації сторінок.
    """

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)


class VersionedMixin:
    """Міксин оптимістичного блокування (OCC) за версією."""

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}


class CreatedAtMixin:
    """
    Міксин часової мітки створення (UTC) для незмінних записів (Append-Only).
    Використовується для таблиць аудит-логів, транзакційних подій та метрик,
    де оновлення записів заборонено бізнес-правилами (відсутнє updated_at).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


class TimestampMixin:
    """
    Міксин системних часових міток створення та оновлення (UTC).
    Поєднує DDL-рівень server_default=func.now() та Python-рівень default/onupdate UTC.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        onupdate=lambda: datetime.now(UTC),
        nullable=True,
    )


class SoftDeleteMixin:
    """Міксин м'якого видалення (UTC часова мітка deleted_at)."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class CreatedByMixin:
    """Міксин аудиту автора створення запису (UUIDv7 користувача)."""

    @declared_attr
    def created_by_id(cls) -> Mapped[UUID | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


@runtime_checkable
class IdentifiableModelProtocol(Protocol):
    """Протокол для ORM-моделей з первинним ключем UUID (RFC 9562 / UUIDv7)."""

    id: Mapped[UUID]


@runtime_checkable
class SoftDeleteModelProtocol(IdentifiableModelProtocol, Protocol):
    """Протокол для ORM-моделей з підтримкою Soft Delete (deleted_at)."""

    deleted_at: Mapped[datetime | None]
