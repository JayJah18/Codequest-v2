from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def save_generated_tasks(tasks: list[dict[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")


def save_generated_answers(answers: list[dict[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(answers, indent=2), encoding="utf-8")


def save_marking_results_csv(results: list[dict[str, Any]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not results:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = sorted({key for item in results for key in item.keys()})
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
