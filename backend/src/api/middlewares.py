import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware
from uuid6 import uuid7
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.core import (
    limiter,
    logger,
    set_correlation_id,
    settings,
)
from src.infrastructure.cache import cache_fallback_ctx


async def request_logger_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Контекстне логування кожного HTTP-запиту з унікальним request_id, діагностичними заголовками та заміром часу."""
    incoming_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
    request_id = incoming_id.strip() if incoming_id and incoming_id.strip() else uuid7().hex[:12]
    client_ip = request.client.host if request.client else "unknown"
    set_correlation_id(request_id)
    cache_fallback_ctx.set(False)

    with logger.contextualize(request_id=request_id, client_ip=client_ip):
        start_time = time.perf_counter()
        logger.info("Запит розпочато: {method} {path}", method=request.method, path=request.url.path)

        # Можливість штучної затримки для тестування алгоритмів балансування (ЛР 3)
        latency_to_simulate = settings.simulate_latency_ms
        header_latency = request.headers.get("X-Simulate-Latency-Ms")
        target_instance = request.headers.get("X-Simulate-Latency-Instance")

        apply_header_latency = not target_instance or target_instance.strip() == settings.instance_id
        if apply_header_latency and header_latency and header_latency.strip().isdigit():
            latency_to_simulate = max(latency_to_simulate, int(header_latency.strip()))
        if latency_to_simulate > 0:
            await asyncio.sleep(latency_to_simulate / 1000.0)
        try:
            response: Response = await call_next(request)
            process_time = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "Запит завершено: {method} {path} | Статус: {status} | Час: {time}ms | Node: {node}",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                time=process_time,
                node=settings.instance_id,
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Instance-ID"] = settings.instance_id
            response.headers["X-Process-Time-Ms"] = str(process_time)
            if cache_fallback_ctx.get():
                response.headers["X-Cache"] = "FALLBACK"
            return response
        except Exception as exc:
            process_time = round((time.perf_counter() - start_time) * 1000, 2)
            logger.opt(exception=exc).error(
                "Помилка виконання запиту: {method} {path} | Час: {time}ms | Node: {node}",
                method=request.method,
                path=request.url.path,
                time=process_time,
                node=settings.instance_id,
            )
            raise


async def no_cache_response_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Гарантує заборону збереження REST API відповідей у браузерному кеші клієнта (тільки для GET запитів)."""
    response: Response = await call_next(request)
    if request.method == "GET" and request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def setup_middlewares(app: FastAPI) -> None:
    """Реєстрація всіх глобальних HTTP-мідлварів додатку."""
    # Заборона браузерного кешування API відповідей
    app.middleware("http")(no_cache_response_middleware)

    # Логування запитів та трасування
    app.middleware("http")(request_logger_middleware)

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Прив'язка SlowAPI Limiter до стану додатку
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    # ProxyHeadersMiddleware для коректного визначення IP клієнта за Nginx зворотним проксі
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
