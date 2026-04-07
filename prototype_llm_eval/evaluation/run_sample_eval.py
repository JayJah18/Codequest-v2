from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.llm_client import generate_json_with_ollama, load_prompt_template
from prototype_llm_eval.evaluation.io_helpers import save_marking_results_csv


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
    template = load_prompt_template("marking_prompt.txt")

    rows: list[dict[str, Any]] = []
    human_template_rows: list[dict[str, Any]] = []
    for task in tasks:
        task_answers = answers_by_task.get(task["task_id"], [])
        for answer in task_answers:
            prompt = template.format(
                question_text=task["question_text"],
                subtasks=task["subtasks"],
                model_answer=task["model_answer"],
                student_answer=answer["code"],
            )
            result = generate_json_with_ollama(prompt)
            rows.append(
                {
                    "task_id": task["task_id"],
                    "concept": task["concept"],
                    "answer_id": answer["answer_id"],
                    "answer_type": answer["type"],
                    "subtask_results": json.dumps(result.get("subtask_marks", [])),
                    "overall_score": result.get("overall_score", 0),
                    "star_rating": result.get("star_rating", 0.0),
                }
            )
            for subtask_id in range(1, len(task["subtasks"]) + 1):
                human_template_rows.append(
                    {
                        "task_id": task["task_id"],
                        "answer_id": answer["answer_id"],
                        "subtask_id": subtask_id,
                        "human_mark": "",
                        "notes": "",
                    }
                )
            print(f"Marked {task['task_id']} / {answer['answer_id']}")

    save_marking_results_csv(rows, results_dir / "marking_results.csv")
    save_marking_results_csv(human_template_rows, results_dir / "human_marks_template.csv")
    print(f"Saved: {results_dir / 'marking_results.csv'}")
    print(f"Saved: {results_dir / 'human_marks_template.csv'}")


if __name__ == "__main__":
    main()
