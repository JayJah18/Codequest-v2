from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _env_csv(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def apply_pilot_task_filter(tasks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Filter tasks using env (all optional):
    - TASK_IDS: comma-separated task_id values (order preserved for selected tasks).
    - CONCEPT_FILTER: comma-separated concepts (case-insensitive); applied after TASK_IDS if both set.
    - TASK_LIMIT: positive int; applied last as a cap on the current list (file order if unordered).

    If only TASK_LIMIT is set, the first N tasks from the file are used.
    """
    task_ids = _env_csv("TASK_IDS")
    concepts = [c.lower() for c in _env_csv("CONCEPT_FILTER")]
    limit_raw = os.getenv("TASK_LIMIT", "").strip()

    meta: dict[str, Any] = {
        "TASK_IDS": task_ids,
        "CONCEPT_FILTER": concepts,
        "TASK_LIMIT": limit_raw or None,
    }

    out = [t for t in tasks if isinstance(t, dict)]

    if task_ids:
        wanted = set(task_ids)
        out = [t for t in out if str(t.get("task_id", "")).strip() in wanted]
        order = {tid: i for i, tid in enumerate(task_ids)}
        out.sort(key=lambda t: order.get(str(t.get("task_id", "")).strip(), 10_000))

    if concepts:
        cset = set(concepts)
        out = [t for t in out if str(t.get("concept", "")).strip().lower() in cset]

    if limit_raw:
        try:
            n = int(limit_raw)
        except ValueError as exc:
            raise ValueError(f"TASK_LIMIT must be a positive integer, got {limit_raw!r}") from exc
        if n < 1:
            raise ValueError(f"TASK_LIMIT must be >= 1, got {n}")
        out = out[:n]

    return out, meta


def load_generated_answers_by_task(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    path = data_dir / "generated_answers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: root must be a JSON array")
    by_task: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("task_id", "")).strip()
        if not tid:
            continue
        answers = item.get("answers")
        if not isinstance(answers, list):
            continue
        by_task[tid] = answers
    return by_task


def validate_generated_answers_align(
    tasks: list[dict[str, Any]],
    answers_by_task: dict[str, list[dict[str, Any]]],
) -> list[str]:
    errors: list[str] = []
    expected_variants = {"fully_correct", "partly_correct", "fully_incorrect"}
    for task in tasks:
        tid = str(task.get("task_id", "")).strip()
        if tid not in answers_by_task:
            errors.append(f"generated_answers.json: missing answers for task_id {tid!r}")
            continue
        answers = answers_by_task[tid]
        if len(answers) != 3:
            errors.append(f"{tid}: expected exactly 3 answer variants, got {len(answers)}")
            continue
        seen_variants: set[str] = set()
        for i, ans in enumerate(answers, start=1):
            if not isinstance(ans, dict):
                errors.append(f"{tid}: answers[{i}] must be an object")
                continue
            aid = str(ans.get("answer_id", "")).strip()
            vt = str(ans.get("variant_type", "")).strip()
            code = ans.get("code")
            if not aid:
                errors.append(f"{tid}: answers[{i}] missing answer_id")
            if vt not in expected_variants:
                errors.append(f"{tid}: answers[{i}] invalid variant_type {vt!r}")
            elif vt in seen_variants:
                errors.append(f"{tid}: duplicate variant_type {vt!r}")
            else:
                seen_variants.add(vt)
            if not isinstance(code, str) or not code.strip():
                errors.append(f"{tid}: answers[{i}] missing or empty code")
    return errors
