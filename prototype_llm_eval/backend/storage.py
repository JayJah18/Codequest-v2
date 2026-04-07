from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InMemoryTaskStore:
    tasks: dict[str, dict[str, Any]]

    def save_task(self, task: dict[str, Any]) -> None:
        self.tasks[task["task_id"]] = task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self.tasks.get(task_id)


task_store = InMemoryTaskStore(tasks={})
