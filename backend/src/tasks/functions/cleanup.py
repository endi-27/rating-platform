import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles.os
import anyio.to_thread
from arq import Retry
from loguru import logger
from sqlalchemy.exc import DBAPIError, OperationalError

from src.core import settings
from src.infrastructure.db import SqlAlchemyUnitOfWork


def _sync_cleanup_expired_files(temp_dir: Path, max_age_seconds: int) -> int:
    """
    Синхронна функція очищення застарілих файлів для запуску в окремому потоці (Worker Thread).
    Не блокує асинхронний цикл подій ARQ воркера.
    """
    now = time.time()
    deleted_count = 0

    try:
        for file_path in temp_dir.iterdir():
            try:
                # Обробляємо виключно файли, пропускаючи вкладені піддиректорії
                if not file_path.is_file():
                    continue

                # Ігноруємо службові файли (наприклад, .gitkeep)
                if file_path.name.startswith("."):
                    continue

                # Ігноруємо файли, які прямо зараз записуються іншими процесами
                if file_path.name.endswith(".tmp") or file_path.name.endswith(".part"):
                    continue

                # Безпечне отримання часу модифікації (захист від Race Condition)
                file_age = now - file_path.stat().st_mtime

                if file_age > max_age_seconds:
                    file_path.unlink(missing_ok=True)
                    deleted_count += 1
                    logger.info(
                        "[Task-CleanUpTempFiles] Видалено застарілий тимчасовий файл: {path}",
                        path=str(file_path),
                    )

            except FileNotFoundError:
                # Файл вже було видалено паралельним процесом
                continue
            except PermissionError as exc:
                logger.warning(
                    "[Task-CleanUpTempFiles] Немає прав для видалення {path}: {exc}",
                    path=str(file_path),
                    exc=str(exc),
                )
            except Exception as exc:
                logger.warning(
                    "[Task-CleanUpTempFiles] Помилка обробки файлу {path}: {exc}",
                    path=str(file_path),
                    exc=str(exc),
                )

    except Exception as exc:
        logger.error(
            "[Task-CleanUpTempFiles] Критична помилка під час обходу тимчасової директорії: {exc}",
            exc=str(exc),
        )

    return deleted_count


async def cleanup_expired_temp_files_task(ctx: dict[Any, Any], *args: Any, **kwargs: Any) -> int:
    """
    Асинхронна задача ARQ для очищення застарілих тимчасових файлів.
    Запускає важкий дисковий I/O в окремому потоці через anyio.to_thread.run_sync.
    """
    temp_dir = Path(settings.storage.temp_dir)
    max_age_seconds = settings.storage.temp_file_max_age_seconds

    # Асинхронна перевірка існування директорії
    if not await aiofiles.os.path.exists(temp_dir) or not await aiofiles.os.path.isdir(temp_dir):
        logger.debug("[Task-CleanUpTempFiles] Тимчасова директорія {dir} не існує", dir=str(temp_dir))
        return 0

    deleted_count: int = await anyio.to_thread.run_sync(_sync_cleanup_expired_files, temp_dir, max_age_seconds)
    logger.info("[Task-CleanUpTempFiles] Очищення завершено. Видалено файлів: {count}", count=deleted_count)
    return deleted_count


async def cleanup_expired_refresh_tokens_task(ctx: dict[Any, Any], *args: Any, **kwargs: Any) -> int:
    """
    Асинхронна задача ARQ для періодичного пакетного очищення протермінованих сесійних refresh-токенів.

    Використовує CleanupExpiredTokensUseCase для батчованого видалення з комітом кожної порції,
    що запобігає тривалим блокуванням рядків та розростанню WAL.
    При транзитних помилках бази даних задача автоматично повторюється через ARQ Retry
    з експоненційною затримкою.
    """
    from src.modules.auth import (
        CleanupExpiredTokensUseCase,
        SqlAlchemyRefreshTokenRepository,
    )

    session_factory = ctx.get("session_factory")
    if session_factory is None:
        logger.error("[Task-CleanUpTokens] Фабрику сесій БД не знайдено в контексті воркера ARQ")
        raise RuntimeError("Фабрику сесій БД не знайдено в контексті воркера ARQ")

    job_try = int(ctx.get("job_try", 1))
    now = datetime.now(UTC)

    try:
        async with session_factory() as session:
            uow = SqlAlchemyUnitOfWork(session=session)
            repo = SqlAlchemyRefreshTokenRepository(session=session)
            use_case = CleanupExpiredTokensUseCase(uow=uow, refresh_repo=repo)
            deleted_count = await use_case.execute(cutoff=now, batch_size=1000)

        logger.info(
            "[Task-CleanUpTokens] Очищення завершено. Видалено застарілих токенів: {count}",
            count=deleted_count,
        )
        return deleted_count

    except (OperationalError, DBAPIError, TimeoutError) as exc:
        defer_seconds = min(15 * (2 ** (job_try - 1)), 300)
        logger.warning(
            "[Task-CleanUpTokens] Транзитна помилка БД під час очищення токенів ({exc}). "
            "Спроба {job_try}. Повтор через {defer}с.",
            exc=str(exc),
            job_try=job_try,
            defer=defer_seconds,
        )
        raise Retry(defer=defer_seconds) from exc
