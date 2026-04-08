from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.llm_provider import generate_json
from prototype_llm_eval.evaluation.io_helpers import save_generated_answers


def _load_prompt(name: str) -> str:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / name).read_text(encoding="utf-8")


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    results_dir = base_dir / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    feedback_models = [m.strip() for m in os.getenv("FEEDBACK_MODELS", "gemini").split(",") if m.strip()]
    max_tasks = int(os.getenv("FEEDBACK_EVAL_TASK_LIMIT", "5"))

    tasks = json.loads((data_dir / "fixed_tasks_with_answers.json").read_text(encoding="utf-8"))[:max_tasks]
    answers_by_task = {
        item["task_id"]: item["answers"]
        for item in json.loads((data_dir / "generated_answers.json").read_text(encoding="utf-8"))
    }
    marking_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    marking_path = results_dir / "marking_results.csv"
    if marking_path.exists():
        import csv

        with marking_path.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                # use gemini row as baseline if present, else first seen
                key = (row["task_id"], row["answer_id"])
                if key not in marking_by_key or row.get("marker_model") == "gemini":
                    marking_by_key[key] = row

    prompt_template = _load_prompt("feedback_prompt.txt")
    results: list[dict[str, Any]] = []
    for feedback_model in feedback_models:
        for task in tasks:
            for answer in answers_by_task.get(task["task_id"], []):
                mark_row = marking_by_key.get((task["task_id"], answer["answer_id"]), {})
                marking_result = {
                    "subtask_results": json.loads(mark_row.get("subtask_results_json", "[]")),
                    "overall_score": int(mark_row.get("overall_score", 0) or 0),
                    "max_score": int(mark_row.get("max_score", 5) or 5),
                    "star_rating": int(mark_row.get("star_rating", 0) or 0),
                    "reasoning": str(mark_row.get("reasoning", "")),
                }
                prompt = prompt_template.format(
                    question_text=task["question_text"],
                    subtasks=task["subtasks"],
                    model_answer=task["model_answer"],
                    student_answer=answer["code"],
                    marking_result=marking_result,
                )
                llm_result = generate_json(prompt, provider_name=feedback_model)
                results.append(
                    {
                        "task_id": task["task_id"],
                        "answer_id": answer["answer_id"],
                        "feedback_model": feedback_model,
                        "feedback_text": str(llm_result.get("feedback", "")).strip(),
                    }
                )
                print(f"[{feedback_model}] Feedback {task['task_id']} / {answer['answer_id']}")

    save_generated_answers(results, results_dir / "feedback_results.json")
    print(f"Saved: {results_dir / 'feedback_results.json'}")


if __name__ == "__main__":
    main()
