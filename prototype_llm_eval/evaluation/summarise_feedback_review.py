"""
Summarise feedback_review.csv by feedback_model.

Run: python -m prototype_llm_eval.evaluation.summarise_feedback_review
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def _avg(nums: list[float]) -> float:
    return sum(nums) / len(nums) if nums else 0.0


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    path = base / "evaluation" / "results" / "feedback_review.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run generate_feedback_review_sheet after feedback eval.")

    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    by_model: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        m = str(r.get("feedback_model", "")).strip() or "unknown"
        by_model[m].append(r)

    print("=== Feedback human review summary ===")
    for model in sorted(by_model):
        rs = by_model[model]
        rel: list[float] = []
        clar: list[float] = []
        usef: list[float] = []
        for r in rs:
            for col, acc in (
                ("relevance_score", rel),
                ("clarity_score", clar),
                ("usefulness_score", usef),
            ):
                t = str(r.get(col, "")).strip()
                if t.isdigit():
                    acc.append(float(int(t)))
        labels = [str(r.get("overall_feedback_label", "")).strip().lower() for r in rs if str(r.get("overall_feedback_label", "")).strip()]
        cnt_poor = sum(1 for x in labels if x == "poor")
        cnt_acc = sum(1 for x in labels if x == "acceptable")
        cnt_good = sum(1 for x in labels if x == "good")

        print(f"\n{model} (rows={len(rs)})")
        print(f"  Avg relevance (filled 1-3):   {_avg(rel):.2f}  (n={len(rel)})")
        print(f"  Avg clarity (filled 1-3):     {_avg(clar):.2f}  (n={len(clar)})")
        print(f"  Avg usefulness (filled 1-3):  {_avg(usef):.2f}  (n={len(usef)})")
        print(f"  Overall labels — poor: {cnt_poor}, acceptable: {cnt_acc}, good: {cnt_good} (labeled n={len(labels)})")


if __name__ == "__main__":
    main()
