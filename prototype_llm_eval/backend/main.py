from __future__ import annotations

import csv
import json
import os
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .dataset_validation import load_fixed_tasks_with_answers_validated
from .generate_answer_variants import generate_variant_codes_for_task
from .live_task_validation import validate_live_task_structure
from .llm_provider import GeminiProviderAuthError, generate_json, get_configured_model_name
from .storage import task_store
from .task_bank import generate_one_task_llm, get_question_generation_provider
from ..evaluation.pilot_filters import apply_pilot_task_filter, load_generated_answers_by_task
from ..evaluation.research_summary_payload import build_research_summary

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
data_dir = Path(__file__).resolve().parent.parent / "data"
results_dir = Path(__file__).resolve().parent.parent / "evaluation" / "results"
eval_ui_dir = Path(__file__).resolve().parent.parent / "eval_ui"
demo_ui_dir = Path(__file__).resolve().parent.parent / "demo_ui"
research_ui_dir = Path(__file__).resolve().parent.parent / "research_ui"
progress_ui_dir = Path(__file__).resolve().parent.parent / "progress_ui"

QUESTION_REVIEW_FIELDNAMES = [
    "task_id",
    "concept",
    "difficulty",
    "question_text",
    "subtasks_summary",
    "human_question_label",
    "notes",
    "level_fit",
    "topic_fit",
    "clarity",
    "subtasks_json",
    "model_answer_present",
]

FEEDBACK_REVIEW_FIELDNAMES = [
    "task_id",
    "concept",
    "answer_id",
    "variant_type",
    "feedback_model",
    "feedback_text",
    "relevance_score",
    "clarity_score",
    "usefulness_score",
    "overall_feedback_label",
    "notes",
]

# --- Two evaluation/demo modes (orthogonal concerns) ---
#
# A) FIXED BENCHMARK MODE (USE_FIXED_DATASET=true)
#    - At startup, loads frozen `data/fixed_tasks_with_answers.json` into memory for /generate-task sampling
#      and populates task_store with those 20 tasks.
#    - Offline scripts (run_sample_eval, compare_results, eval-ui data) always read that JSON from disk;
#      they do not depend on this flag.
#
# B) DYNAMIC SERVER MODE (USE_FIXED_DATASET=false)
#    - No frozen bank at startup; POST /generate-task generates via QUESTION_GENERATION_PROVIDER for each new task.
#
# Live demo generation: POST /api/demo/generate-live-task uses QUESTION_GENERATION_PROVIDER (gemini / llama / mistral),
# saves the result to task_store for marking/feedback, and is independent of USE_FIXED_DATASET so
# supervisors can see live generation even while the server also hosts the frozen bank for other routes.
USE_FIXED_DATASET = os.getenv("USE_FIXED_DATASET", "false").lower() == "true"

BANK_DIFFICULTY = os.getenv("BANK_DIFFICULTY", "beginner")
MARKING_PROVIDER = os.getenv("MARKING_PROVIDER", "gemini")
FEEDBACK_PROVIDER = os.getenv("FEEDBACK_PROVIDER", "gemini")

# --- Prototype admin gate (NOT production auth: no hashing, no DB, env-only credentials) ---
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip() or "prototype-change-SESSION_SECRET-in-local-env"


def _prototype_admin_credentials() -> tuple[str, str]:
    """
    Read admin username/password from the process environment on each call.
    If ADMIN_PASSWORD is unset, the effective password is 'codequest-demo' (restart after editing local.env).
    """
    user = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    raw = os.getenv("ADMIN_PASSWORD", "").strip()
    effective = raw if raw else "codequest-demo"
    return user, effective


def _session_is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _is_public_path(path: str) -> bool:
    """Paths that do not require an admin session cookie."""
    if path in ("/", "/login"):
        return True
    if path.startswith("/static/"):
        return True
    if path.startswith("/demo-ui"):
        return True
    if path.startswith("/api/demo/") or path.startswith("/api/auth/"):
        return True
    if path.startswith("/eval-ui/static/"):
        return True
    if path.startswith("/research-ui/static/"):
        return True
    if path.startswith("/progress-ui/static/"):
        return True
    if path in ("/openapi.json", "/redoc") or path.startswith("/docs"):
        return True
    return False


