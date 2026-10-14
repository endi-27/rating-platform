from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_IGNORE_KEYS: tuple[str, ...] = (
    "service",
    "db",
    "session",
    "request",
    "response",
    "current_user",
    "_current_user",
    "current_user_id",
    "actor_user_id",
    "actor_id",
    "uow",
    "bus",
    "event_bus",
    "publisher",
    "sse_publisher",
    "background_tasks",
    "dispatcher",
)

_DEPENDENCY_SUFFIXES: tuple[str, ...] = (
    "_service",
    "_queries",
    "_query_service",
    "_uc",
    "_use_case",
    "_repo",
    "_repository",
    "_gateway",
    "_bus",
    "_publisher",
    "_uow",
    "_client",
    "_manager",
    "_dispatcher",
)

_DEPENDENCY_TYPE_NAMES: tuple[str, ...] = (
    "Service",
    "QueryService",
    "UseCase",
    "Repository",
    "Gateway",
    "Client",
    "Dispatcher",
    "Session",
    "AsyncSession",
    "UnitOfWork",
    "EventBus",
    "ConnectionManager",
    "Publisher",
    "Request",
    "Response",
    "BackgroundTasks",
)


def _is_dependency(key: str, val: Any, ignore_keys: tuple[str, ...] = DEFAULT_IGNORE_KEYS) -> bool:
    """Визначення, чи є параметр ін'єктованою службовою залежністю (DI), а не параметром запиту."""
    if key in ignore_keys or key == "_" or key.startswith("_"):
        return True
    if key.endswith(_DEPENDENCY_SUFFIXES):
        return True
    type_name = type(val).__name__
    if any(type_name.endswith(suffix) for suffix in _DEPENDENCY_TYPE_NAMES):
        return True
    if hasattr(val, "effective_permissions"):
        return True
    return (
        not isinstance(
            val,
            (
                str,
                int,
                float,
                bool,
                bytes,
                list,
                tuple,
                set,
                frozenset,
                dict,
                Enum,
                BaseModel,
                UUID,
                Decimal,
                datetime,
                date,
                time,
            ),
        )
        and str(val).startswith("<")
        and " at 0x" in str(val)
    )


def _normalize_for_dict(val: Any) -> Any:
    """Рекурсивна нормалізація структури для детерміністичної JSON-серіалізації словників."""
    if val is None or isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, BaseModel):
        return val.model_dump(mode="json")
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, (UUID, Decimal)):
        return str(val)
    if isinstance(val, (set, frozenset)):
        normalized_list = [_normalize_for_dict(x) for x in val]
        return sorted(normalized_list, key=lambda x: json.dumps(x, sort_keys=True, default=str))
    if isinstance(val, (list, tuple)):
        return [_normalize_for_dict(x) for x in val]
    if isinstance(val, dict):
        return {str(k): _normalize_for_dict(v) for k, v in val.items()}
    return str(val)


def serialize_value(val: Any) -> str:
    """Серіалізація значення доменного аргументу для побудови кеш-ключа."""
    if val is None:
        return "null"
    if isinstance(val, BaseModel):
        return val.model_dump_json()
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, Enum):
        return str(val.value)
    if isinstance(val, (UUID, Decimal)):
        return str(val)
    if isinstance(val, (set, frozenset)):
        return "[" + ",".join(sorted(serialize_value(x) for x in val)) + "]"
    if isinstance(val, (list, tuple)):
        return "[" + ",".join(serialize_value(x) for x in val) + "]"
    if isinstance(val, dict):
        normalized = {str(k): _normalize_for_dict(v) for k, v in sorted(val.items(), key=lambda item: str(item[0]))}
        return json.dumps(normalized, sort_keys=True)
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, (int, float)):
        return str(val)
    return str(val)


