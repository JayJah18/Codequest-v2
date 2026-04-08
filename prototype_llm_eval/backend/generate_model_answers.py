from __future__ import annotations

from typing import Any


def build_prompt(task: dict[str, Any], *, fix_feedback: str | None = None) -> str:
    fix_block = ""
    if fix_feedback:
        fix_block = f"""
A previous answer was rejected for this task. Address the issue and return a new complete solution.
Rejection note:
{fix_feedback}

"""
    return f"""
You are writing a perfect beginner Python model answer for a fixed evaluation task.

Question:
{task["question_text"]}

Subtasks:
{task["subtasks"]}
{fix_block}
Rules:
- The answer must satisfy all subtasks (by what the code does), not by repeating subtask text in comments.
- Output a single complete, runnable Python script: valid syntax, no placeholders, no truncation, no trailing junk.
- You may use any clear variable names; they do not need to match subtask wording.
- Keep it concise and beginner friendly.

Output format (critical):
- Respond with ONLY the Python source code.
- Do NOT wrap JSON around the code.
- Do NOT use markdown code fences unless you only use one ```python block and nothing else.
- No explanation before or after the code.
""".strip()


def main() -> None:
    """Delegates to prepare_fixed_dataset (validated pipeline)."""
    from prototype_llm_eval.backend.prepare_fixed_dataset import main as prepare_main

    prepare_main()


if __name__ == "__main__":
    main()