class PrototypeAdminGateMiddleware(BaseHTTPMiddleware):
    """
    Enforces a single 'admin' role via signed session cookie (SessionMiddleware).
    Public learner flow: /, /login, /demo-ui. Everything else requires login.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path
        if _is_public_path(path):
            return await call_next(request)
        if _session_is_admin(request):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Admin authentication required. This prototype uses POST /api/auth/login "
                        "(see ADMIN_USERNAME / ADMIN_PASSWORD in local.env)."
                    )
                },
            )
        return RedirectResponse(url=f"/login?next={quote(path, safe='')}", status_code=302)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


_task_bank: list[dict[str, Any]] = []


class GenerateTaskRequest(BaseModel):
    concept: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    include_answer_variants: bool = Field(
        default=True,
        description="If true, generate three example learner answers (fully_correct / partly_correct / fully_incorrect) for the demo.",
    )


class MarkAnswerRequest(BaseModel):
    task_id: str = Field(min_length=1)
    student_answer: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    task_id: str = Field(min_length=1)
    student_answer: str = Field(min_length=1)
    marking_result: dict[str, Any]


class HumanSubtaskMark(BaseModel):
    subtask_id: str = Field(min_length=1)
    subtask_label: str = Field(min_length=1)
    human_mark: str = Field(min_length=1)
    llm_mark_for_subtask: str = ""


class SaveHumanMarksRequest(BaseModel):
    task_id: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    answer_id: str = Field(min_length=1)
    variant_type: str = Field(min_length=1)
    student_answer_code: str = Field(min_length=1)
    llm_marker_model: str = ""
    notes: str = ""
    subtasks: list[HumanSubtaskMark]


class QuestionReviewSaveRequest(BaseModel):
    task_id: str = Field(min_length=1)
    human_question_label: str = ""
    notes: str = ""
    level_fit: str = ""
    topic_fit: str = ""
    clarity: str = ""


class FeedbackReviewSaveRequest(BaseModel):
    task_id: str = Field(min_length=1)
    answer_id: str = Field(min_length=1)
    feedback_model: str = Field(min_length=1)
    relevance_score: str = ""
    clarity_score: str = ""
    usefulness_score: str = ""
    overall_feedback_label: str = ""
    notes: str = ""


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
    _au, _ = _prototype_admin_credentials()
    _raw_len = len(os.getenv("ADMIN_PASSWORD", "").strip())
    print(
        f"PROTOTYPE AUTH: login username={_au!r}; ADMIN_PASSWORD from process env is "
        f"{_raw_len} char(s). If 0, use password 'codequest-demo' or restart the server after editing local.env "
        f"(uvicorn --reload does not reload env from disk)."
    )
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

# Session must run before the admin gate (add_middleware: last added = outer / runs first).
app.add_middleware(PrototypeAdminGateMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="cq_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)


@app.exception_handler(GeminiProviderAuthError)
async def gemini_provider_auth_exception_handler(_request: Request, exc: GeminiProviderAuthError) -> JSONResponse:
    """503 = missing GEMINI_API_KEY; 502 = key rejected / wrong type for this SDK path."""
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
app.mount("/eval-ui/static", StaticFiles(directory=eval_ui_dir), name="eval-ui-static")
app.mount("/demo-ui/static", StaticFiles(directory=demo_ui_dir), name="demo-ui-static")
app.mount("/research-ui/static", StaticFiles(directory=research_ui_dir), name="research-ui-static")
app.mount("/progress-ui/static", StaticFiles(directory=progress_ui_dir), name="progress-ui-static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(frontend_dir / "login.html")


@app.get("/admin")
def admin_hub() -> FileResponse:
    return FileResponse(frontend_dir / "admin.html")


@app.get("/legacy-console")
def legacy_console_page() -> FileResponse:
    return FileResponse(frontend_dir / "legacy_console.html")


@app.post("/api/auth/login")
async def api_auth_login(request: Request, body: LoginRequest) -> dict[str, Any]:
    expected_user, expected_password = _prototype_admin_credentials()
    if body.username.strip() != expected_user or body.password != expected_password:
        hint = (
            "Invalid username or password. If ADMIN_PASSWORD is unset in the server process, "
            "the password is the default 'codequest-demo'. Start via start_demo_server.ps1 (loads local.env) "
            "and restart after changing local.env."
        )
        raise HTTPException(status_code=401, detail=hint)
    request.session["admin"] = True
    return {"ok": True, "role": "admin"}


@app.post("/api/auth/logout")
async def api_auth_logout(request: Request) -> dict[str, Any]:
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def api_auth_me(request: Request) -> dict[str, Any]:
    return {"authenticated": _session_is_admin(request), "role": "admin" if _session_is_admin(request) else "public"}


@app.get("/eval-ui")
def eval_ui_index() -> FileResponse:
    return FileResponse(eval_ui_dir / "index.html")


@app.get("/demo-ui")
def demo_ui_index() -> FileResponse:
    return FileResponse(demo_ui_dir / "index.html")


@app.get("/research-dashboard")
def research_dashboard() -> FileResponse:
    return FileResponse(research_ui_dir / "index.html")


@app.get("/progress-ui")
def progress_ui_index() -> FileResponse:
    return FileResponse(progress_ui_dir / "index.html")


@app.get("/api/research-summary")
def research_summary() -> dict[str, Any]:
    return build_research_summary(
        results_dir=results_dir,
        data_dir=data_dir,
        use_fixed_dataset_for_server=USE_FIXED_DATASET,
    )


def _subtask_summary_inline(subtasks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for st in subtasks:
        if isinstance(st, dict):
            sid = str(st.get("subtask_id", "")).strip()
            lab = str(st.get("label", "")).strip()
            parts.append(f"{sid}: {lab}" if sid else lab)
    return " | ".join(parts)


def _review_row_from_task(t: dict[str, Any]) -> dict[str, str]:
    subtasks = t.get("subtasks") if isinstance(t.get("subtasks"), list) else []
    ma = t.get("model_answer")
    present = "yes" if isinstance(ma, str) and ma.strip() else "no"
    return {
        "task_id": str(t.get("task_id", "")),
        "concept": str(t.get("concept", "")),
        "difficulty": str(t.get("difficulty", "")),
        "question_text": str(t.get("question_text", "")),
        "subtasks_summary": _subtask_summary_inline(subtasks),
        "subtasks_json": json.dumps(subtasks, ensure_ascii=False),
        "model_answer_present": present,
        "human_question_label": "",
        "notes": "",
        "level_fit": "",
        "topic_fit": "",
        "clarity": "",
    }


def _question_review_csv_path() -> Path:
    return results_dir / "question_generation_review.csv"


def _write_question_review_csv(rows: list[dict[str, Any]]) -> Path:
    path = _question_review_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUESTION_REVIEW_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: str(row.get(k, "")) for k in QUESTION_REVIEW_FIELDNAMES})
    return path


@app.get("/api/research/question-review")
def get_question_generation_review() -> dict[str, Any]:
    """
    Tasks from the frozen benchmark plus any saved human appropriateness labels
    in evaluation/results/question_generation_review.csv.
    """
    fixed_path = data_dir / "fixed_tasks_with_answers.json"
    tasks = load_fixed_tasks_with_answers_validated(fixed_path)
    csv_path = _question_review_csv_path()
    existing: dict[str, dict[str, str]] = {}
    if csv_path.exists():
        for r in _read_csv_rows(csv_path):
            tid = str(r.get("task_id", "")).strip()
            if tid:
                existing[tid] = r

    items: list[dict[str, Any]] = []
    reviewed = 0
    appropriate = 0
    by_concept: dict[str, dict[str, int]] = {}

    for t in tasks:
        tid = str(t.get("task_id", "")).strip()
        row = _review_row_from_task(t)
        if tid in existing:
            old = existing[tid]
            for key in QUESTION_REVIEW_FIELDNAMES:
                val = old.get(key)
                if val is not None and str(val).strip():
                    row[key] = str(val)

        label = str(row.get("human_question_label", "")).strip().lower()
        concept = str(t.get("concept", "")).strip() or "—"
        if concept not in by_concept:
            by_concept[concept] = {"n": 0, "reviewed": 0, "appropriate": 0}
        by_concept[concept]["n"] += 1
        if label in {"appropriate", "inappropriate"}:
            reviewed += 1
            by_concept[concept]["reviewed"] += 1
            if label == "appropriate":
                appropriate += 1
                by_concept[concept]["appropriate"] += 1

        subtasks_out = t.get("subtasks") if isinstance(t.get("subtasks"), list) else []
        items.append(
            {
                "task_id": tid,
                "concept": t.get("concept"),
                "difficulty": t.get("difficulty"),
                "question_text": t.get("question_text"),
                "subtasks": subtasks_out,
                "model_answer_present": row.get("model_answer_present"),
                "has_model_answer": row.get("model_answer_present") == "yes",
                "human_question_label": row.get("human_question_label", ""),
                "notes": row.get("notes", ""),
                "level_fit": row.get("level_fit", ""),
                "topic_fit": row.get("topic_fit", ""),
                "clarity": row.get("clarity", ""),
            }
        )

    pct = (appropriate / reviewed) if reviewed else None
    return {
        "file": str(csv_path),
        "file_exists": csv_path.exists(),
        "tasks": items,
        "summary": {
            "total_tasks": len(items),
            "reviewed": reviewed,
            "appropriate_count": appropriate,
            "percent_appropriate": pct,
            "per_concept": by_concept,
        },
    }


@app.post("/api/research/question-review")
def save_question_generation_review(payload: QuestionReviewSaveRequest) -> dict[str, Any]:
    label_raw = payload.human_question_label.strip().lower()
    if label_raw and label_raw not in {"appropriate", "inappropriate"}:
        raise HTTPException(
            status_code=400,
            detail='human_question_label must be empty, "appropriate", or "inappropriate".',
        )

    fixed_path = data_dir / "fixed_tasks_with_answers.json"
    tasks = load_fixed_tasks_with_answers_validated(fixed_path)
    tid_target = payload.task_id.strip()
    ids = {str(t.get("task_id", "")).strip() for t in tasks}
    if tid_target not in ids:
        raise HTTPException(status_code=404, detail="task_id not found in fixed benchmark.")

    csv_path = _question_review_csv_path()
    existing: dict[str, dict[str, str]] = {}
    if csv_path.exists():
        for r in _read_csv_rows(csv_path):
            tid = str(r.get("task_id", "")).strip()
            if tid:
                existing[tid] = r

    out_rows: list[dict[str, str]] = []
    for t in tasks:
        tid = str(t.get("task_id", "")).strip()
        row = _review_row_from_task(t)
        if tid in existing:
            old = existing[tid]
            for key in QUESTION_REVIEW_FIELDNAMES:
                val = old.get(key)
                if val is not None and str(val).strip():
                    row[key] = str(val)
        if tid == tid_target:
            row["human_question_label"] = label_raw
            row["notes"] = payload.notes.strip()
            row["level_fit"] = payload.level_fit.strip()
            row["topic_fit"] = payload.topic_fit.strip()
            row["clarity"] = payload.clarity.strip()
        out_rows.append(row)

    written = _write_question_review_csv(out_rows)
    return {"ok": True, "path": str(written), "task_id": tid_target}


def _feedback_results_json_path() -> Path:
    return results_dir / "feedback_results.json"


def _feedback_review_csv_path() -> Path:
    return results_dir / "feedback_review.csv"


def _feedback_review_row_key(r: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(r.get("task_id", "")).strip(),
        str(r.get("answer_id", "")).strip(),
        str(r.get("feedback_model", "")).strip(),
    )


def _load_feedback_results_items() -> list[dict[str, Any]]:
    path = _feedback_results_json_path()
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _merge_feedback_review_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Merge feedback_results.json with optional saved scores in feedback_review.csv.
    """
    json_items = _load_feedback_results_items()
    csv_path = _feedback_review_csv_path()
    saved: dict[tuple[str, str, str], dict[str, str]] = {}
    if csv_path.exists():
        for r in _read_csv_rows(csv_path):
            k = _feedback_review_row_key(r)
            if all(k):
                saved[k] = r

    items: list[dict[str, Any]] = []
    error_n = 0
    scored_n = 0
    models: set[str] = set()

    for raw in json_items:
        tid = str(raw.get("task_id", "")).strip()
        aid = str(raw.get("answer_id", "")).strip()
        fm = str(raw.get("feedback_model", "")).strip()
        k = (tid, aid, fm)
        models.add(fm)

        text = str(raw.get("feedback_text", "")).strip()
        if text.upper().startswith("FEEDBACK_ERROR"):
            error_n += 1

        row: dict[str, Any] = {
            "task_id": tid,
            "concept": str(raw.get("concept", "")).strip(),
            "answer_id": aid,
            "variant_type": str(raw.get("variant_type", "")).strip(),
            "feedback_model": fm,
            "feedback_text": text,
            "relevance_score": "",
            "clarity_score": "",
            "usefulness_score": "",
            "overall_feedback_label": "",
            "notes": "",
            "is_feedback_error": text.upper().startswith("FEEDBACK_ERROR"),
            "run_timestamp": str(raw.get("run_timestamp", "")).strip(),
            "actual_model_name": str(raw.get("actual_model_name", "")).strip(),
        }
        if k in saved:
            old = saved[k]
            for col in ("relevance_score", "clarity_score", "usefulness_score", "overall_feedback_label", "notes"):
                v = old.get(col)
                if v is not None and str(v).strip():
                    row[col] = str(v).strip()

        rs, cs, us = row["relevance_score"], row["clarity_score"], row["usefulness_score"]
        if rs in {"1", "2", "3"} and cs in {"1", "2", "3"} and us in {"1", "2", "3"}:
            scored_n += 1

        items.append(row)

    summary = {
        "total": len(items),
        "feedback_error_rows": error_n,
        "fully_scored_1_3_count": scored_n,
        "models_sorted": sorted(m for m in models if m),
        "json_path": str(_feedback_results_json_path()),
        "csv_path": str(csv_path),
        "csv_exists": csv_path.exists(),
    }
    return items, summary


