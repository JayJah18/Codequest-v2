from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Concept = Literal["variables", "conditionals", "loops", "strings"]
Difficulty = Literal["beginner", "intermediate"]


class GenerateQuestionRequest(BaseModel):
    concept: str
    difficulty: str


class UnitTestCase(BaseModel):
    input: list[Any] = Field(default_factory=list)
    expected: Any


class QuestionPackage(BaseModel):
    """Full package stored server-side (includes model_answer)."""
    question_id: str
    concept: str
    difficulty: str
    title: str
    question_text: str
    function_name: str
    starter_code: str
    model_answer: str
    unit_tests: list[UnitTestCase]


class QuestionPackageResponse(BaseModel):
    """Package returned to frontend (model_answer excluded)."""
    question_id: str
    concept: str
    difficulty: str
    title: str
    question_text: str
    function_name: str
    starter_code: str
    unit_tests: list[UnitTestCase]


class SubmitAnswerRequest(BaseModel):
    question_id: str
    learner_code: str


class TestResult(BaseModel):
    input: list[Any]
    expected: Any
    actual: Any
    passed: bool


class SubmitAnswerResponse(BaseModel):
    passed: bool
    passed_count: int
    failed_count: int
    test_results: list[TestResult]


class GetFeedbackRequest(BaseModel):
    question_id: str
    learner_code: str


class GetFeedbackResponse(BaseModel):
    feedback: str

