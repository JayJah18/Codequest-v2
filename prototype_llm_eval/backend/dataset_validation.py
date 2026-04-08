from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPECTED_TASK_COUNT = 20
SUBTASKS_PER_TASK = 5
EXPECTED_TOTAL_SUBTASKS = EXPECTED_TASK_COUNT * SUBTASKS_PER_TASK

REQUIRED_CONCEPT_COUNTS: dict[str, int] = {
    "variables": 5,
    "conditionals": 5,
    "loops": 5,
    "functions": 5,
}

REQUIRED_TASK_KEYS = frozenset(
    {"task_id", "concept", "difficulty", "question_text", "subtasks", "model_answer"}
)


def _validate_subtask_object(subtask: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(subtask, dict):
        return [f"{label}: each subtask must be an object with subtask_id and label"]
    subtask_id = subtask.get("subtask_id")
    text_label = subtask.get("label")
    if not isinstance(subtask_id, str) or not subtask_id.strip():
        errors.append(f"{label}: subtask_id must be a non-empty string")
    if not isinstance(text_label, str) or not text_label.strip():
        errors.append(f"{label}: label must be a non-empty string")
    return errors


def validate_task_schema(
    task: dict[str, Any],
    *,
    label: str,
    require_model_answer: bool = True,
) -> list[str]:
    errors: list[str] = []
    required_keys = {"task_id", "concept", "difficulty", "question_text", "subtasks"}
    if require_model_answer:
        required_keys = REQUIRED_TASK_KEYS
    missing = required_keys - set(task.keys())
    if missing:
        errors.append(f"{label}: missing keys: {sorted(missing)}")

    if not isinstance(task.get("task_id"), str) or not str(task["task_id"]).strip():
        errors.append(f"{label}: task_id must be a non-empty string")
    if not isinstance(task.get("concept"), str) or not str(task["concept"]).strip():
        errors.append(f"{label}: concept must be a non-empty string")
    if not isinstance(task.get("difficulty"), str) or not str(task["difficulty"]).strip():
        errors.append(f"{label}: difficulty must be a non-empty string")
    if not isinstance(task.get("question_text"), str) or not str(task["question_text"]).strip():
        errors.append(f"{label}: question_text must be a non-empty string")

    subtasks = task.get("subtasks")
    if not isinstance(subtasks, list):
        errors.append(f"{label}: subtasks must be a list")
    else:
        if len(subtasks) != SUBTASKS_PER_TASK:
            errors.append(
                f"{label}: subtasks must have exactly {SUBTASKS_PER_TASK} items, got {len(subtasks)}"
            )
        seen_subtask_ids: set[str] = set()
        for i, st in enumerate(subtasks, start=1):
            errors.extend(_validate_subtask_object(st, f"{label}: subtasks[{i}]"))
            if isinstance(st, dict):
                sid = st.get("subtask_id")
                if isinstance(sid, str) and sid.strip():
                    if sid in seen_subtask_ids:
                        errors.append(f"{label}: duplicate subtask_id {sid!r}")
                    seen_subtask_ids.add(sid)

    if require_model_answer:
        ma = task.get("model_answer")
        if not isinstance(ma, str) or not ma.strip():
            errors.append(f"{label}: model_answer must be a non-empty string")

    return errors


def validate_concept_counts(tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    counts: dict[str, int] = {c: 0 for c in REQUIRED_CONCEPT_COUNTS}
    for i, task in enumerate(tasks):
        c = task.get("concept")
        if not isinstance(c, str) or c not in REQUIRED_CONCEPT_COUNTS:
            errors.append(
                f"task[{i}]: concept must be one of {sorted(REQUIRED_CONCEPT_COUNTS)}, got {c!r}"
            )
            continue
        counts[c] += 1
    for concept, need in REQUIRED_CONCEPT_COUNTS.items():
        got = counts[concept]
        if got != need:
            errors.append(f"Concept {concept!r}: expected {need} tasks, got {got}")
    return errors


def validate_subtask_counts(tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    total = 0
    for task in tasks:
        st = task.get("subtasks")
        if isinstance(st, list):
            total += len(st)
    if len(tasks) != EXPECTED_TASK_COUNT:
        errors.append(f"Expected {EXPECTED_TASK_COUNT} tasks, got {len(tasks)}")
    if total != EXPECTED_TOTAL_SUBTASKS:
        errors.append(
            f"Expected {EXPECTED_TOTAL_SUBTASKS} subtasks total (20 tasks x 5), got {total}"
        )
    return errors


def validate_dataset_completeness(tasks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if len(tasks) != EXPECTED_TASK_COUNT:
        errors.append(f"Dataset must contain exactly {EXPECTED_TASK_COUNT} tasks, got {len(tasks)}")

    seen_ids: set[str] = set()
    for i, task in enumerate(tasks):
        label = f"task[{i}] ({task.get('task_id', '?')})"
        errors.extend(validate_task_schema(task, label=label, require_model_answer=True))
        tid = task.get("task_id")
        if isinstance(tid, str) and tid.strip():
            if tid in seen_ids:
                errors.append(f"Duplicate task_id: {tid!r}")
            seen_ids.add(tid)

    errors.extend(validate_concept_counts(tasks))
    errors.extend(validate_subtask_counts(tasks))
    return errors


def assert_valid_dataset(tasks: list[dict[str, Any]]) -> None:
    errors = validate_dataset_completeness(tasks)
    if errors:
        raise ValueError("Dataset validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


def load_json_task_list(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path}: root must be a JSON array")
    return data


def load_fixed_tasks_with_answers_validated(path: Path) -> list[dict[str, Any]]:
    """
    Load fixed_tasks_with_answers.json and validate. Used by the server in fixed mode.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Missing dataset file: {path}\n"
            "Prepare it first with:\n"
            "  python -m prototype_llm_eval.backend.prepare_fixed_dataset"
        )
    tasks = load_json_task_list(path)
    assert_valid_dataset(tasks)
    return tasks
