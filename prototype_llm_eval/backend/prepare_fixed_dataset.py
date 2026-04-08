from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .dataset_validation import (
    EXPECTED_TOTAL_SUBTASKS,
    load_json_task_list,
    validate_dataset_completeness,
    validate_task_schema,
)
from .generate_model_answers import build_prompt
from .llm_provider import generate_text

INPUT_NAME = "fixed_tasks.json"
OUTPUT_NAME = "fixed_tasks_with_answers.json"
MAX_RETRIES = int(os.getenv("PREPARE_MODEL_ANSWER_MAX_RETRIES", "4"))
TASK_GENERATION_PROVIDER = os.getenv("TASK_GENERATION_PROVIDER", "gemini")


def _python_compiles(code: str) -> tuple[bool, str]:
    stripped = code.strip()
    if len(stripped) < 8:
        return False, "Answer too short or empty."
    try:
        compile(stripped, "<model_answer>", "exec")
    except SyntaxError as exc:
        return False, f"Python syntax error: {exc.msg} (line {exc.lineno})"
    return True, ""


def _generate_valid_model_answer(task: dict[str, Any]) -> str:
    last_reason = ""
    for attempt in range(1, MAX_RETRIES + 1):
        prompt = build_prompt(task, fix_feedback=last_reason or None)
        model_answer = generate_text(prompt, provider_name=TASK_GENERATION_PROVIDER)
        ok, reason = _python_compiles(model_answer)
        if ok:
            return model_answer.strip()
        last_reason = reason
        print(f"[{task['task_id']}] retry {attempt}/{MAX_RETRIES}: {reason}")
    raise RuntimeError(f"Could not generate valid model_answer for {task['task_id']}")


def _prepare_tasks_with_llm(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for task in tasks:
        row = dict(task)
        existing = str(row.get("model_answer", "")).strip()
        if existing:
            ok, _ = _python_compiles(existing)
            if ok:
                row["model_answer"] = existing
                prepared.append(row)
                continue
        row["model_answer"] = _generate_valid_model_answer(row)
        prepared.append(row)
        print(f"Generated model answer for {row['task_id']}")
    return prepared


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    input_path = data_dir / INPUT_NAME
    output_path = data_dir / OUTPUT_NAME

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    tasks = load_json_task_list(input_path)
    shape_errors: list[str] = []
    for i, task in enumerate(tasks):
        label = f"task[{i}] ({task.get('task_id', '?')})"
        shape_errors.extend(validate_task_schema(task, label=label, require_model_answer=False))
        ma = task.get("model_answer")
        if ma is not None and not isinstance(ma, str):
            shape_errors.append(f"{label}: model_answer must be string if present")

    if shape_errors:
        print("ERROR: Input validation failed:", file=sys.stderr)
        for err in shape_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    prepared = _prepare_tasks_with_llm(tasks)
    final_errors = validate_dataset_completeness(prepared)
    if final_errors:
        print("ERROR: Prepared dataset failed final validation (output not written):", file=sys.stderr)
        for err in final_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    output_path.write_text(json.dumps(prepared, indent=2), encoding="utf-8")
    subtask_total = sum(len(t.get("subtasks", [])) for t in prepared)
    print("Success:")
    print(f"  Tasks prepared: {len(prepared)}")
    print(f"  Subtasks counted: {subtask_total} (expected {EXPECTED_TOTAL_SUBTASKS})")
    print(f"  File saved: {output_path}")


if __name__ == "__main__":
    main()