def _write_feedback_review_csv(rows: list[dict[str, str]]) -> Path:
    path = _feedback_review_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEEDBACK_REVIEW_FIELDNAMES)
        w.writeheader()
        for row in rows:
            w.writerow({fn: str(row.get(fn, "")) for fn in FEEDBACK_REVIEW_FIELDNAMES})
    return path


@app.get("/api/research/feedback-review")
def get_feedback_review() -> dict[str, Any]:
    """
    Rows from evaluation/results/feedback_results.json merged with human scores in feedback_review.csv.
    """
    items, summary = _merge_feedback_review_rows()
    return {
        "items": items,
        "summary": summary,
    }


@app.post("/api/research/feedback-review")
def save_feedback_review(payload: FeedbackReviewSaveRequest) -> dict[str, Any]:
    json_items = _load_feedback_results_items()
    if not json_items:
        raise HTTPException(
            status_code=404,
            detail="No feedback_results.json — run: python -m prototype_llm_eval.evaluation.run_feedback_eval",
        )

    rs = payload.relevance_score.strip()
    cs = payload.clarity_score.strip()
    us = payload.usefulness_score.strip()
    for name, val in (("relevance_score", rs), ("clarity_score", cs), ("usefulness_score", us)):
        if val and val not in {"1", "2", "3"}:
            raise HTTPException(status_code=400, detail=f"{name} must be empty or 1, 2, or 3.")
    lab = payload.overall_feedback_label.strip().lower()
    if lab and lab not in {"poor", "acceptable", "good"}:
        raise HTTPException(
            status_code=400,
            detail='overall_feedback_label must be empty, "poor", "acceptable", or "good".',
        )

    tid_t = payload.task_id.strip()
    aid_t = payload.answer_id.strip()
    fm_t = payload.feedback_model.strip()
    target = (tid_t, aid_t, fm_t)

    merged, _summary = _merge_feedback_review_rows()
    found = False
    out_rows: list[dict[str, str]] = []
    for row in merged:
        k = (row["task_id"], row["answer_id"], row["feedback_model"])
        if k == target:
            found = True
            row = {
                **row,
                "relevance_score": rs,
                "clarity_score": cs,
                "usefulness_score": us,
                "overall_feedback_label": lab,
                "notes": payload.notes.strip(),
            }
        out_rows.append({fn: str(row.get(fn, "")) for fn in FEEDBACK_REVIEW_FIELDNAMES})

    if not found:
        raise HTTPException(status_code=404, detail="No matching row in feedback_results.json for that task/answer/model.")

    written = _write_feedback_review_csv(out_rows)
    return {"ok": True, "path": str(written), "task_id": tid_t, "answer_id": aid_t, "feedback_model": fm_t}


