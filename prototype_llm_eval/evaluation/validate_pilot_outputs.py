from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.dataset_validation import load_json_task_list, validate_task_subset_for_evaluation
from prototype_llm_eval.evaluation.pilot_filters import (
    apply_pilot_task_filter,
    load_generated_answers_by_task,
    validate_generated_answers_align,
)


REQUIRED_MARKING_COLS = frozenset(
    {
        "task_id",
        "concept",
        "answer_id",
        "variant_type",
        "marker_model",
        "subtask_results_json",
        "overall_score",
        "max_score",
        "star_rating",
        "reasoning",
        "run_timestamp",
        "actual_model_name",
        "marking_prompt_version",
    }
)


def _load_filtered_tasks(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "fixed_tasks_with_answers.json"
    tasks = load_json_task_list(path)
    filtered, _meta = apply_pilot_task_filter(tasks)
    subset_errors = validate_task_subset_for_evaluation(filtered)
    if subset_errors:
        raise ValueError("Task subset validation failed:\n" + "\n".join(f"  - {e}" for e in subset_errors))
    answers_by_task = load_generated_answers_by_task(data_dir)
    align_errors = validate_generated_answers_align(filtered, answers_by_task)
    if align_errors:
        raise ValueError("Answer alignment failed:\n" + "\n".join(f"  - {e}" for e in align_errors))
    return filtered


def main() -> int:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    results_dir = base_dir / "evaluation" / "results"
    marking_path = results_dir / "marking_results.csv"

    if not marking_path.exists():
        print(f"ERROR: Missing {marking_path}", file=sys.stderr)
        return 1

    marking_models = [m.strip() for m in os.getenv("MARKING_MODELS", "gemini").split(",") if m.strip()]

    try:
        tasks = _load_filtered_tasks(data_dir)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    answers_by_task = load_generated_answers_by_task(data_dir)
    expected_pairs: list[tuple[str, str]] = []
    for task in tasks:
        tid = str(task["task_id"])
        for ans in answers_by_task.get(tid, []):
            expected_pairs.append((tid, str(ans["answer_id"])))

    expected_keys = {(tid, aid, m) for tid, aid in expected_pairs for m in marking_models}

    rows: list[dict[str, str]] = []
    with marking_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    errors: list[str] = []
    if not rows:
        errors.append("marking_results.csv is empty")

    relevant_rows: list[dict[str, str]] = []
    ignored_rows = 0
    for i, row in enumerate(rows, start=2):
        missing = REQUIRED_MARKING_COLS - set(row.keys())
        if missing:
            errors.append(f"Row {i}: missing columns {sorted(missing)}")
            continue
        key = (row["task_id"], row["answer_id"], row["marker_model"])
        if key not in expected_keys:
            ignored_rows += 1
            continue
        relevant_rows.append(row)

    task_map = {str(t["task_id"]): t for t in tasks}
    for i, row in enumerate(relevant_rows, start=2):
        key = (row["task_id"], row["answer_id"], row["marker_model"])

        try:
            sub = json.loads(row["subtask_results_json"] or "[]")
        except json.JSONDecodeError as exc:
            errors.append(f"Row {i}: invalid subtask_results_json ({exc})")
            continue

        if not isinstance(sub, list):
            errors.append(f"Row {i}: subtask_results_json must be a JSON array")
            continue

        t = task_map.get(row["task_id"])
        if t:
            want_ids = {str(st["subtask_id"]) for st in t["subtasks"]}
            got_ids = {str(x.get("subtask_id")) for x in sub if isinstance(x, dict)}
            if len(sub) != 5 or len(want_ids) != 5:
                errors.append(f"Row {i}: expected 5 subtask results, got {len(sub)}")
            elif got_ids != want_ids:
                errors.append(f"Row {i}: subtask_id mismatch (expected {sorted(want_ids)}, got {sorted(got_ids)})")

        for field in ("overall_score", "max_score", "star_rating"):
            val = str(row.get(field, "")).strip()
            if val == "":
                errors.append(f"Row {i}: empty {field}")
            else:
                try:
                    int(float(val))
                except ValueError:
                    errors.append(f"Row {i}: {field} must be numeric, got {val!r}")

    seen_keys: set[tuple[str, str, str]] = set()
    for i, row in enumerate(relevant_rows, start=2):
        key = (row.get("task_id", ""), row.get("answer_id", ""), row.get("marker_model", ""))
        if key in seen_keys:
            errors.append(f"Row {i}: duplicate (task_id, answer_id, marker_model)")
        seen_keys.add(key)

    for key in sorted(expected_keys):
        if key not in seen_keys:
            errors.append(f"Missing row for {key}")

    if errors:
        print("Pilot output validation FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("Pilot output validation OK")
    print(f"  Tasks in filter: {len(tasks)}")
    print(f"  Expected marking rows: {len(expected_keys)}")
    print(f"  Actual relevant rows: {len(relevant_rows)}")
    print(f"  Ignored non-pilot rows: {ignored_rows}")
    print(f"  File checked: {marking_path}")
    print("Next: copy human_marks_template.csv to human_marks.csv, fill marks, run compare_results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
