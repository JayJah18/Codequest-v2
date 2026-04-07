from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .llm_client import generate_json_with_ollama, load_prompt_template
from .storage import task_store


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


app = FastAPI(title="LLM Evaluation Prototype")
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.post("/generate-task")
def generate_task(payload: GenerateTaskRequest) -> dict[str, Any]:
    template = load_prompt_template("task_generation_prompt.txt")
    prompt = template.format(concept=payload.concept, difficulty=payload.difficulty)
    llm_result = generate_json_with_ollama(prompt)

    subtasks = llm_result.get("subtasks", [])
    if not isinstance(subtasks, list) or not 4 <= len(subtasks) <= 5:
        raise HTTPException(status_code=500, detail="Task generation did not return 4-5 subtasks.")

    task = {
        "task_id": str(uuid4()),
        "concept": payload.concept,
        "difficulty": payload.difficulty,
        "question_text": llm_result.get("question_text", "").strip(),
        "subtasks": [str(item).strip() for item in subtasks],
        "model_answer": llm_result.get("model_answer", "").strip(),
    }
    if not task["question_text"] or not task["model_answer"]:
        raise HTTPException(status_code=500, detail="Task generation returned incomplete JSON.")

    task_store.save_task(task)
    return task


@app.post("/mark-answer")
def mark_answer(payload: MarkAnswerRequest) -> dict[str, Any]:
    task = task_store.get_task(payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    template = load_prompt_template("marking_prompt.txt")
    prompt = template.format(
        question_text=task["question_text"],
        subtasks=task["subtasks"],
        model_answer=task["model_answer"],
        student_answer=payload.student_answer,
    )
    llm_result = generate_json_with_ollama(prompt)
    required = {"subtask_marks", "overall_score", "max_score", "star_rating", "reasoning"}
    if not required.issubset(set(llm_result.keys())):
        raise HTTPException(status_code=500, detail="Marking did not return required JSON fields.")
    return llm_result


@app.post("/generate-feedback")
def generate_feedback(payload: FeedbackRequest) -> dict[str, str]:
    task = task_store.get_task(payload.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    template = load_prompt_template("feedback_prompt.txt")
    prompt = template.format(
        question_text=task["question_text"],
        subtasks=task["subtasks"],
        model_answer=task["model_answer"],
        student_answer=payload.student_answer,
        marking_result=payload.marking_result,
    )
    llm_result = generate_json_with_ollama(prompt)
    feedback = str(llm_result.get("feedback", "")).strip()
    if not feedback:
        raise HTTPException(status_code=500, detail="Feedback generation did not return feedback text.")
    return {"feedback": feedback}