def _demo_tasks_list() -> list[dict[str, Any]]:
    return load_fixed_tasks_with_answers_validated(data_dir / "fixed_tasks_with_answers.json")


_generated_answers_demo_cache: list[dict[str, Any]] | None = None


def _demo_answer_variants_from_file(task_id: str) -> list[dict[str, Any]]:
    """Pre-built variants from data/generated_answers.json (frozen benchmark only)."""
    global _generated_answers_demo_cache
    if _generated_answers_demo_cache is None:
        path = data_dir / "generated_answers.json"
        if path.exists():
            _generated_answers_demo_cache = json.loads(path.read_text(encoding="utf-8"))
        else:
            _generated_answers_demo_cache = []
    tid = task_id.strip()
    for block in _generated_answers_demo_cache:
        if str(block.get("task_id", "")).strip() == tid:
            return list(block.get("answers") or [])
    return []


def _resolve_task_for_demo(task_id: str) -> dict[str, Any]:
    """Prefer a freshly generated live task in task_store; else fall back to frozen benchmark by id."""
    tid = task_id.strip()
    live = task_store.get_task(tid)
    if live:
        return live
    for row in _demo_tasks_list():
        if str(row.get("task_id", "")).strip() == tid:
            return row
    raise HTTPException(
        status_code=404,
        detail="Task not found. Generate a live task (Demo UI) or use a frozen benchmark id such as q1.",
    )


