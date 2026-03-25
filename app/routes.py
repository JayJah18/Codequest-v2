from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from .evaluator import EvaluationError, run_unit_tests
from .llm_service import LlmError, generate_feedback_text, generate_question_json
from .models import (
    GenerateQuestionRequest,
    GetFeedbackRequest,
    GetFeedbackResponse,
    QuestionPackage,
    QuestionPackageResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    TestResult,
    UnitTestCase,
)
from .question_store import QuestionStore


router = APIRouter()
store = QuestionStore()


@router.post("/generate-question", response_model=QuestionPackageResponse)
def generate_question(req: GenerateQuestionRequest) -> QuestionPackageResponse:
    concept = (req.concept or "").strip().lower()
    difficulty = (req.difficulty or "").strip().lower()

    allowed_concepts = {"variables", "conditionals", "loops", "strings"}
    if concept not in allowed_concepts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported concept '{concept}'. Allowed: {sorted(allowed_concepts)}",
        )

    allowed_difficulties = {"beginner", "intermediate"}
    if difficulty not in allowed_difficulties:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported difficulty '{difficulty}'. Allowed: {sorted(allowed_difficulties)}",
        )

    try:
        data = generate_question_json(concept=concept, difficulty=difficulty)
    except LlmError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    missing = [k for k in ["title", "question_text", "function_name", "starter_code", "model_answer", "unit_tests"] if k not in data]
    if missing:
        raise HTTPException(status_code=502, detail=f"LLM question JSON missing keys: {missing}")

    try:
        unit_tests = [UnitTestCase.model_validate(t) for t in data["unit_tests"]]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Invalid unit_tests schema: {e}") from e

    if len(unit_tests) < 2:
        raise HTTPException(
            status_code=502,
            detail="Generated package must include at least 2 unit tests.",
        )

    pkg = QuestionPackage(
        question_id=str(uuid4()),
        concept=concept,
        difficulty=difficulty,
        title=str(data["title"]),
        question_text=str(data["question_text"]),
        function_name=str(data["function_name"]),
        starter_code=str(data["starter_code"]),
        model_answer=str(data["model_answer"]),
        unit_tests=unit_tests,
    )

    if not pkg.function_name.isidentifier():
        raise HTTPException(
            status_code=502,
            detail="Generated function_name is not a valid Python identifier.",
        )

    try:
        model_passed, model_results = run_unit_tests(
            learner_code=pkg.model_answer,
            function_name=pkg.function_name,
            unit_tests=[t.model_dump() for t in pkg.unit_tests],
            timeout_seconds=2.0,
        )
    except EvaluationError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Generated model answer could not be executed against generated tests: {e}",
        ) from e

    if not model_passed:
        raise HTTPException(
            status_code=502,
            detail="Generated model answer did not pass generated unit tests.",
        )

    store.put(pkg)
    return QuestionPackageResponse(
        question_id=pkg.question_id,
        concept=pkg.concept,
        difficulty=pkg.difficulty,
        title=pkg.title,
        question_text=pkg.question_text,
        function_name=pkg.function_name,
        starter_code=pkg.starter_code,
        unit_tests=pkg.unit_tests,
    )


@router.post("/submit-answer", response_model=SubmitAnswerResponse)
def submit_answer(req: SubmitAnswerRequest) -> SubmitAnswerResponse:
    pkg = store.get(req.question_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Unknown question_id. Generate a question first.")

    try:
        passed, results = run_unit_tests(
            learner_code=req.learner_code,
            function_name=pkg.function_name,
            unit_tests=[t.model_dump() for t in pkg.unit_tests],
            timeout_seconds=2.0,
        )
    except EvaluationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    test_results = [TestResult.model_validate(r) for r in results]
    passed_count = sum(1 for r in test_results if r.passed)
    failed_count = len(test_results) - passed_count

    return SubmitAnswerResponse(
        passed=bool(passed),
        passed_count=passed_count,
        failed_count=failed_count,
        test_results=test_results,
    )


@router.post("/get-feedback", response_model=GetFeedbackResponse)
def get_feedback(req: GetFeedbackRequest) -> GetFeedbackResponse:
    pkg = store.get(req.question_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Unknown question_id. Generate a question first.")

    try:
        _, results = run_unit_tests(
            learner_code=req.learner_code,
            function_name=pkg.function_name,
            unit_tests=[t.model_dump() for t in pkg.unit_tests],
            timeout_seconds=2.0,
        )
    except EvaluationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        feedback = generate_feedback_text(
            question_text=pkg.question_text,
            function_name=pkg.function_name,
            learner_code=req.learner_code,
            test_results=results,
        )
    except LlmError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return GetFeedbackResponse(feedback=feedback)

