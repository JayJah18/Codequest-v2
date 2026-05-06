from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .llm_provider import generate_json


def load_prompt_template(prompt_filename: str) -> str:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / prompt_filename).read_text(encoding="utf-8")

# Twenty slots: five per concept, beginner difficulty when building via LLM.
BANK_CONCEPT_SCHEDULE: tuple[str, ...] = (
    *(["variables"] * 5),
    *(["conditionals"] * 5),
    *(["loops"] * 5),
    *(["functions"] * 5),
)
GENERATION_MAX_RETRIES = int(os.getenv("TASK_GENERATION_MAX_RETRIES", "5"))


def get_question_generation_provider() -> str:
    """Live /demo-ui task JSON generation: gemini (default), llama (Ollama), or mistral."""
    raw = (os.getenv("QUESTION_GENERATION_PROVIDER") or "gemini").strip().lower()
    if raw in ("gemini", "llama", "mistral"):
        return raw
    print(f"WARNING: invalid QUESTION_GENERATION_PROVIDER={raw!r}; using gemini")
    return "gemini"


def normalize_task_payload(
    llm_result: dict[str, Any],
    *,
    task_id: str,
    concept: str,
    difficulty: str,
) -> dict[str, Any]:
    subtasks = llm_result.get("subtasks", [])
    if not isinstance(subtasks, list) or len(subtasks) != 5:
        raise ValueError(f"{task_id}: expected exactly 5 subtasks")

    normalized_subtasks: list[dict[str, str]] = []
    for idx, item in enumerate(subtasks, start=1):
        if isinstance(item, dict):
            label = str(item.get("label", "")).strip()
        else:
            label = str(item).strip()
        if not label:
            raise ValueError(f"{task_id}: empty subtask label at index {idx}")
        normalized_subtasks.append({"subtask_id": f"s{idx}", "label": label})

    question_text = str(llm_result.get("question_text", "")).strip()
    model_answer = str(llm_result.get("model_answer", "")).strip()
    if not question_text or not model_answer:
        raise ValueError(f"{task_id}: missing question_text or model_answer")

    return {
        "task_id": task_id,
        "concept": concept,
        "difficulty": difficulty,
        "question_text": question_text,
        "subtasks": normalized_subtasks,
        "model_answer": model_answer,
    }


def _validate_task_quality(task: dict[str, Any], *, task_id: str) -> None:
    question = task["question_text"].strip().lower()
    # Reject vague/meta questions that confuse learners.
    banned_fragments = (
        "what is the value of x",
        "enter a variable name",
        "verify the output matches",
        "for reference",
    )
    if any(fragment in question for fragment in banned_fragments):
        raise ValueError(f"{task_id}: question is too generic or meta-instructional")

    for idx, subtask in enumerate(task["subtasks"], start=1):
        sub = str(subtask.get("label", "")).strip().lower()
        if len(sub) < 8:
            raise ValueError(f"{task_id}: subtask {idx} is too short")
        if "for reference" in sub or "verify" in sub:
            raise ValueError(f"{task_id}: subtask {idx} is vague for marking")


def generate_one_task_llm(concept: str, difficulty: str, task_id: str) -> dict[str, Any]:
    template = load_prompt_template("task_generation_prompt.txt")
    last_error = "unknown generation failure"
    for attempt in range(1, GENERATION_MAX_RETRIES + 1):
        prompt = template.format(concept=concept, difficulty=difficulty)
        llm_result = generate_json(prompt, provider_name=get_question_generation_provider())
        try:
            task = normalize_task_payload(llm_result, task_id=task_id, concept=concept, difficulty=difficulty)
            _validate_task_quality(task, task_id=task_id)
            return task
        except ValueError as exc:
            last_error = str(exc)
            print(f"{task_id}: retry {attempt}/{GENERATION_MAX_RETRIES} - {last_error}")
    raise ValueError(f"{task_id}: unable to generate acceptable task after retries ({last_error})")


def build_llm_task_bank(difficulty: str = "beginner") -> list[dict[str, Any]]:
    bank: list[dict[str, Any]] = []
    for index, concept in enumerate(BANK_CONCEPT_SCHEDULE, start=1):
        task_id = f"q{index}"
        print(f"Task bank: generating {task_id} ({concept})...")
        task = generate_one_task_llm(concept, difficulty, task_id)
        bank.append(task)
    return bank


def load_fixed_tasks_from_file(data_dir: Path) -> list[dict[str, Any]]:
    """Load and validate fixed_tasks_with_answers.json (same rules as the server fixed mode)."""
    from .dataset_validation import load_fixed_tasks_with_answers_validated

    return load_fixed_tasks_with_answers_validated(data_dir / "fixed_tasks_with_answers.json")
