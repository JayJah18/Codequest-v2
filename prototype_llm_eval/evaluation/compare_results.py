from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _to_bool_mark(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "correct", "yes", "y"}


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

    llm_marks: dict[tuple[str, str, str], bool] = {}
    with llm_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            marks = json.loads(row.get("subtask_results", "[]"))
            for mark in marks:
                key = (row["task_id"], row["answer_id"], str(mark.get("subtask")))
                llm_marks[key] = str(mark.get("result", "")).strip().lower() == "correct"

    human_marks: dict[tuple[str, str, str], bool] = {}
    with human_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["task_id"], row["answer_id"], str(row["subtask_id"]))
            human_marks[key] = _to_bool_mark(row["human_mark"])

    common_keys = sorted(set(llm_marks).intersection(human_marks))
    if not common_keys:
        raise ValueError("No overlapping (task_id, answer_id, subtask_id) rows between LLM and human files.")

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

    print("Comparison Results")
    print("------------------")
    print(f"Total compared subtasks: {total}")
    print(f"Accuracy: {accuracy:.3f}")
    print(f"Agreement rate: {agreement_rate:.3f}")
    print("Confusion matrix counts:")
    print(f"TP: {tp}")
    print(f"TN: {tn}")
    print(f"FP: {fp}")
    print(f"FN: {fn}")


if __name__ == "__main__":
    main()
