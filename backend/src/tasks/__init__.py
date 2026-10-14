from typing import Any

from src.tasks.dispatcher import (
    TaskDispatcher,
    close_task_dispatcher,
    get_task_dispatcher,
)


def __getattr__(name: str) -> Any:
    if name == "WorkerSettings":
        from src.tasks.worker import WorkerSettings

        return WorkerSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TaskDispatcher",
    "WorkerSettings",
    "close_task_dispatcher",
    "get_task_dispatcher",
]
