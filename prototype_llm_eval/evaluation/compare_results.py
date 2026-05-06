from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


def _to_bool_mark(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "correct", "yes", "y"}


def _print_confusion_matrix(marker_model: str, tp: int, tn: int, fp: int, fn: int) -> None:
    """
    Binary subtask marking: positive class = 'correct'.
    Rows = human (reference), columns = LLM (predictor).
    """
    print(f"Confusion matrix - {marker_model} (subtask level, positive class = correct)")
    print("  Rows: human ground truth. Columns: LLM prediction.")
    h_inc_llm_inc = tn
    h_inc_llm_cor = fp
    h_cor_llm_inc = fn
    h_cor_llm_cor = tp
    col_w = max(len(str(v)) for v in (h_inc_llm_inc, h_inc_llm_cor, h_cor_llm_inc, h_cor_llm_cor, "LLM incorrect", "LLM correct")) + 2
    col_w = max(col_w, 18)
    row_label_w = 22

    def cell(n: int) -> str:
        return str(n).rjust(col_w)

    sep = "-" * (row_label_w + 1 + col_w + 3 + col_w)
    print(sep)
    print(f"{'':{row_label_w}s} {'LLM incorrect':>{col_w}s} | {'LLM correct':>{col_w}s}")
    print(sep)
    print(f"{'Human incorrect':<{row_label_w}s} {cell(h_inc_llm_inc)} | {cell(h_inc_llm_cor)}  (TN | FP)")
    print(f"{'Human correct':<{row_label_w}s} {cell(h_cor_llm_inc)} | {cell(h_cor_llm_cor)}  (FN | TP)")
    print(sep)
    total = tp + tn + fp + fn
    if total:
        print("Row % (human marginal, for interpretation):")
        r0 = h_inc_llm_inc + h_inc_llm_cor
        r1 = h_cor_llm_inc + h_cor_llm_cor
        if r0:
            print(
                f"  P(LLM pred | human incorrect): incorrect {100 * h_inc_llm_inc / r0:.1f}%, "
                f"correct {100 * h_inc_llm_cor / r0:.1f}%"
            )
        if r1:
            print(
                f"  P(LLM pred | human correct):   incorrect {100 * h_cor_llm_inc / r1:.1f}%, "
                f"correct {100 * h_cor_llm_cor / r1:.1f}%"
            )


