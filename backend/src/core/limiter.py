from typing import Any, cast

from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings

# Ініціалізація SlowAPI Limiter з використанням Redis пулу для розподіленого rate limiting
# Автоматично вимикається у тестовому середовищі (settings.is_testing)
# При падінні Redis перемикається на in-memory fallback та ігнорує помилки з'єднання (swallow_errors)
# slowapi анотує storage_options як Dict[str, str], проте драйвер Redis вимагає числових таймаутів
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri=settings.redis.url,
    storage_options=cast(Any, {"socket_connect_timeout": 1, "socket_timeout": 1}),
    swallow_errors=True,
    in_memory_fallback_enabled=True,
    enabled=not settings.is_testing,
)