@app.get("/api/demo/config")
def demo_config() -> dict[str, Any]:
    gemini_ok = bool(os.getenv("GEMINI_API_KEY", "").strip())
    qg = get_question_generation_provider()
    return {
        "use_fixed_dataset": USE_FIXED_DATASET,
        "gemini_api_key_configured": gemini_ok,
        "question_generation_provider": qg,
        "question_generation_model": get_configured_model_name(qg),
        "marking_provider": MARKING_PROVIDER,
        "marking_model": get_configured_model_name(MARKING_PROVIDER),
        "feedback_provider": FEEDBACK_PROVIDER,
        "feedback_model": get_configured_model_name(FEEDBACK_PROVIDER),
        "notes": {
            "frozen_benchmark": "data/fixed_tasks_with_answers.json — used by eval scripts, eval-ui, and optional sample load in demo.",
            "live_generation": (
                "POST /api/demo/generate-live-task — one fresh JSON task from QUESTION_GENERATION_PROVIDER "
                "(gemini / llama / mistral); validated then stored in task_store for marking."
            ),
            "gemini_auth": (
                "The gemini provider uses GEMINI_API_KEY + google.generativeai (Generative Language API), "
                "not Vertex AI or service accounts. Marking/feedback use MARKING_PROVIDER and FEEDBACK_PROVIDER separately."
            ),
            "gemini_env": "For live generation with gemini: set GEMINI_API_KEY (+ GEMINI_MODEL) in local.env. "
            "For local demo without Gemini: QUESTION_GENERATION_PROVIDER=llama and run Ollama.",
        },
    }


