from __future__ import annotations

import multiprocessing as mp
from typing import Any, Dict, Tuple


class EvaluationError(RuntimeError):
    pass


def _safe_exec_and_get_function(learner_code: str, function_name: str) -> Any:
    # Minimal prototype assumptions: trusted-ish environment, but we still isolate in a process
    # and restrict obvious builtins. This is NOT a full sandbox.
    allowed_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }

    env: Dict[str, Any] = {"__builtins__": allowed_builtins}
    exec(learner_code, env, env)
    fn = env.get(function_name)
    if not callable(fn):
        raise EvaluationError(f"Function '{function_name}' was not found or is not callable.")
    return fn


def _make_jsonable(value: Any) -> Any:
    # Best-effort for returning "actual" values to frontend.
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_make_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _make_jsonable(v) for k, v in value.items()}
    return repr(value)


def _worker(
    learner_code: str,
    function_name: str,
    unit_tests: list[dict[str, Any]],
    q: mp.Queue,
) -> None:
    try:
        fn = _safe_exec_and_get_function(learner_code, function_name)
        results = []
        for t in unit_tests:
            inputs = t.get("input") or []
            expected = t.get("expected")
            try:
                actual = fn(*inputs)
                passed = actual == expected
                results.append(
                    {
                        "input": inputs,
                        "expected": expected,
                        "actual": _make_jsonable(actual),
                        "passed": bool(passed),
                    }
                )
            except Exception as e:  # noqa: BLE001 - prototype: surface exception as actual
                results.append(
                    {
                        "input": inputs,
                        "expected": expected,
                        "actual": f"Exception: {type(e).__name__}: {e}",
                        "passed": False,
                    }
                )
        q.put(("ok", results))
    except Exception as e:
        q.put(("error", f"{type(e).__name__}: {e}"))


def run_unit_tests(
    *,
    learner_code: str,
    function_name: str,
    unit_tests: list[dict[str, Any]],
    timeout_seconds: float = 2.0,
) -> Tuple[bool, list[dict[str, Any]]]:
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    p = ctx.Process(target=_worker, args=(learner_code, function_name, unit_tests, q))
    p.start()
    p.join(timeout_seconds)

    if p.is_alive():
        p.terminate()
        p.join(1)
        raise EvaluationError("Test execution timed out (possible infinite loop).")

    try:
        status, payload = q.get_nowait()
    except Exception as e:
        raise EvaluationError(f"No test results returned: {e}") from e

    if status == "error":
        raise EvaluationError(str(payload))

    results = payload
    passed = all(bool(r.get("passed")) for r in results)
    return passed, results

