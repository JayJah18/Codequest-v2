from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import os

from prototype_llm_eval.backend.llm_provider import generate_text


VARIANTS: tuple[str, ...] = ("fully_correct", "partly_correct", "fully_incorrect")
ANSWER_VARIANT_PROVIDER = os.getenv("ANSWER_VARIANT_PROVIDER", "gemini")


def _variant_prompt(task: dict[str, Any], variant_type: str) -> str:
    variant_rule = {
        "fully_correct": "Solve all 5 subtasks correctly.",
        "partly_correct": "Intentionally solve only 2 or 3 subtasks correctly. The rest should be wrong or missing.",
        "fully_incorrect": "Produce code that clearly fails all subtasks.",
    }[variant_type]
    subtasks_txt = json.dumps(task.get("subtasks", []), indent=2, ensure_ascii=False)
    return f"""
You are simulating a beginner student's answer.

Task:
{task["question_text"]}

Subtasks:
{subtasks_txt}

Rules:
- {variant_rule}
- Keep the code realistic for a beginner.
- Return only Python code, no markdown.
""".strip()


def generate_variant_codes_for_task(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Three synthetic learner submissions: fully_correct, partly_correct, fully_incorrect (same contract as generated_answers.json)."""
    tid = str(task.get("task_id", "task"))
    out: list[dict[str, Any]] = []
    for idx, variant_type in enumerate(VARIANTS, start=1):
        code = generate_text(
            _variant_prompt(task, variant_type),
            provider_name=ANSWER_VARIANT_PROVIDER,
        ).strip()
        out.append(
            {
                "answer_id": f"{tid}_v{idx}",
                "variant_type": variant_type,
                "code": code,
            }
        )
    return out


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    tasks = json.loads((data_dir / "fixed_tasks_with_answers.json").read_text(encoding="utf-8"))
    answers: list[dict[str, Any]] = []

    for task in tasks:
        item = {"task_id": task["task_id"], "concept": task["concept"], "answers": []}
        for idx, variant_type in enumerate(VARIANTS, start=1):
            code = generate_text(
                _variant_prompt(task, variant_type),
                provider_name=ANSWER_VARIANT_PROVIDER,
            ).strip()
            item["answers"].append(
                {
                    "answer_id": f"{task['task_id']}_a{idx}",
                    "variant_type": variant_type,
                    "code": code,
                }
            )
            print(f"Generated {variant_type} answer for {task['task_id']}")
        answers.append(item)

    output_path = data_dir / "generated_answers.json"
    output_path.write_text(json.dumps(answers, indent=2), encoding="utf-8")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
