"""
Structural checks for live Gemini-generated tasks (demo / supervisor evidence).

Does not replace task_bank._validate_task_quality; adds schema-level checks
that are easy to report in API JSON.
"""

from __future__ import annotations

from typing import Any

from .dataset_validation import validate_task_schema


def validate_live_task_structure(task: dict[str, Any], *, label: str = "live_task") -> dict[str, Any]:
    """
    Returns {ok: bool, checks: [{id, passed, detail}], schema_errors: [str]}.
    """
    checks: list[dict[str, Any]] = []

    st = task.get("subtasks")
    n = len(st) if isinstance(st, list) else 0
    ok_count = n == 5
    checks.append({"id": "subtask_count", "passed": ok_count, "detail": f"expected 5, got {n}"})

    labels_ok = True
    if isinstance(st, list):
        for i, item in enumerate(st, start=1):
            if not isinstance(item, dict):
                labels_ok = False
                break
            lab = str(item.get("label", "")).strip()
            if len(lab) < 1:
                labels_ok = False
                break
    else:
        labels_ok = False
    checks.append({"id": "non_empty_subtask_labels", "passed": labels_ok, "detail": "each subtask needs a label"})

    qt = str(task.get("question_text", "")).strip()
    checks.append({"id": "question_text", "passed": len(qt) >= 8, "detail": f"length {len(qt)}"})

    tid = str(task.get("task_id", "")).strip()
    checks.append({"id": "task_id", "passed": bool(tid), "detail": tid or "(missing)"})

    concept = str(task.get("concept", "")).strip()
    checks.append({"id": "concept", "passed": bool(concept), "detail": concept or "(missing)"})

    schema_errors = validate_task_schema(task, label=label, require_model_answer=True)
    schema_ok = len(schema_errors) == 0
    checks.append({"id": "dataset_schema", "passed": schema_ok, "detail": "; ".join(schema_errors[:3]) or "ok"})

    ok = ok_count and labels_ok and len(qt) >= 8 and bool(tid) and bool(concept) and schema_ok
    return {"ok": ok, "checks": checks, "schema_errors": schema_errors}
