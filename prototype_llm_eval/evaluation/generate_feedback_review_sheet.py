"""
Build feedback_review.csv for human scoring of feedback quality.

Reads evaluation/results/feedback_results.json (run run_feedback_eval first).
Run: python -m prototype_llm_eval.evaluation.generate_feedback_review_sheet
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    json_path = base / "evaluation" / "results" / "feedback_results.json"
    csv_src = base / "evaluation" / "results" / "feedback_results.csv"
    out = base / "evaluation" / "results" / "feedback_review.csv"
    raw: list[Any]
    if json_path.exists():
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{json_path}: expected JSON array")
    elif csv_src.exists():
        with csv_src.open("r", encoding="utf-8", newline="") as f:
            raw = list(csv.DictReader(f))
    else:
        raise FileNotFoundError(
            f"Missing {json_path} and {csv_src}. Run: python -m prototype_llm_eval.evaluation.run_feedback_eval"
        )

    fieldnames = [
        "task_id",
        "concept",
        "answer_id",
        "variant_type",
        "feedback_model",
        "feedback_text",
        "relevance_score",
        "clarity_score",
        "usefulness_score",
        "overall_feedback_label",
        "notes",
    ]
    rows: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "task_id": str(item.get("task_id", "")),
                "concept": str(item.get("concept", "")),
                "answer_id": str(item.get("answer_id", "")),
                "variant_type": str(item.get("variant_type", "")),
                "feedback_model": str(item.get("feedback_model", "")),
                "feedback_text": str(item.get("feedback_text", "")),
                "relevance_score": "",
                "clarity_score": "",
                "usefulness_score": "",
                "overall_feedback_label": "",
                "notes": "",
            }
        )

    err_n = sum(
        1
        for r in rows
        if str(r.get("feedback_text", "")).strip().upper().startswith("FEEDBACK_ERROR")
    )
    if err_n:
        print(
            f"WARNING: {err_n}/{len(rows)} rows contain FEEDBACK_ERROR in feedback_text. "
            "Re-run run_feedback_eval with API keys / local models loaded, then regenerate this sheet."
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out}")
    print("Score relevance/clarity/usefulness 1-3; overall_feedback_label: poor | acceptable | good")


if __name__ == "__main__":
    main()
