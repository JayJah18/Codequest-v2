"""
Export illustrative examples for dissertation / demo (JSON).

Uses human_marks.csv, marking_results.csv, fixed_tasks, optional review files.

Run: python -m prototype_llm_eval.evaluation.export_example_cases
Output: evaluation/results/example_cases.json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _norm_mark(s: str) -> bool:
    t = str(s).strip().lower()
    return t in {"correct", "1", "true", "yes"}


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    results = base / "evaluation" / "results"
    human_path = results / "human_marks.csv"
    marking_path = results / "marking_results.csv"
    fixed_path = base / "data" / "fixed_tasks_with_answers.json"
    q_review = results / "question_generation_review.csv"
    fb_json = results / "feedback_results.json"
    fb_review = results / "feedback_review.csv"

    out: dict[str, Any] = {"notes": "Examples for screenshots and thesis discussion; labels heuristic where noted."}

    tasks = json.loads(fixed_path.read_text(encoding="utf-8"))
    by_id = {str(t["task_id"]): t for t in tasks if isinstance(t, dict)}

    # Human + LLM per (task, answer, subtask, model) from human_marks (one llm column per row)
    examples_marking: dict[str, Any] = {}
    if human_path.exists() and marking_path.exists():
        humans: list[dict[str, str]] = list(csv.DictReader(human_path.open("r", encoding="utf-8", newline="")))

        def find_tp_fp_fn(model: str) -> tuple[dict[str, str] | None, dict[str, str] | None, dict[str, str] | None]:
            tp = fp = fn = None
            for h in humans:
                if not str(h.get("human_mark", "")).strip():
                    continue
                if str(h.get("llm_marker_model", "")).strip() != model:
                    continue
                hum = _norm_mark(h["human_mark"])
                llm = _norm_mark(h.get("llm_mark_for_subtask", ""))
                if llm and hum and tp is None:
                    tp = dict(h)
                if llm and not hum and fp is None:
                    fp = dict(h)
                if not llm and hum and fn is None:
                    fn = dict(h)
            return tp, fp, fn

        for model in ("mistral", "gemini", "llama"):
            tp, fp, fn = find_tp_fp_fn(model)
            if tp or fp or fn:
                examples_marking[model] = {
                    "agreement_true_positive_subtask": tp,
                    "false_positive_llm_correct_human_incorrect": fp,
                    "false_negative_llm_incorrect_human_correct": fn,
                }
                break
        if not examples_marking:
            h0 = next((h for h in humans if str(h.get("human_mark", "")).strip()), None)
            examples_marking["sample_human_row"] = h0

        out["marking_examples"] = examples_marking

    # Question review
    out["question_examples"] = {}
    if q_review.exists():
        rows = list(csv.DictReader(q_review.open("r", encoding="utf-8-sig", newline="")))
        appr = next((r for r in rows if str(r.get("human_question_label", "")).strip().lower() == "appropriate"), None)
        inap = next((r for r in rows if str(r.get("human_question_label", "")).strip().lower() == "inappropriate"), None)
        if appr:
            tid = appr.get("task_id", "")
            out["question_examples"]["appropriate_labeled"] = {"review_row": appr, "task": by_id.get(str(tid), {})}
        if inap:
            tid = inap.get("task_id", "")
            out["question_examples"]["inappropriate_labeled"] = {"review_row": inap, "task": by_id.get(str(tid), {})}
    if not out["question_examples"]:
        t0 = tasks[0] if tasks else {}
        out["question_examples"]["default_first_task"] = {
            "task_id": t0.get("task_id"),
            "question_text": t0.get("question_text"),
            "note": "Fill question_generation_review.csv and re-run to export labeled examples.",
        }

    out["feedback_examples"] = {}
    if fb_json.exists():
        fb = json.loads(fb_json.read_text(encoding="utf-8"))
        if isinstance(fb, list) and fb:
            useful = next(
                (
                    x
                    for x in fb
                    if isinstance(x, dict)
                    and len(str(x.get("feedback_text", "")).strip()) > 80
                    and "FEEDBACK_ERROR" not in str(x.get("feedback_text", ""))
                ),
                fb[0],
            )
            weak = next(
                (
                    x
                    for x in fb
                    if isinstance(x, dict)
                    and (
                        "FEEDBACK_ERROR" in str(x.get("feedback_text", ""))
                        or len(str(x.get("feedback_text", "")).strip()) < 40
                    )
                ),
                None,
            )
            out["feedback_examples"]["useful_sample"] = useful
            out["feedback_examples"]["weak_or_error_sample"] = weak
    if fb_review.exists():
        rows = list(csv.DictReader(fb_review.open("r", encoding="utf-8-sig", newline="")))
        good = next((r for r in rows if str(r.get("overall_feedback_label", "")).strip().lower() == "good"), None)
        poor = next((r for r in rows if str(r.get("overall_feedback_label", "")).strip().lower() == "poor"), None)
        if good:
            out["feedback_examples"]["human_rated_good"] = good
        if poor:
            out["feedback_examples"]["human_rated_poor"] = poor

    out_path = results / "example_cases.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