@app.post("/api/demo/generate-live-task")
def demo_generate_live_task(payload: GenerateTaskRequest) -> dict[str, Any]:
    """
    Supervisor/demo path: one new LLM-authored task (QUESTION_GENERATION_PROVIDER; ignores USE_FIXED_DATASET).
    Response includes structural validation metadata (generation is not blindly trusted).
    """
    provider = get_question_generation_provider()
    task_id = f"dyn-{uuid4()}"
    task = generate_one_task_llm(
        concept=payload.concept.strip(),
        difficulty=payload.difficulty.strip(),
        task_id=task_id,
    )
    validation = validate_live_task_structure(task, label=task_id)
    if not validation["ok"]:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Live {provider} output failed structural validation.",
                "validation": validation,
                "task": task,
            },
        )
    task_store.save_task(task)
    answer_variants: list[dict[str, Any]] = []
    variants_note = ""
    if payload.include_answer_variants:
        try:
            answer_variants = generate_variant_codes_for_task(task)
        except Exception as exc:
            variants_note = f"Example answers were not generated ({type(exc).__name__}). You can still type code or load a frozen task for pre-built variants."
    return {
        "task": task,
        "validation": validation,
        "task_source": f"live_{provider}",
        "answer_variants": answer_variants,
        **({"variants_note": variants_note} if variants_note else {}),
    }


