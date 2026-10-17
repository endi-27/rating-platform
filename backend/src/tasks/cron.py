from arq.cron import cron

from src.tasks.functions import (
    cleanup_expired_refresh_tokens_task,
    cleanup_expired_temp_files_task,
    process_dirty_target_ratings_task,
)

# Реєстрація періодичних задач воркера ARQ
cron_jobs = [
    # Пакетний перерахунок байєсівських рейтингів кожні 15 секунд (Batch Accumulation)
    cron(
        process_dirty_target_ratings_task,
        second=set(range(0, 60, 15)),
        run_at_startup=False,
        unique=True,
    ),
    # Очищення застарілих тимчасових файлів кожні 30 хвилин (на 0-й та 30-й хвилині)
    cron(
        cleanup_expired_temp_files_task,
        minute={0, 30},
        run_at_startup=False,
    ),
    # Щоденне очищення протермінованих сесійних токенів о 03:00 UTC
    cron(
        cleanup_expired_refresh_tokens_task,
        hour={3},
        minute={0},
        run_at_startup=False,
    ),
]
