from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Protocol

from fastapi import HTTPException, Query, status
from sqlalchemy import ColumnExpressionArgument, Select, asc, desc


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class SortItem[TField: StrEnum]:
    """
    Окремий критерій сортування: типізоване поле (Enum) та напрямок (ASC/DESC).
    """

    field: TField
    order: SortOrder = SortOrder.ASC

    @property
    def is_desc(self) -> bool:
        """Чи є сортування за спаданням."""
        return self.order == SortOrder.DESC


class MultiSort[TField: StrEnum]:
    """
    Ітерований, безпечний до типів контейнер мульти-сортування із збереженням пріоритету колонок.
    """

    __slots__ = ("_items",)

    def __init__(self, items: Sequence[SortItem[TField]]) -> None:
        self._items: tuple[SortItem[TField], ...] = tuple(items)

    def __iter__(self) -> Iterator[SortItem[TField]]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> SortItem[TField]:
        return self._items[index]

    def __repr__(self) -> str:
        return f"MultiSort({list(self._items)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MultiSort):
            return self._items == other._items
        return False

    @classmethod
    def empty(cls) -> "MultiSort[TField]":
        """Створення порожнього контейнера сортування."""
        return cls(())

    @classmethod
    def from_items(cls, *items: SortItem[TField]) -> "MultiSort[TField]":
        """Фабричний метод створення зі списку SortItem."""
        return cls(items)

    @classmethod
    def from_raw(cls, raw_values: Sequence[str], field_enum: type[TField]) -> "MultiSort[TField]":
        """
        Фабричний метод для швидкого створення MultiSort із рядків (зручно для тестів).
        Підтримує префікси '-' (DESC) та '+' / без префіксу (ASC).
        """
        allowed = {e.value: e for e in field_enum}
        items: list[SortItem[TField]] = []
        for raw in raw_values:
            for part in raw.split(","):
                token = part.strip()
                if not token:
                    continue
                if token.startswith("-"):
                    field_name = token[1:]
                    order = SortOrder.DESC
                elif token.startswith("+"):
                    field_name = token[1:]
                    order = SortOrder.ASC
                else:
                    field_name = token
                    order = SortOrder.ASC

                if field_name not in allowed:
                    raise ValueError(f"Unknown sort field: {field_name}")
                items.append(SortItem(field=allowed[field_name], order=order))
        return cls(items)


class SortDependency[TField: StrEnum](Protocol):
    async def __call__(self, sort: list[str] | None = None) -> MultiSort[TField]: ...


def sort_dependency[TField: StrEnum](
    field_enum: type[TField],
    default: Sequence[str] = ("-created_at",),
    max_fields: int = 3,
) -> SortDependency[TField]:
    """
    Фабрика FastAPI Dependency для типізованого мульти-сортування (JSON:API style).

    - Формує опис дозволених полів та дефолтів для Swagger UI / OpenAPI.
    - Парсить як рядки з комами (?sort=-created_at,name), так і повторювані параметри (?sort=-created_at&sort=name).
    - Перевіряє обмеження на кількість полів (за замовчуванням до 3).
    - Валідує кожне поле проти field_enum (повертає HTTP 422 при помилці).
    """
    allowed_fields: dict[str, TField] = {e.value: e for e in field_enum}
    allowed_fields_doc = ", ".join(f"`{f}`" for f in allowed_fields)
    default_doc = ", ".join(f"`{d}`" for d in default)

    description = (
        f"Мульти-колонкове сортування (JSON:API style, макс. {max_fields} полів).\n\n"
        f"- Префікс `-` означає спадання (DESC), без префіксу або `+` — зростання (ASC).\n"
        f"- Можна передавати через кому (`?sort=-field1,field2`) "
        f"або повторюваним параметром (`?sort=-field1&sort=field2`).\n\n"
        f"**Дозволені поля:** {allowed_fields_doc}.\n\n"
        f"**За замовчуванням:** {default_doc}."
    )

    extra_metadata: dict[str, Any] = {
        "example": list(default),
        "x-allowed-sorting": list(allowed_fields.keys()),
        "x-default-sorting": list(default),
        "x-max-sorting-fields": max_fields,
    }

    async def _parse_sort(
        sort: Annotated[
            list[str] | None,
            Query(
                description=description,
                json_schema_extra=extra_metadata,
            ),
        ] = None,
    ) -> MultiSort[TField]:
        raw_values = sort if (sort is not None and len(sort) > 0) else list(default)
        tokens: list[tuple[str, SortOrder]] = []

        for raw in raw_values:
            for part in raw.split(","):
                token = part.strip()
                if not token:
                    continue

                if token.startswith("-"):
                    field_name = token[1:]
                    order = SortOrder.DESC
                elif token.startswith("+"):
                    field_name = token[1:]
                    order = SortOrder.ASC
                else:
                    field_name = token
                    order = SortOrder.ASC

                tokens.append((field_name, order))

        if len(tokens) > max_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "error_code": "SORT_TOO_MANY_FIELDS",
                    "message": f"Дозволено максимум {max_fields} параметри(ів) сортування, отримано: {len(tokens)}",
                },
            )

        items: list[SortItem[TField]] = []
        for field_name, order in tokens:
            if field_name not in allowed_fields:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "error_code": "INVALID_SORT_FIELD",
                        "message": (
                            f"Некоректне поле сортування '{field_name}'. Дозволені поля: {list(allowed_fields.keys())}"
                        ),
                    },
                )
            items.append(SortItem(field=allowed_fields[field_name], order=order))

        return MultiSort(items)

    return _parse_sort


def apply_sorting[TField: StrEnum](
    stmt: Select[Any],
    sort: MultiSort[TField],
    sort_map: Mapping[TField, ColumnExpressionArgument[Any]],
    id_column: ColumnExpressionArgument[Any],
) -> Select[Any]:
    """
    Застосовує мульти-колонкове сортування до запиту SQLAlchemy з обов'язковим tie-breaker по id.

    1. Додає кожне поле із sort у порядку їх черговості.
    2. Наприкінці додає сортування по id_column (ASC) для гарантії детермінованості
       порядку рядків при однакових значеннях інших полів (якщо id_column не був доданий раніше).
    """
    has_id_sorted = False

    for item in sort:
        col = sort_map.get(item.field)
        if col is not None:
            stmt = stmt.order_by(desc(col) if item.is_desc else asc(col))
            if col is id_column:
                has_id_sorted = True

    # Обов'язковий детермінований tie-breaker для стабільної пагінації у PostgreSQL
    if not has_id_sorted:
        stmt = stmt.order_by(asc(id_column))

    return stmt
