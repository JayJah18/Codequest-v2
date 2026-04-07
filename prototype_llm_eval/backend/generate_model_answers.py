from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.llm_client import generate_json_with_ollama


def build_prompt(task: dict[str, Any]) -> str:
    return f"""
You are writing a perfect beginner Python model answer for a fixed evaluation task.
Return JSON only. Do not return markdown. Do not return extra keys.

Question:
{task["question_text"]}

Subtasks:
{task["subtasks"]}

Rules:
- The answer must satisfy all subtasks.
- Keep it concise and beginner friendly.
- Provide Python code only inside the model_answer string.

Output schema:
{{
  "model_answer": "string"
}}
""".strip()


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    input_path = data_dir / "fixed_tasks.json"
    output_path = data_dir / "fixed_tasks_with_answers.json"

    tasks = json.loads(input_path.read_text(encoding="utf-8"))
    for task in tasks:
        result = generate_json_with_ollama(build_prompt(task))
        model_answer = str(result.get("model_answer", "")).strip()
        if not model_answer:
            raise ValueError(f"Missing model_answer for task {task['task_id']}")
        task["model_answer"] = model_answer
        print(f"Generated model answer for {task['task_id']}")

    output_path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
