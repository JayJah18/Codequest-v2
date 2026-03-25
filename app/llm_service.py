from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests


OLLAMA_URL = "http://localhost:11434/api/chat"


class LlmError(RuntimeError):
    pass


def _chat(messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> str:
    model = os.getenv("OLLAMA_MODEL", "llama3")
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    if options:
        payload["options"] = options
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
    except requests.RequestException as e:
        raise LlmError(f"Failed to reach Ollama at {OLLAMA_URL}: {e}") from e

    if r.status_code != 200:
        raise LlmError(f"Ollama error {r.status_code}: {r.text}")

    data = r.json()
    content = (data.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise LlmError(f"Ollama returned empty content: {data}")
    return content.strip()


def generate_question_json(concept: str, difficulty: str) -> Dict[str, Any]:
    system = (
        "Generate a single Python exercise as valid JSON only. No markdown, no code fences.\n"
        "Keys: title, question_text, function_name, starter_code, model_answer, unit_tests.\n"
        "Rules: function_name is a Python identifier. starter_code and model_answer define the function; use \\n for newlines in JSON strings (no triple quotes).\n"
        "unit_tests: array of { \"input\": [args...], \"expected\": value }. For one list arg use [[1,2,3]] not [1,2,3]. Exactly 2-3 tests, deterministic.\n"
        "Keep question_text and title brief. One short paragraph max."
    )

    user = (
        f"Concept: {concept}, difficulty: {difficulty}. "
        "Return only the JSON object."
    )

    # Cap tokens and keep temperature low to speed up and keep output compact
    ollama_options = {
        "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "1024")),
        "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
    }

    content = _chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        options=ollama_options,
    )

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise LlmError(
            "LLM returned malformed JSON for question generation. "
            f"Error: {e}. Raw content: {content[:1000]}"
        ) from e

    if not isinstance(data, dict):
        raise LlmError("LLM question JSON must be an object.")
    return data


def generate_feedback_text(
    *,
    question_text: str,
    function_name: str,
    learner_code: str,
    test_results: list[dict[str, Any]],
) -> str:
    system = (
        "You are a supportive programming tutor.\n"
        "Give concise, learner-friendly feedback based on the question, the learner's code, and test results.\n"
        "Do NOT change the pass/fail outcome. Tests are the source of truth.\n"
        "Focus on:\n"
        "- Why tests failed (if any) using the inputs/expected/actual\n"
        "- One or two concrete fixes\n"
        "- If all passed, confirm and suggest a small improvement (readability/edge cases)\n"
    )

    user_payload = {
        "question_text": question_text,
        "function_name": function_name,
        "learner_code": learner_code,
        "test_results": test_results,
    }

    feedback_options = {
        "num_predict": int(os.getenv("OLLAMA_FEEDBACK_NUM_PREDICT", "256")),
        "temperature": float(os.getenv("OLLAMA_FEEDBACK_TEMPERATURE", "0.2")),
    }

    content = _chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        options=feedback_options,
    )
    return content.strip()

