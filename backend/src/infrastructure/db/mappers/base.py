from typing import Protocol


class BaseMapper[TDomain, TModel](Protocol):
    """Протокол для Data Mappers між чистими доменними агрегатами та ORM-моделями."""

    @staticmethod
    def to_domain(model: TModel) -> TDomain: ...

    @staticmethod
    def to_orm(domain: TDomain) -> TModel: ...