def serialize_cache_parts(
    kwargs: dict[str, Any],
    ignore_keys: tuple[str, ...] = DEFAULT_IGNORE_KEYS,
) -> list[str]:
    """Формування списку серіалізованих параметрів запиту з фільтрацією DI-залежностей."""
    parts: list[str] = []
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if _is_dependency(k, v, ignore_keys=ignore_keys):
            continue
        parts.append(f"{k}={serialize_value(v)}")
    return parts


def generate_md5_hash(module: str, func_name: str, parts: list[str]) -> str:
    """Генерація стабільного MD5 хешу від імені функції та її серіалізованих параметрів."""
    raw = f"{module}:{func_name}:" + ":".join(parts)
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324


def _extract_current_user(kw: dict[str, Any], request: Request | None) -> Any:
    """Уніфіковане вилучення об'єкта поточного користувача з kwargs або request."""
    user = kw.get("current_user") or kw.get("_current_user") or kw.get("user")
    if user and hasattr(user, "id"):
        return user
    for v in kw.values():
        if hasattr(v, "id") and hasattr(v, "effective_permissions"):
            return v
    if request and hasattr(request, "state") and hasattr(request.state, "user") and hasattr(request.state.user, "id"):
        return request.state.user
    return None


def default_key_builder(
    __function: Callable[..., Any],
    __namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    namespace: str | None = None,
) -> str:
    """
    Глобальний білдер ключів для спільних ендпоінтів.
    Враховує exclude_current_user / exclude_current та гарантовано підмішує id поточного користувача.
    """
    func = __function
    ns = namespace if namespace is not None else __namespace
    kw = dict(kwargs or {})
    parts = serialize_cache_parts(kw)
    if args:
        parts = [f"arg_{i}={serialize_value(a)}" for i, a in enumerate(args)] + parts

    if kw.get("exclude_current_user") or kw.get("exclude_current"):
        user = _extract_current_user(kw, request)
        if not user or not hasattr(user, "id"):
            raise ValueError(
                "Не вдалося визначити поточного користувача для формування кеш-ключа з exclude_current_user"
            )
        parts.append(f"current_user_id={user.id}")
        parts.sort()

    cache_hash = generate_md5_hash(func.__module__, func.__name__, parts)
    return f"{ns}:{cache_hash}" if ns else cache_hash


def resource_key_builder(
    __function: Callable[..., Any],
    __namespace: str = "",
    *,
    request: Request | None = None,
    response: Response | None = None,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    namespace: str | None = None,
) -> str:
    """Білдер ключів для одиничних сутностей за їхнім ID у kwargs або path_params."""
    func = __function
    base_ns = namespace if namespace is not None else __namespace
    kw = dict(kwargs or {})
    resource_id = (
        kw.get("id")
        or kw.get("entity_id")
        or kw.get("user_id")
        or kw.get("role_id")
        or kw.get("permission_id")
        or kw.get("code")
    )
    if resource_id is None:
        for k, v in kw.items():
            if k.endswith("_id") and v is not None and not _is_dependency(k, v):
                resource_id = v
                break

    if resource_id is None and request and hasattr(request, "path_params"):
        resource_id = (
            request.path_params.get("id")
            or request.path_params.get("entity_id")
            or request.path_params.get("user_id")
            or request.path_params.get("role_id")
            or request.path_params.get("permission_id")
            or request.path_params.get("code")
        )
        if resource_id is None:
            for k, v in request.path_params.items():
                if k.endswith("_id") and v is not None and k not in DEFAULT_IGNORE_KEYS:
                    resource_id = v
                    break

    parts = serialize_cache_parts(kw)
    if args:
        parts = [f"arg_{i}={serialize_value(a)}" for i, a in enumerate(args)] + parts

    if resource_id is not None:
        res_str = str(resource_id)
        ns = f"{base_ns}:{res_str}" if base_ns else res_str
    else:
        ns = base_ns

    cache_hash = generate_md5_hash(func.__module__, func.__name__, parts)
    return f"{ns}:{cache_hash}" if ns else cache_hash
