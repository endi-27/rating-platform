from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm.base import NO_VALUE


def is_loaded(model: object, attr_name: str) -> bool:
    """Безпечно перевіряє, чи завантажений зв'язок або атрибут ORM-моделі (для lazy='raise')."""
    insp = inspect(model, raiseerr=False)
    if insp is None:
        return hasattr(model, attr_name)
    attr = insp.attrs.get(attr_name)
    return bool(attr is not None and attr.loaded_value is not NO_VALUE)


def get_loaded(model: object, attr_name: str, default: Any = None) -> Any:
    """Безпечно повертає завантажений зв'язок ORM-моделі без спрацювання lazy='raise'.

    Якщо зв'язок не був явно завантажений (Eager Loading не застосовувався),
    повертає default (за замовчуванням None).
    """
    insp = inspect(model, raiseerr=False)
    if insp is None:
        return getattr(model, attr_name, default)
    attr = insp.attrs.get(attr_name)
    if attr is None or attr.loaded_value is NO_VALUE:
        return default
    return attr.loaded_value
