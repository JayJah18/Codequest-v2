from __future__ import annotations

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
from prototype_llm_eval.evaluation.io_helpers import save_marking_results_csv
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

    answers_by_task = load_generated_answers_by_task(data_dir)
    align_errors = validate_generated_answers_align(tasks, answers_by_task)
    if align_errors:
        raise ValueError("generated_answers.json alignment failed:\n" + "\n".join(f"  - {e}" for e in align_errors))

    template = _load_prompt("marking_prompt.txt")
    prompt_version = _prompt_version(template, "PROMPT_VERSION:marking_unknown")
    marking_models = [m.strip() for m in os.getenv("MARKING_MODELS", "gemini").split(",") if m.strip()]
    run_timestamp = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, Any]] = []
    human_template_rows: list[dict[str, Any]] = []
    for marker_model in marking_models:
        actual_model_name = get_configured_model_name(marker_model)
        for task in tasks:
            task_answers = answers_by_task.get(task["task_id"], [])
            for answer in task_answers:
                prompt = template.format(
                    question_text=task["question_text"],
                    subtasks=task["subtasks"],
                    model_answer=task["model_answer"],
                    student_answer=answer["code"],
                )
                result: dict[str, Any]
                model_error = ""
                try:
                    result = generate_json(prompt, provider_name=marker_model)
                except Exception as exc:
                    # Continue other rows/models even if one generation fails.
                    model_error = str(exc)
                    result = {
                        "subtask_results": [],
                        "overall_score": 0,
                        "max_score": 5,
                        "star_rating": 0,
                        "reasoning": f"MARKING_ERROR: {model_error}",
                    }
                rows.append(
                    {
                        "task_id": task["task_id"],
                        "concept": task["concept"],
                        "answer_id": answer["answer_id"],
                        "variant_type": answer["variant_type"],
                        "marker_model": marker_model,
                        "subtask_results_json": json.dumps(result.get("subtask_results", [])),
                        "overall_score": result.get("overall_score", 0),
                        "max_score": result.get("max_score", 5),
                        "star_rating": result.get("star_rating", 0),
                        "reasoning": result.get("reasoning", ""),
                        "run_timestamp": run_timestamp,
                        "actual_model_name": actual_model_name,
                        "marking_prompt_version": prompt_version,
                    }
                )
                if model_error:
                    print(f"MARK {marker_model}: ERROR {task['task_id']} / {answer['answer_id']}: {model_error}")
                else:
                    # Avoid leading "[name]" — PowerShell treats it as a cast if this line is pasted into the shell.
                    print(f"MARK {marker_model}: Marked {task['task_id']} / {answer['answer_id']}")

                if marker_model == marking_models[0]:
                    subtask_results = result.get("subtask_results", [])
                    subtask_map: dict[str, Any] = {}
                    if isinstance(subtask_results, list):
                        for item in subtask_results:
                            if isinstance(item, dict):
                                sid = str(item.get("subtask_id", "")).strip()
                                if sid:
                                    subtask_map[sid] = item
                    for st in task["subtasks"]:
                        sid = st["subtask_id"]
                        llm_item = subtask_map.get(sid, {})
                        llm_mark = ""
                        if isinstance(llm_item, dict) and "correct" in llm_item:
                            llm_mark = "correct" if bool(llm_item.get("correct")) else "incorrect"
                        human_template_rows.append(
                            {
                                "task_id": task["task_id"],
                                "concept": task["concept"],
                                "answer_id": answer["answer_id"],
                                "variant_type": answer["variant_type"],
                                "subtask_id": sid,
                                "subtask_label": st["label"],
                                "student_answer_code": answer.get("code", ""),
                                "llm_marker_model": marker_model,
                                "llm_mark_for_subtask": llm_mark,
                                "human_mark": "",
                                "notes": "",
                            }
                        )

    marking_csv = results_dir / "marking_results.csv"
    human_csv = results_dir / "human_marks_template.csv"
    save_marking_results_csv(rows, marking_csv)
    save_marking_results_csv(human_template_rows, human_csv)

    answer_eval_count = sum(len(answers_by_task.get(t["task_id"], [])) for t in tasks)
    print()
    print("Marking run summary")
    print("-" * 40)
    print(f"Tasks in this run: {len(tasks)} ({', '.join(str(t['task_id']) for t in tasks)})")
    print("Pilot filter:", json.dumps(pilot_meta, separators=(",", ":")))
    print(f"Unique task plus answer attempts: {answer_eval_count}")
    print(f"Marking models: {', '.join(marking_models)}")
    print(f"Marking rows written: {len(rows)}")
    print(f"Human template rows (subtasks): {len(human_template_rows)}")
    print(f"Saved: {marking_csv}")
    print(f"Saved: {human_csv}")
    print()
    print("Next steps — do not paste these lines into PowerShell; run only the python commands above if needed.")
    print("  1. Copy human_marks_template.csv to human_marks.csv in the same folder.")
    print("  2. Fill human_mark (correct/incorrect or 1/0) and optional notes per row.")
    print("  3. Run: python -m prototype_llm_eval.evaluation.compare_results")
    print("  4. Optional: python -m prototype_llm_eval.evaluation.validate_pilot_outputs")
    print()


if __name__ == "__main__":
    main()
