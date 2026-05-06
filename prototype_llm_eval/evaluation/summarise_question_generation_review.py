"""
Summarise question_generation_review.csv after human labels are filled.

Run: python -m prototype_llm_eval.evaluation.summarise_question_generation_review
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    path = base / "evaluation" / "results" / "question_generation_review.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run generate_question_review_sheet first.")

    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    labels = [str(r.get("human_question_label", "")).strip().lower() for r in rows]
    filled = [lb for lb in labels if lb]
    appr = sum(1 for lb in filled if lb == "appropriate")
    inap = sum(1 for lb in filled if lb == "inappropriate")
    other = len(filled) - appr - inap

    by_concept: Counter[str] = Counter()
    by_concept_appr: Counter[str] = Counter()
    by_concept_inap: Counter[str] = Counter()
    for r in rows:
        lb = str(r.get("human_question_label", "")).strip().lower()
        c = str(r.get("concept", "")).strip() or "unknown"
        if lb:
            by_concept[c] += 1
            if lb == "appropriate":
                by_concept_appr[c] += 1
            elif lb == "inappropriate":
                by_concept_inap[c] += 1

    print("=== Question generation review summary ===")
    print(f"Total tasks in sheet: {len(rows)}")
    print(f"Reviewed (label filled): {len(filled)}")
    print(f"  appropriate:   {appr}")
    print(f"  inappropriate: {inap}")
    if other:
        print(f"  other labels:  {other}")
    if filled:
        print(f"Proportion appropriate (of reviewed): {appr / len(filled):.3f}")
    print("Per-concept reviewed / appropriate / inappropriate:")
    for c in sorted(by_concept):
        n = by_concept[c]
        a = by_concept_appr[c]
        i = by_concept_inap[c]
        print(f"  {c}: appropriate {a}/{n}, inappropriate {i}/{n}")


if __name__ == "__main__":
    main()