@app.get("/api/demo/task")
def demo_task(task_id: str | None = None) -> dict[str, Any]:
    """Read-only sample from the frozen benchmark (contrast with POST /api/demo/generate-live-task)."""
    tasks = _demo_tasks_list()
    if task_id:
        for t in tasks:
            if str(t.get("task_id", "")).strip() == task_id.strip():
                tid = str(t.get("task_id", "")).strip()
                return {
                    **t,
                    "task_source": "frozen_benchmark_sample",
                    "answer_variants": _demo_answer_variants_from_file(tid),
                }
        raise HTTPException(status_code=404, detail="Task not found in fixed benchmark.")
    first = tasks[0]
    tid0 = str(first.get("task_id", "")).strip()
    return {
        **first,
        "task_source": "frozen_benchmark_sample",
        "answer_variants": _demo_answer_variants_from_file(tid0),
    }


@app.post("/api/demo/mark")
def demo_mark(payload: MarkAnswerRequest) -> dict[str, Any]:
    task = _resolve_task_for_demo(payload.task_id)

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


@app.post("/api/demo/feedback")
def demo_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    task = _resolve_task_for_demo(payload.task_id)

    template = _load_prompt("feedback_prompt.txt")
    prompt = template.format(
        question_text=task["question_text"],
        subtasks=task["subtasks"],
        model_answer=task["model_answer"],
        student_answer=payload.student_answer,
        marking_result=json.dumps(payload.marking_result, ensure_ascii=False),
    )
    llm_result = generate_json(prompt, provider_name=FEEDBACK_PROVIDER)
    feedback = str(llm_result.get("feedback", "")).strip()
    if not feedback:
        raise HTTPException(status_code=500, detail="Feedback generation did not return feedback text.")
    return {"feedback": feedback}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _write_csv_rows(path: Path, rows: list[dict[str, Any]], field_order: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        writer.writeheader()
        writer.writerows(rows)


@app.get("/api/eval/data")
def eval_data() -> dict[str, Any]:
    tasks_all = load_fixed_tasks_with_answers_validated(data_dir / "fixed_tasks_with_answers.json")
    # Human marking UI defaults to all 20 tasks so pilot env vars (TASK_IDS, etc.) on the server
    # do not hide the rest of the benchmark. Set EVAL_UI_PILOT_ONLY=true to apply the same pilot filter as batch scripts.
    if os.getenv("EVAL_UI_PILOT_ONLY", "false").lower() == "true":
        tasks, pilot_meta = apply_pilot_task_filter(tasks_all)
    else:
        tasks = tasks_all
        pilot_meta = {"EVAL_UI_PILOT_ONLY": False, "task_count": len(tasks_all)}
    answers_by_task = load_generated_answers_by_task(data_dir)
    marking_rows = _read_csv_rows(results_dir / "marking_results.csv")
    human_rows = _read_csv_rows(results_dir / "human_marks.csv")

    return {
        "pilot_filter": pilot_meta,
        "tasks": tasks,
        "answers_by_task": answers_by_task,
        "marking_rows": marking_rows,
        "human_rows": human_rows,
    }


@app.post("/api/eval/human-marks")
def save_human_marks(payload: SaveHumanMarksRequest) -> dict[str, Any]:
    if len(payload.subtasks) != 5:
        raise HTTPException(status_code=400, detail="Exactly 5 subtask marks are required.")
    human_path = results_dir / "human_marks.csv"
    existing = _read_csv_rows(human_path)
    kept: list[dict[str, str]] = []
    for row in existing:
        if row.get("task_id") == payload.task_id and row.get("answer_id") == payload.answer_id:
            continue
        kept.append(row)

    new_rows: list[dict[str, Any]] = []
    for item in payload.subtasks:
        mark_text = item.human_mark.strip().lower()
        if mark_text not in {"correct", "incorrect", "1", "0", "true", "false"}:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid human_mark {item.human_mark!r}. Use correct/incorrect (or 1/0).",
            )
        new_rows.append(
            {
                "task_id": payload.task_id,
                "concept": payload.concept,
                "answer_id": payload.answer_id,
                "variant_type": payload.variant_type,
                "subtask_id": item.subtask_id,
                "subtask_label": item.subtask_label,
                "student_answer_code": payload.student_answer_code,
                "llm_marker_model": payload.llm_marker_model,
                "llm_mark_for_subtask": item.llm_mark_for_subtask,
                "human_mark": item.human_mark,
                "notes": payload.notes,
            }
        )

    field_order = [
        "task_id",
        "concept",
        "answer_id",
        "variant_type",
        "subtask_id",
        "subtask_label",
        "student_answer_code",
        "llm_marker_model",
        "llm_mark_for_subtask",
        "human_mark",
        "notes",
    ]
    all_rows: list[dict[str, Any]] = [*kept, *new_rows]
    _write_csv_rows(human_path, all_rows, field_order)
    return {"saved_rows": len(new_rows), "file": str(human_path)}


