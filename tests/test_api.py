from __future__ import annotations

from fastapi.testclient import TestClient

import app.routes as routes
from main import app


client = TestClient(app)


def _good_llm_package() -> dict:
    return {
        "title": "Add two numbers",
        "question_text": "Write a function that returns the sum of two integers a and b.",
        "function_name": "add_two",
        "starter_code": "def add_two(a, b):\n    # TODO\n    return 0\n",
        "model_answer": "def add_two(a, b):\n    return a + b\n",
        "unit_tests": [
            {"input": [1, 2], "expected": 3},
            {"input": [-5, 10], "expected": 5},
        ],
    }


def setup_function() -> None:
    # Ensure a clean in-memory store for every test
    routes.store.clear()


def test_generate_question_rejects_incomplete_llm_json(monkeypatch) -> None:
    def fake_generate_question_json(*, concept: str, difficulty: str) -> dict:
        return {"title": "Missing keys"}

    monkeypatch.setattr(routes, "generate_question_json", fake_generate_question_json)

    r = client.post("/generate-question", json={"concept": "loops", "difficulty": "beginner"})
    assert r.status_code == 502
    assert "missing keys" in r.json()["detail"].lower()


def test_generate_question_rejects_model_answer_if_it_fails_own_tests(monkeypatch) -> None:
    bad = _good_llm_package()
    bad["model_answer"] = "def add_two(a, b):\n    return a\n"

    def fake_generate_question_json(*, concept: str, difficulty: str) -> dict:
        return bad

    monkeypatch.setattr(routes, "generate_question_json", fake_generate_question_json)

    r = client.post("/generate-question", json={"concept": "variables", "difficulty": "beginner"})
    assert r.status_code == 502
    assert "did not pass" in r.json()["detail"].lower()


def test_generate_question_success_hides_model_answer(monkeypatch) -> None:
    def fake_generate_question_json(*, concept: str, difficulty: str) -> dict:
        return _good_llm_package()

    monkeypatch.setattr(routes, "generate_question_json", fake_generate_question_json)

    r = client.post("/generate-question", json={"concept": "variables", "difficulty": "beginner"})
    assert r.status_code == 200
    body = r.json()
    assert "model_answer" not in body
    assert body["function_name"] == "add_two"
    assert len(body["unit_tests"]) >= 2


def test_get_feedback_reruns_tests_server_side_and_works_when_failing(monkeypatch) -> None:
    # Generate/store a question first
    monkeypatch.setattr(routes, "generate_question_json", lambda **kwargs: _good_llm_package())
    gen = client.post("/generate-question", json={"concept": "variables", "difficulty": "beginner"})
    assert gen.status_code == 200
    qid = gen.json()["question_id"]

    calls = {"run_unit_tests": 0, "feedback": 0}

    def fake_run_unit_tests(*, learner_code: str, function_name: str, unit_tests: list[dict], timeout_seconds: float):
        calls["run_unit_tests"] += 1
        assert function_name == "add_two"
        assert isinstance(unit_tests, list) and len(unit_tests) >= 2
        # Force a deterministic failing result to prove feedback still works when tests fail
        return False, [
            {"input": [1, 2], "expected": 3, "actual": 1, "passed": False},
            {"input": [-5, 10], "expected": 5, "actual": 5, "passed": True},
        ]

    def fake_generate_feedback_text(*, question_text: str, function_name: str, learner_code: str, test_results: list[dict]):
        calls["feedback"] += 1
        # Ensure feedback is grounded in backend-computed results
        assert any(r.get("passed") is False for r in test_results)
        return "Dummy feedback based on real server-side test results."

    monkeypatch.setattr(routes, "run_unit_tests", fake_run_unit_tests)
    monkeypatch.setattr(routes, "generate_feedback_text", fake_generate_feedback_text)

    r = client.post(
        "/get-feedback",
        json={"question_id": qid, "learner_code": "def add_two(a, b):\n    return a\n"},
    )
    assert r.status_code == 200
    assert "feedback" in r.json()
    assert "server-side" in r.json()["feedback"].lower()
    assert calls["run_unit_tests"] == 1
    assert calls["feedback"] == 1

