from typing import Any

from arq import create_pool
from arq.connections import ArqRedis
from arq.connections import RedisSettings as ArqRedisSettings

from src.core import logger, settings


class TaskDispatcher:
    """Диспетчер для постановки задач у фонову чергу ARQ з коду додатку.

    Усі публічні методи є типізованими обгортками над приватним `_enqueue_task`.
    Пряме використання `_enqueue_task` із рядком-ідентифікатором ззовні заборонено —
    це захищає від magic strings та помилок при перейменуванні задач.
    """

    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        """Отримання або лінива ініціалізація пулу підключень ARQ до Redis."""
        if self._pool is None:
            self._pool = await create_pool(
                ArqRedisSettings(
                    host=settings.redis.host,
                    port=settings.redis.port,
                    password=settings.redis.password,
                    database=settings.redis.databases.task,
                )
            )
        return self._pool

    async def _enqueue_task(self, function_name: str, *args: Any, **kwargs: Any) -> str | None:
        """Внутрішній примітив постановки задачі у чергу ARQ за іменем функції.

        Використовується виключно типізованими публічними методами цього класу.
        """
        try:
            pool = await self._get_pool()
            job = await pool.enqueue_job(function_name, *args, _queue_name=settings.arq.queue_name, **kwargs)
            if job:
                logger.info("Задачу {fn} поставлено в чергу ARQ (job_id: {id})", fn=function_name, id=job.job_id)
                return job.job_id
            return None
        except Exception as err:
            logger.error(
                "Не вдалося поставити задачу {function_name} у чергу: {err}",
                function_name=function_name,
                err=str(err),
            )
            return None

    async def enqueue_cleanup_temp_files(self) -> str | None:
        """Типізована відправка задачі очищення тимчасових файлів."""
        from src.tasks.functions import cleanup_expired_temp_files_task

        return await self._enqueue_task(cleanup_expired_temp_files_task.__name__)

    async def close(self) -> None:
        """Закриття клієнтського пулу ARQ."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


_global_dispatcher: TaskDispatcher | None = None


def get_task_dispatcher() -> TaskDispatcher:
    """FastAPI Depends провайдер для отримання TaskDispatcher."""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = TaskDispatcher()
    return _global_dispatcher


async def close_task_dispatcher() -> None:
    """Закриття глобального екземпляра TaskDispatcher при зупинці додатку."""
    global _global_dispatcher
    if _global_dispatcher is not None:
        await _global_dispatcher.close()
        _global_dispatcher = None
