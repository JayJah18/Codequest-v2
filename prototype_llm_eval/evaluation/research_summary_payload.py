"""
Read-only aggregation for GET /api/research-summary (dissertation dashboard).

Does not write files or call LLMs.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


def _bool_mark(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "correct", "yes", "y"}


def _float_cell(row: dict[str, str], key: str) -> float | None:
    t = str(row.get(key, "")).strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_research_summary(
    *,
    results_dir: Path,
    data_dir: Path,
    use_fixed_dataset_for_server: bool | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "file_status": {},
        "dataset": {
            "total_tasks": 0,
            "total_subtasks": 0,
            "total_answers": 0,
            "total_subtask_marks_expected": 0,
        },
        "marking_summary": [],
        "confusion": {},
        "per_concept": {},
        "per_variant": {},
        "speed_estimates": {
            "note": "Qualitative wall-clock notes from pilot runs; not micro-benchmarked.",
            "mistral_marking_full_benchmark": "~fastest (API or local, typical run)",
            "gemini_marking_full_benchmark": "~similar, slightly slower than Mistral in author runs",
            "llama_marking_full_benchmark": "~slowest (~1.5 h author observation for full benchmark on local Ollama)",
            "task_authoring_gemini": "Used for fixed benchmark construction",
        },
        "question_eval": {
            "file_present": False,
            "total": 0,
            "reviewed": 0,
            "appropriate_count": 0,
            "percent_appropriate": None,
            "sample_row": None,
        },
        "feedback_eval": {
            "file_present": False,
            "row_count": 0,
            "avg_relevance": None,
            "avg_clarity": None,
            "avg_usefulness": None,
            "by_model": {},
        },
    }

    fixed_path = data_dir / "fixed_tasks_with_answers.json"
    gen_path = data_dir / "generated_answers.json"
    comp_path = results_dir / "comparison_summary.csv"
    cm_path = results_dir / "confusion_matrix.csv"
    marking_path = results_dir / "marking_results.csv"
    human_path = results_dir / "human_marks.csv"
    q_path = results_dir / "question_generation_review.csv"
    fb_path = results_dir / "feedback_review.csv"

    for label, p in [
        ("comparison_summary", comp_path),
        ("confusion_matrix", cm_path),
        ("marking_results", marking_path),
        ("human_marks", human_path),
        ("question_generation_review", q_path),
        ("feedback_review", fb_path),
    ]:
        out["file_status"][label] = p.exists()

    # Dataset counts
    if fixed_path.exists():
        try:
            tasks = json.loads(fixed_path.read_text(encoding="utf-8"))
            if isinstance(tasks, list):
                out["dataset"]["total_tasks"] = len(tasks)
                st = 0
                for t in tasks:
                    if isinstance(t, dict) and isinstance(t.get("subtasks"), list):
                        st += len(t["subtasks"])
                out["dataset"]["total_subtasks"] = st
        except (json.JSONDecodeError, OSError):
            pass
    if gen_path.exists():
        try:
            data = json.loads(gen_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                n = 0
                for item in data:
                    if isinstance(item, dict) and isinstance(item.get("answers"), list):
                        n += len(item["answers"])
                out["dataset"]["total_answers"] = n
                out["dataset"]["total_subtask_marks_expected"] = n * 5
        except (json.JSONDecodeError, OSError):
            pass

    # comparison_summary.csv
    if comp_path.exists():
        for row in _load_csv(comp_path):
            model = str(row.get("marker_model", "")).strip() or "unknown"
            acc = _float_cell(row, "accuracy")
            f1 = _float_cell(row, "f1")
            tot_raw = str(row.get("total", "")).strip()
            try:
                tot = int(float(tot_raw))
            except (TypeError, ValueError):
                tot = 0
            denom = out["dataset"].get("total_subtask_marks_expected") or 0
            if not denom and out["dataset"]["total_tasks"]:
                denom = out["dataset"]["total_tasks"] * 15
            if not denom:
                denom = 300
            coverage = (tot / denom) if denom else None
            out["marking_summary"].append(
                {
                    "model": model,
                    "accuracy": acc,
                    "f1": f1,
                    "total": tot,
                    "coverage": coverage,
                    "coverage_label": f"{tot} / {denom} subtask marks (overlap with human)",
                }
            )

    # confusion_matrix.csv
    if cm_path.exists():
        for row in _load_csv(cm_path):
            m = str(row.get("marker_model", "")).strip() or "unknown"
            try:
                tp = int(float(row.get("tp_human_correct_llm_correct", 0) or 0))
                tn = int(float(row.get("tn_human_incorrect_llm_incorrect", 0) or 0))
                fp = int(float(row.get("fp_human_incorrect_llm_correct", 0) or 0))
                fn = int(float(row.get("fn_human_correct_llm_incorrect", 0) or 0))
            except (TypeError, ValueError):
                tp = tn = fp = fn = 0
            out["confusion"][m] = {"TP": tp, "TN": tn, "FP": fp, "FN": fn}

    # per_concept / per_variant (same logic as compare_results, read-only)
    if marking_path.exists() and human_path.exists():
        llm_marks_by_model: dict[str, dict[tuple[str, str, str], bool]] = {}
        llm_meta_by_model: dict[str, dict[tuple[str, str, str], str]] = {}
        llm_variant_by_model: dict[str, dict[tuple[str, str, str], str]] = {}
        with marking_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                marker_model = row.get("marker_model", "unknown").strip() or "unknown"
                llm_marks_by_model.setdefault(marker_model, {})
                llm_meta_by_model.setdefault(marker_model, {})
                llm_variant_by_model.setdefault(marker_model, {})
                try:
                    marks = json.loads(row.get("subtask_results_json") or row.get("subtask_results", "[]"))
                except json.JSONDecodeError:
                    marks = []
                for mark in marks:
                    if not isinstance(mark, dict):
                        continue
                    key = (row["task_id"], row["answer_id"], str(mark.get("subtask_id")))
                    llm_marks_by_model[marker_model][key] = bool(mark.get("correct", False))
                    llm_meta_by_model[marker_model][key] = row.get("concept", "unknown")
                    llm_variant_by_model[marker_model][key] = row.get("variant_type", "unknown")

        human_marks: dict[tuple[str, str, str], bool] = {}
        with human_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if not str(row.get("human_mark", "")).strip():
                    continue
                key = (row["task_id"], row["answer_id"], str(row["subtask_id"]))
                human_marks[key] = _bool_mark(row["human_mark"])

        for marker_model, llm_marks in sorted(llm_marks_by_model.items()):
            common_keys = sorted(set(llm_marks).intersection(human_marks))
            if not common_keys:
                out["per_concept"][marker_model] = {}
                out["per_variant"][marker_model] = {}
                continue
            per_concept: dict[str, list[bool]] = {}
            meta = llm_meta_by_model.get(marker_model, {})
            for key in common_keys:
                concept = meta.get(key, "unknown")
                per_concept.setdefault(concept, []).append(llm_marks[key] == human_marks[key])
            out["per_concept"][marker_model] = {
                c: {"accuracy": sum(v) / len(v), "n": len(v), "correct": sum(v)} for c, v in sorted(per_concept.items())
            }
            per_variant: dict[str, list[bool]] = {}
            variant_meta = llm_variant_by_model.get(marker_model, {})
            for key in common_keys:
                variant = variant_meta.get(key, "unknown")
                per_variant.setdefault(variant, []).append(llm_marks[key] == human_marks[key])
            out["per_variant"][marker_model] = {
                v: {"accuracy": sum(vals) / len(vals), "n": len(vals), "correct": sum(vals)}
                for v, vals in sorted(per_variant.items())
            }

    # question_generation_review.csv
    if q_path.exists():
        rows = _load_csv(q_path)
        out["question_eval"]["file_present"] = True
        out["question_eval"]["total"] = len(rows)
        reviewed = 0
        appr = 0
        sample = None
        for r in rows:
            lab = str(r.get("human_question_label", "")).strip().lower()
            if lab:
                reviewed += 1
                if lab == "appropriate":
                    appr += 1
                if sample is None and lab:
                    sample = {k: r.get(k, "") for k in ("task_id", "concept", "human_question_label", "question_text", "notes")}
        out["question_eval"]["reviewed"] = reviewed
        out["question_eval"]["appropriate_count"] = appr
        out["question_eval"]["percent_appropriate"] = (appr / reviewed) if reviewed else None
        out["question_eval"]["sample_row"] = sample or (rows[0] if rows else None)

    # feedback_review.csv
    if fb_path.exists():
        rows = _load_csv(fb_path)
        out["feedback_eval"]["file_present"] = True
        out["feedback_eval"]["row_count"] = len(rows)
        rel: list[float] = []
        clar: list[float] = []
        usef: list[float] = []
        by_model: dict[str, dict[str, list[float]]] = {}
        for r in rows:
            m = str(r.get("feedback_model", "")).strip() or "unknown"
            by_model.setdefault(m, {"relevance": [], "clarity": [], "usefulness": []})
            for col, acc, key in (
                ("relevance_score", rel, "relevance"),
                ("clarity_score", clar, "clarity"),
                ("usefulness_score", usef, "usefulness"),
            ):
                v = _float_cell(r, col)
                if v is not None:
                    acc.append(v)
                    by_model[m][key].append(v)
        out["feedback_eval"]["avg_relevance"] = sum(rel) / len(rel) if rel else None
        out["feedback_eval"]["avg_clarity"] = sum(clar) / len(clar) if clar else None
        out["feedback_eval"]["avg_usefulness"] = sum(usef) / len(usef) if usef else None
        out["feedback_eval"]["by_model"] = {
            m: {
                "avg_relevance": sum(vals["relevance"]) / len(vals["relevance"]) if vals["relevance"] else None,
                "avg_clarity": sum(vals["clarity"]) / len(vals["clarity"]) if vals["clarity"] else None,
                "avg_usefulness": sum(vals["usefulness"]) / len(vals["usefulness"]) if vals["usefulness"] else None,
                "n_scored": max(len(vals["relevance"]), len(vals["clarity"]), len(vals["usefulness"])),
            }
            for m, vals in sorted(by_model.items())
        }

    ufd = use_fixed_dataset_for_server
    if ufd is None:
        ufd = os.getenv("USE_FIXED_DATASET", "false").lower() == "true"
    out["system_modes"] = {
        "server_use_fixed_dataset": ufd,
        "benchmark_type": "Fixed LLM-authored dataset (frozen JSON on disk)",
        "demo_live_generation": "POST /api/demo/generate-live-task — live Gemini; structurally validated",
        "evaluation_scripts": "Read frozen files under data/ and evaluation/results/; reproducible regardless of server env.",
        "marking_comparison": "ready" if comp_path.exists() else "missing comparison_summary.csv",
        "question_review": "ready" if q_path.exists() else "missing question_generation_review.csv",
        "feedback_review": "ready" if fb_path.exists() else "missing feedback_review.csv",
        "human_marks": "ready" if human_path.exists() else "missing human_marks.csv",
        "live_task_structural_checks": "subtask_count, labels, question_text, schema — see validate_live_task_structure",
    }

    return out
