from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.dataset_validation import (
    assert_valid_dataset,
    load_json_task_list,
    validate_task_subset_for_evaluation,
)
from prototype_llm_eval.backend.llm_provider import generate_json, get_configured_model_name
from prototype_llm_eval.evaluation.io_helpers import save_generated_answers
from prototype_llm_eval.evaluation.pilot_filters import (
    apply_pilot_task_filter,
    load_generated_answers_by_task,
    validate_generated_answers_align,
)


def _load_prompt(name: str) -> str:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / name).read_text(encoding="utf-8")


def _prompt_version(prompt_text: str, fallback: str) -> str:
    first = prompt_text.splitlines()[0].strip() if prompt_text.strip() else ""
    return first if first.startswith("PROMPT_VERSION:") else fallback


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    results_dir = base_dir / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    feedback_models = [m.strip() for m in os.getenv("FEEDBACK_MODELS", "gemini").split(",") if m.strip()]

    fixed_path = data_dir / "fixed_tasks_with_answers.json"
    tasks_all = load_json_task_list(fixed_path)
    assert_valid_dataset(tasks_all)
    tasks, pilot_meta = apply_pilot_task_filter(tasks_all)
    if not tasks:
        raise ValueError(
            "Pilot filter produced zero tasks. Check TASK_IDS, CONCEPT_FILTER, and TASK_LIMIT."
        )
    subset_errors = validate_task_subset_for_evaluation(tasks)
    if subset_errors:
        raise ValueError("Pilot task subset failed validation:\n" + "\n".join(f"  - {e}" for e in subset_errors))

    # Default smaller feedback run: first N tasks after pilot filter (unless 0 = no cap).
    # If TASK_LIMIT is set, assume pilot already sized the run — do not apply the default cap.
    if os.getenv("TASK_LIMIT", "").strip():
        feedback_cap = 0
    else:
        limit_raw = os.getenv("FEEDBACK_EVAL_TASK_LIMIT", "4").strip()
        try:
            feedback_cap = int(limit_raw) if limit_raw else 4
        except ValueError as exc:
            raise ValueError(f"FEEDBACK_EVAL_TASK_LIMIT must be int or empty, got {limit_raw!r}") from exc
    if feedback_cap > 0 and len(tasks) > feedback_cap:
        tasks = tasks[:feedback_cap]

    answers_by_task = load_generated_answers_by_task(data_dir)
    align_errors = validate_generated_answers_align(tasks, answers_by_task)
    if align_errors:
        raise ValueError("generated_answers.json alignment failed:\n" + "\n".join(f"  - {e}" for e in align_errors))
    pilot_task_ids = {str(t["task_id"]) for t in tasks}
    marking_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    marking_path = results_dir / "marking_results.csv"
    if marking_path.exists():
        with marking_path.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if str(row.get("task_id", "")).strip() not in pilot_task_ids:
                    continue
                # use gemini row as baseline if present, else first seen
                key = (row["task_id"], row["answer_id"])
                if key not in marking_by_key or row.get("marker_model") == "gemini":
                    marking_by_key[key] = row

    prompt_template = _load_prompt("feedback_prompt.txt")
    feedback_prompt_version = _prompt_version(prompt_template, "PROMPT_VERSION:feedback_unknown")
    results: list[dict[str, Any]] = []
    for feedback_model in feedback_models:
        actual_model_name = get_configured_model_name(feedback_model)
        for task in tasks:
            concept = str(task.get("concept", ""))
            for answer in answers_by_task.get(task["task_id"], []):
                mark_row = marking_by_key.get((task["task_id"], answer["answer_id"]), {})
                raw_sub = mark_row.get("subtask_results_json") or mark_row.get("subtask_results", "[]")
                marking_result = {
                    "subtask_results": json.loads(raw_sub or "[]"),
                    "overall_score": int(float(mark_row.get("overall_score", 0) or 0)),
                    "max_score": int(float(mark_row.get("max_score", 5) or 5)),
                    "star_rating": int(float(mark_row.get("star_rating", 0) or 0)),
                    "reasoning": str(mark_row.get("reasoning", "")),
                }
                prompt = prompt_template.format(
                    question_text=task["question_text"],
                    subtasks=task["subtasks"],
                    model_answer=task["model_answer"],
                    student_answer=answer["code"],
                    marking_result=json.dumps(marking_result, ensure_ascii=False),
                )
                llm_result: dict[str, Any]
                run_timestamp = datetime.now(timezone.utc).isoformat()
                try:
                    llm_result = generate_json(prompt, provider_name=feedback_model)
                except Exception as exc:
                    llm_result = {"feedback": f"FEEDBACK_ERROR: {exc}"}
                variant_type = str(answer.get("variant_type", "") or "")
                results.append(
                    {
                        "task_id": task["task_id"],
                        "concept": concept,
                        "answer_id": answer["answer_id"],
                        "variant_type": variant_type,
                        "feedback_model": feedback_model,
                        "feedback_text": str(llm_result.get("feedback", "")).strip(),
                        "run_timestamp": run_timestamp,
                        "actual_model_name": actual_model_name,
                        "feedback_prompt_version": feedback_prompt_version,
                    }
                )
                print(f"MARK {feedback_model}: Feedback {task['task_id']} / {answer['answer_id']}")

    save_generated_answers(results, results_dir / "feedback_results.json")
    csv_path = results_dir / "feedback_results.csv"
    if results:
        fieldnames = [
            "task_id",
            "concept",
            "answer_id",
            "variant_type",
            "feedback_model",
            "feedback_text",
            "run_timestamp",
            "actual_model_name",
            "feedback_prompt_version",
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(results)
    else:
        if csv_path.exists():
            csv_path.unlink()

    print()
    print("=== Feedback run summary ===")
    print(f"pilot_filter: {pilot_meta}")
    cap_msg = "no extra cap (TASK_LIMIT set)" if os.getenv("TASK_LIMIT", "").strip() else f"cap={feedback_cap} (0=all after pilot)"
    print(f"FEEDBACK_EVAL_TASK_LIMIT: {cap_msg}")
    print(f"Tasks in this run: {len(tasks)}")
    print(f"Feedback models: {', '.join(feedback_models)}")
    print(f"Feedback rows written: {len(results)}")
    print(f"Saved: {results_dir / 'feedback_results.json'}")
    if results:
        print(f"Saved: {csv_path}")


if __name__ == "__main__":
    main()
