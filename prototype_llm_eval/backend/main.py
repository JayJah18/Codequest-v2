from __future__ import annotations

import os
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .dataset_validation import load_fixed_tasks_with_answers_validated
from .llm_provider import generate_json
from .storage import task_store
from .task_bank import generate_one_task_llm

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
data_dir = Path(__file__).resolve().parent.parent / "data"

# Fixed mode: load validated file on startup.
# Dynamic mode: generate one task on demand per /generate-task call.
USE_FIXED_DATASET = os.getenv("USE_FIXED_DATASET", "false").lower() == "true"

BANK_DIFFICULTY = os.getenv("BANK_DIFFICULTY", "beginner")
MARKING_PROVIDER = os.getenv("MARKING_PROVIDER", "gemini")
FEEDBACK_PROVIDER = os.getenv("FEEDBACK_PROVIDER", "gemini")

_task_bank: list[dict[str, Any]] = []


class GenerateTaskRequest(BaseModel):
    concept: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)


class MarkAnswerRequest(BaseModel):
    task_id: str = Field(min_length=1)
    student_answer: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    task_id: str = Field(min_length=1)
    student_answer: str = Field(min_length=1)
    marking_result: dict[str, Any]


def _select_task_from_bank(concept: str, difficulty: str) -> dict[str, Any]:
    if not _task_bank:
        raise HTTPException(
            status_code=503,
            detail="Task bank not ready yet. Wait for startup to finish or check server logs.",
        )
    filtered = [t for t in _task_bank if t.get("concept") == concept and t.get("difficulty") == difficulty]
    if not filtered:
        filtered = [t for t in _task_bank if t.get("concept") == concept]
    if not filtered:
        raise HTTPException(status_code=404, detail="No task found for that concept in the bank.")
    return random.choice(filtered)


def _load_prompt(prompt_filename: str) -> str:
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / prompt_filename).read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _task_bank
    task_store.tasks.clear()
    if USE_FIXED_DATASET:
        fixed_path = data_dir / "fixed_tasks_with_answers.json"
        print(f"Loading fixed task bank (read-only): {fixed_path}")
        try:
            _task_bank = load_fixed_tasks_with_answers_validated(fixed_path)
        except (FileNotFoundError, ValueError) as exc:
            raise RuntimeError(
                "Fixed dataset is missing or failed validation.\n"
                "Prepare a validated dataset first:\n"
                "  python -m prototype_llm_eval.backend.prepare_fixed_dataset\n"
                f"Original error: {exc}"
            ) from exc
        for task in _task_bank:
            task_store.save_task(task)
        print(f"Fixed task bank ready: {len(_task_bank)} tasks.")
    else:
        _task_bank = []
        print("Dynamic mode ready: tasks are generated on demand per request.")
    yield


app = FastAPI(title="LLM Evaluation Prototype", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.post("/generate-task")
def generate_task(payload: GenerateTaskRequest) -> dict[str, Any]:
    if USE_FIXED_DATASET:
        task = _select_task_from_bank(payload.concept, payload.difficulty)
        task_store.save_task(task)
        return task

    task_id = f"dyn-{uuid4()}"
    task = generate_one_task_llm(
        concept=payload.concept,
        difficulty=payload.difficulty,
        task_id=task_id,
    )
    task_store.save_task(task)
    return task


@app.post("/mark-answer")
def mark_answer(payload: MarkAnswerRequest) -> dict[str, Any]:
    task = task_store.get_task(payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    template = _load_prompt("marking_prompt.txt")
    prompt = template.format(
        question_text=task["question_text"],
        subtasks=task["subtasks"],
        model_answer=task["model_answer"],
        student_answer=payload.student_answer,
    )
    llm_result = generate_json(prompt, provider_name=MARKING_PROVIDER)
    required = {"subtask_results", "overall_score", "max_score", "star_rating", "reasoning"}
    if not required.issubset(set(llm_result.keys())):
        raise HTTPException(status_code=500, detail="Marking did not return required JSON fields.")
    return llm_result


@app.post("/generate-feedback")
def generate_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    task = task_store.get_task(payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    template = _load_prompt("feedback_prompt.txt")
    prompt = template.format(
        question_text=task["question_text"],
        subtasks=task["subtasks"],
        model_answer=task["model_answer"],
        student_answer=payload.student_answer,
        marking_result=payload.marking_result,
    )
    llm_result = generate_json(prompt, provider_name=FEEDBACK_PROVIDER)
    feedback = str(llm_result.get("feedback", "")).strip()
    if not feedback:
        raise HTTPException(status_code=500, detail="Feedback generation did not return feedback text.")
    return {"feedback": feedback}
