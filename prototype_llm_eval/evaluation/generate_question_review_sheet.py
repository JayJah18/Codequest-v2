"""
Emit a CSV template for human review of fixed benchmark task appropriateness.

Human judgement is against the intended learner level / topic — not string-match
against another "gold" question set.

Run: python -m prototype_llm_eval.evaluation.generate_question_review_sheet
Output: evaluation/results/question_generation_review.csv
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.dataset_validation import assert_valid_dataset, load_json_task_list


def _subtask_summary(subtasks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for st in subtasks:
        if isinstance(st, dict):
            sid = str(st.get("subtask_id", "")).strip()
            lab = str(st.get("label", "")).strip()
            parts.append(f"{sid}: {lab}" if sid else lab)
    return " | ".join(parts)


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    data_path = base / "data" / "fixed_tasks_with_answers.json"
    out_path = base / "evaluation" / "results" / "question_generation_review.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tasks = load_json_task_list(data_path)
    assert_valid_dataset(tasks)

    fieldnames = [
        "task_id",
        "concept",
        "difficulty",
        "question_text",
        "subtasks_summary",
        "human_question_label",
        "notes",
        "level_fit",
        "topic_fit",
        "clarity",
        "subtasks_json",
        "model_answer_present",
    ]
    rows: list[dict[str, str]] = []
    for t in tasks:
        subtasks = t.get("subtasks") if isinstance(t.get("subtasks"), list) else []
        ma = t.get("model_answer")
        present = "yes" if isinstance(ma, str) and ma.strip() else "no"
        rows.append(
            {
                "task_id": str(t.get("task_id", "")),
                "concept": str(t.get("concept", "")),
                "difficulty": str(t.get("difficulty", "")),
                "question_text": str(t.get("question_text", "")),
                "subtasks_summary": _subtask_summary(subtasks),
                "subtasks_json": json.dumps(subtasks, ensure_ascii=False),
                "model_answer_present": present,
                "level_fit": "",
                "topic_fit": "",
                "clarity": "",
                "human_question_label": "",
                "notes": "",
            }
        )

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")
    print("Fill human_question_label with: appropriate | inappropriate")
    print("Optional: level_fit, topic_fit, clarity (e.g. 1-3 or short text)")


if __name__ == "__main__":
    main()
