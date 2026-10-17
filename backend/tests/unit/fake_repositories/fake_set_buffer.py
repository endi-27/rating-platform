from __future__ import annotations

from uuid import UUID

from src.core import ISetBuffer


class FakeSetBuffer(ISetBuffer):
    """Швидкий тестовий дублер розподіленого буфера на базі множин Redis Set (In-Memory Set Buffer)."""

    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = {}

    async def add(self, key: str, *values: str | UUID) -> int:
        if key not in self.sets:
            self.sets[key] = set()
        initial_len = len(self.sets[key])
        for val in values:
            self.sets[key].add(str(val))
        return len(self.sets[key]) - initial_len

    async def pop_batch(self, key: str, batch_size: int = 100) -> list[str]:
        target_set = self.sets.get(key)
        if not target_set:
            return []
        batch: list[str] = []
        while target_set and len(batch) < batch_size:
            batch.append(target_set.pop())
        return batch

    async def count(self, key: str) -> int:
        return len(self.sets.get(key, set()))
