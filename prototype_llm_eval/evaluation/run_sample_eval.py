from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.llm_provider import generate_json
from prototype_llm_eval.evaluation.io_helpers import save_marking_results_csv


def _load_prompt(name: str) -> str:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / name).read_text(encoding="utf-8")


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    results_dir = base_dir / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    tasks = json.loads((data_dir / "fixed_tasks_with_answers.json").read_text(encoding="utf-8"))
    answers_by_task = {
        item["task_id"]: item["answers"]
        for item in json.loads((data_dir / "generated_answers.json").read_text(encoding="utf-8"))
    }
    template = _load_prompt("marking_prompt.txt")
    marking_models = [m.strip() for m in os.getenv("MARKING_MODELS", "gemini").split(",") if m.strip()]

    rows: list[dict[str, Any]] = []
    human_template_rows: list[dict[str, Any]] = []
    for marker_model in marking_models:
        for task in tasks:
            task_answers = answers_by_task.get(task["task_id"], [])
            for answer in task_answers:
                prompt = template.format(
                    question_text=task["question_text"],
                    subtasks=task["subtasks"],
                    model_answer=task["model_answer"],
                    student_answer=answer["code"],
                )
                result = generate_json(prompt, provider_name=marker_model)
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
                    }
                )
                print(f"[{marker_model}] Marked {task['task_id']} / {answer['answer_id']}")

                if marker_model == marking_models[0]:
                    for st in task["subtasks"]:
                        human_template_rows.append(
                            {
                                "task_id": task["task_id"],
                                "concept": task["concept"],
                                "answer_id": answer["answer_id"],
                                "variant_type": answer["variant_type"],
                                "subtask_id": st["subtask_id"],
                                "subtask_label": st["label"],
                                "human_mark": "",
                                "notes": "",
                            }
                        )

    save_marking_results_csv(rows, results_dir / "marking_results.csv")
    save_marking_results_csv(human_template_rows, results_dir / "human_marks_template.csv")
    print(f"Saved: {results_dir / 'marking_results.csv'}")
    print(f"Saved: {results_dir / 'human_marks_template.csv'}")


if __name__ == "__main__":
    main()
