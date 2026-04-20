"""
Write a reproducible validation report for dissertation methodology.

Run: python -m prototype_llm_eval.evaluation.generate_validation_report
Outputs:
  evaluation/results/validation_report.json
  evaluation/results/validation_report.txt
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prototype_llm_eval.backend.dataset_validation import (
    EXPECTED_TASK_COUNT,
    EXPECTED_TOTAL_SUBTASKS,
    assert_valid_dataset,
    load_json_task_list,
)
from prototype_llm_eval.evaluation.pilot_filters import load_generated_answers_by_task, validate_generated_answers_align


def _prompt_version(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    first = path.read_text(encoding="utf-8").splitlines()[0].strip()
    return first if first.startswith("PROMPT_VERSION:") else fallback


def _read_marking_models(path: Path) -> tuple[list[str], list[str], list[str]]:
    if not path.exists():
        return [], [], []
    models: list[str] = []
    actuals: list[str] = []
    versions: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            m = str(row.get("marker_model", "")).strip()
            if m:
                models.append(m)
            a = str(row.get("actual_model_name", "")).strip()
            if a:
                actuals.append(a)
            v = str(row.get("marking_prompt_version", "")).strip()
            if v:
                versions.append(v)
    return models, actuals, versions


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    data_dir = base / "data"
    results_dir = base / "evaluation" / "results"
    prompts_dir = base / "prompts"
    fixed_path = data_dir / "fixed_tasks_with_answers.json"
    gen_path = data_dir / "generated_answers.json"
    marking_path = results_dir / "marking_results.csv"
    human_path = results_dir / "human_marks.csv"

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment_hints": {
            "GEMINI_MODEL": os.getenv("GEMINI_MODEL", ""),
            "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", ""),
            "MISTRAL_MODEL": os.getenv("MISTRAL_MODEL", ""),
        },
    }

    fixed_ok = False
    fixed_errors: list[str] = []
    n_tasks = 0
    n_subtasks = 0
    try:
        tasks = load_json_task_list(fixed_path)
        assert_valid_dataset(tasks)
        fixed_ok = True
        n_tasks = len(tasks)
        n_subtasks = sum(len(t.get("subtasks", [])) if isinstance(t.get("subtasks"), list) else 0 for t in tasks)
    except Exception as exc:  # noqa: BLE001
        fixed_errors.append(str(exc))

    report["fixed_dataset"] = {
        "path": str(fixed_path),
        "valid": fixed_ok,
        "errors": fixed_errors,
        "total_tasks": n_tasks,
        "total_subtasks": n_subtasks,
        "expected_tasks": EXPECTED_TASK_COUNT,
        "expected_subtasks_total": EXPECTED_TOTAL_SUBTASKS,
    }

    variants_ok = False
    variant_errors: list[str] = []
    n_answer_rows = 0
    answers_by_task: dict[str, list[dict[str, Any]]] = {}
    if fixed_ok:
        try:
            answers_by_task = load_generated_answers_by_task(data_dir)
            align = validate_generated_answers_align(tasks, answers_by_task)
            variant_errors = align
            variants_ok = len(align) == 0
            for _tid, ans in answers_by_task.items():
                n_answer_rows += len(ans)
        except Exception as exc:  # noqa: BLE001
            variant_errors.append(str(exc))

    report["answer_variants"] = {
        "path": str(gen_path),
        "total_answer_rows": n_answer_rows,
        "expected_per_task": 3,
        "alignment_ok": variants_ok,
        "alignment_errors": variant_errors,
    }

    marking_rows = 0
    if marking_path.exists():
        with marking_path.open("r", encoding="utf-8", newline="") as f:
            marking_rows = sum(1 for _ in csv.DictReader(f))

    mm, actuals, mvers = _read_marking_models(marking_path)
    report["marking_results"] = {
        "path": str(marking_path),
        "row_count": marking_rows,
        "marker_model_counts": dict(Counter(mm)),
        "actual_model_name_unique": sorted(set(actuals)),
        "marking_prompt_version_unique": sorted(set(mvers)),
    }

    human_rows = 0
    human_filled = 0
    if human_path.exists():
        with human_path.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                human_rows += 1
                if str(row.get("human_mark", "")).strip():
                    human_filled += 1
    report["human_marks"] = {
        "path": str(human_path),
        "row_count": human_rows,
        "rows_with_human_mark": human_filled,
    }

    report["prompt_versions"] = {
        "task_generation": _prompt_version(prompts_dir / "task_generation_prompt.txt", "missing"),
        "marking": _prompt_version(prompts_dir / "marking_prompt.txt", "missing"),
        "feedback": _prompt_version(prompts_dir / "feedback_prompt.txt", "missing"),
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "validation_report.json"
    txt_path = results_dir / "validation_report.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "VALIDATION REPORT (prototype_llm_eval)",
        f"Generated: {report['generated_at_utc']}",
        "",
        "Fixed dataset",
        f"  valid: {fixed_ok}",
        f"  tasks: {n_tasks} (expected {EXPECTED_TASK_COUNT})",
        f"  subtasks total: {n_subtasks} (expected {EXPECTED_TOTAL_SUBTASKS})",
        "",
        "Answer variants",
        f"  alignment_ok: {variants_ok}",
        f"  answer row count (sum over tasks): {n_answer_rows}",
        "",
        "Marking results CSV",
        f"  rows: {marking_rows}",
        f"  marker_model counts: {report['marking_results']['marker_model_counts']}",
        f"  actual_model_name (unique): {report['marking_results']['actual_model_name_unique']}",
        "",
        "Human marks CSV",
        f"  rows: {human_rows}",
        f"  rows with human_mark filled: {human_filled}",
        "",
        "Prompt versions",
        f"  task_generation: {report['prompt_versions']['task_generation']}",
        f"  marking:         {report['prompt_versions']['marking']}",
        f"  feedback:        {report['prompt_versions']['feedback']}",
    ]
    if fixed_errors:
        lines.extend(["", "Fixed dataset errors:", *[f"  - {e}" for e in fixed_errors]])
    if variant_errors:
        lines.extend(["", "Variant alignment errors:", *[f"  - {e}" for e in variant_errors]])

    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()