@app.post("/generate-task")
def generate_task(payload: GenerateTaskRequest) -> dict[str, Any]:
    """
    Legacy/general API: behaviour depends on USE_FIXED_DATASET.
    When dynamic, uses QUESTION_GENERATION_PROVIDER (same as POST /api/demo/generate-live-task).
    """
    if USE_FIXED_DATASET:
        task = _select_task_from_bank(payload.concept, payload.difficulty)
        task_store.save_task(task)
        return {
            **task,
            "task_source": "fixed_bank",
            "mode_note": "Sampled from frozen benchmark (USE_FIXED_DATASET=true). Not a fresh LLM generation.",
        }

    provider = get_question_generation_provider()
    task_id = f"dyn-{uuid4()}"
    task = generate_one_task_llm(
        concept=payload.concept,
        difficulty=payload.difficulty,
        task_id=task_id,
    )
    validation = validate_live_task_structure(task, label=task_id)
    task_store.save_task(task)
    return {
        **task,
        "task_source": f"live_{provider}",
        "mode_note": f"Fresh {provider} generation (USE_FIXED_DATASET=false).",
        "validation": validation,
    }


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
        marking_result=json.dumps(payload.marking_result, ensure_ascii=False),
    )
    llm_result = generate_json(prompt, provider_name=FEEDBACK_PROVIDER)
    feedback = str(llm_result.get("feedback", "")).strip()
    if not feedback:
        raise HTTPException(status_code=500, detail="Feedback generation did not return feedback text.")
    return {"feedback": feedback}
