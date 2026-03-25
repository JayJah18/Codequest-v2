from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional

from .models import QuestionPackage


@dataclass
class QuestionStore:
    _items: Dict[str, QuestionPackage]
    _lock: Lock

    def __init__(self) -> None:
        self._items = {}
        self._lock = Lock()

    def put(self, pkg: QuestionPackage) -> None:
        with self._lock:
            self._items[pkg.question_id] = pkg

    def get(self, question_id: str) -> Optional[QuestionPackage]:
        with self._lock:
            return self._items.get(question_id)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