def main() -> None:
    results_dir = Path(__file__).resolve().parent / "results"
    llm_path = results_dir / "marking_results.csv"
    human_path = results_dir / "human_marks.csv"

    if not llm_path.exists():
        raise FileNotFoundError(f"Missing {llm_path}")
    if not human_path.exists():
        raise FileNotFoundError(
            f"Missing {human_path}. Copy human_marks_template.csv to human_marks.csv and fill marks first."
        )

    llm_marks_by_model: dict[str, dict[tuple[str, str, str], bool]] = {}
    llm_meta_by_model: dict[str, dict[tuple[str, str, str], str]] = {}
    llm_variant_by_model: dict[str, dict[tuple[str, str, str], str]] = {}
    with llm_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            marker_model = row.get("marker_model", "unknown").strip() or "unknown"
            llm_marks_by_model.setdefault(marker_model, {})
            llm_meta_by_model.setdefault(marker_model, {})
            llm_variant_by_model.setdefault(marker_model, {})
            marks = json.loads(row.get("subtask_results_json") or row.get("subtask_results", "[]"))
            for mark in marks:
                key = (row["task_id"], row["answer_id"], str(mark.get("subtask_id")))
                llm_marks_by_model[marker_model][key] = bool(mark.get("correct", False))
                llm_meta_by_model[marker_model][key] = row["concept"]
                llm_variant_by_model[marker_model][key] = row.get("variant_type", "unknown")

    human_marks: dict[tuple[str, str, str], bool] = {}
    with human_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if not str(row.get("human_mark", "")).strip():
                continue
            key = (row["task_id"], row["answer_id"], str(row["subtask_id"]))
            human_marks[key] = _to_bool_mark(row["human_mark"])

    summary_rows: list[dict[str, Any]] = []
    confusion_rows: list[dict[str, Any]] = []
    for marker_model, llm_marks in sorted(llm_marks_by_model.items()):
        common_keys = sorted(set(llm_marks).intersection(human_marks))
        if not common_keys:
            print(f"WARN {marker_model}: No overlapping rows with human marks.")
            continue

        tp = tn = fp = fn = 0
        matches = 0
        for key in common_keys:
            llm = llm_marks[key]
            human = human_marks[key]
            if llm == human:
                matches += 1
            if llm and human:
                tp += 1
            elif not llm and not human:
                tn += 1
            elif llm and not human:
                fp += 1
            else:
                fn += 1

        total = len(common_keys)
        accuracy = (tp + tn) / total
        agreement_rate = matches / total
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        print(f"\nComparison results - {marker_model}")
        print("------------------------------")
        print(f"Total compared subtasks: {total}")
        print(f"Accuracy: {accuracy:.3f}")
        print(f"Agreement rate: {agreement_rate:.3f}")
        print(f"Precision: {precision:.3f}")
        print(f"Recall:    {recall:.3f}")
        print(f"F1 score:  {f1:.3f}")
        print(f"Counts - TP: {tp}  TN: {tn}  FP: {fp}  FN: {fn}")
        _print_confusion_matrix(marker_model, tp, tn, fp, fn)

        per_concept: dict[str, list[bool]] = {}
        meta = llm_meta_by_model.get(marker_model, {})
        for key in common_keys:
            concept = meta.get(key, "unknown")
            per_concept.setdefault(concept, []).append(llm_marks[key] == human_marks[key])
        print("Per-concept accuracy:")
        for concept, values in sorted(per_concept.items()):
            score = sum(values) / len(values) if values else 0.0
            print(f"  {concept}: {score:.3f} ({sum(values)}/{len(values)})")

        per_variant: dict[str, list[bool]] = {}
        variant_meta = llm_variant_by_model.get(marker_model, {})
        for key in common_keys:
            variant = variant_meta.get(key, "unknown")
            per_variant.setdefault(variant, []).append(llm_marks[key] == human_marks[key])
        print("Per-variant accuracy:")
        for variant, values in sorted(per_variant.items()):
            score = sum(values) / len(values) if values else 0.0
            print(f"  {variant}: {score:.3f} ({sum(values)}/{len(values)})")

        summary_rows.append(
            {
                "marker_model": marker_model,
                "total": total,
                "accuracy": f"{accuracy:.6f}",
                "agreement_rate": f"{agreement_rate:.6f}",
                "tp": tp,
                "tn": tn,
                "fp": fp,
                "fn": fn,
                "precision": f"{precision:.6f}",
                "recall": f"{recall:.6f}",
                "f1": f"{f1:.6f}",
            }
        )
        confusion_rows.append(
            {
                "marker_model": marker_model,
                "total_compared": total,
                "tp_human_correct_llm_correct": tp,
                "tn_human_incorrect_llm_incorrect": tn,
                "fp_human_incorrect_llm_correct": fp,
                "fn_human_correct_llm_incorrect": fn,
            }
        )

    if os.getenv("SAVE_COMPARISON_SUMMARY", "true").lower() == "true" and summary_rows:
        summary_path = results_dir / "comparison_summary.csv"
        with summary_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"\nSaved summary: {summary_path}")

    if os.getenv("SAVE_CONFUSION_MATRIX", "true").lower() == "true" and confusion_rows:
        cm_path = results_dir / "confusion_matrix.csv"
        with cm_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(confusion_rows[0].keys()))
            writer.writeheader()
            writer.writerows(confusion_rows)
        print(f"Saved confusion matrix: {cm_path}")


if __name__ == "__main__":
    main()
