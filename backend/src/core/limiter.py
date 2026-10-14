from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core.config import settings

# Ініціалізація SlowAPI Limiter з використанням Redis пулу для розподіленого rate limiting
# Автоматично вимикається у тестовому середовищі (settings.is_testing)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri=settings.redis.url,
    enabled=not settings.is_testing,
)
