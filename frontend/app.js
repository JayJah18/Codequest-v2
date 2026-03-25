let currentQuestionId = null;
let currentFunctionName = null;
let lastTestResults = null;

function $(id) {
  return document.getElementById(id);
}

function show(el, on) {
  el.classList.toggle("hidden", !on);
}

function setError(id, msg) {
  const el = $(id);
  if (!msg) {
    el.textContent = "";
    show(el, false);
    return;
  }
  el.textContent = msg;
  show(el, true);
}

function renderTests(results) {
  const container = $("testResults");
  container.innerHTML = "";
  for (const r of results) {
    const div = document.createElement("div");
    div.className = "test " + (r.passed ? "pass" : "fail");
    div.innerHTML = `
      <div><strong>${r.passed ? "PASS" : "FAIL"}</strong></div>
      <div><strong>input:</strong> <code>${escapeHtml(JSON.stringify(r.input))}</code></div>
      <div><strong>expected:</strong> <code>${escapeHtml(JSON.stringify(r.expected))}</code></div>
      <div><strong>actual:</strong> <code>${escapeHtml(JSON.stringify(r.actual))}</code></div>
    `;
    container.appendChild(div);
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch { /* keep raw */ }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : text;
    throw new Error(detail);
  }
  return data;
}

async function onGenerate() {
  setError("genError", "");
  setError("testError", "");
  setError("feedbackError", "");
  $("feedback").textContent = "Run tests first, then click “Get Feedback”.";
  lastTestResults = null;

  const concept = $("concept").value;
  const difficulty = $("difficulty").value;

  $("btnGenerate").disabled = true;
  try {
    const pkg = await apiPost("/generate-question", { concept, difficulty });
    currentQuestionId = pkg.question_id;
    currentFunctionName = pkg.function_name;

    $("title").textContent = pkg.title;
    $("functionName").textContent = pkg.function_name;
    $("questionId").textContent = pkg.question_id;
    $("questionText").textContent = pkg.question_text;
    $("code").value = pkg.starter_code || "";

    $("testSummary").textContent = "";
    $("testResults").innerHTML = "";
  } catch (e) {
    setError("genError", String(e.message || e));
  } finally {
    $("btnGenerate").disabled = false;
  }
}

async function onRunTests() {
  setError("testError", "");
  setError("feedbackError", "");
  $("feedback").textContent = "Click “Get Feedback” to ask the LLM for coaching based on these results.";

  if (!currentQuestionId) {
    setError("testError", "Generate a question first.");
    return;
  }

  const learner_code = $("code").value;
  $("btnRunTests").disabled = true;
  try {
    const resp = await apiPost("/submit-answer", { question_id: currentQuestionId, learner_code });
    lastTestResults = resp.test_results;
    renderTests(resp.test_results);
    $("testSummary").textContent = resp.passed
      ? `All tests passed (${resp.passed_count}/${resp.passed_count + resp.failed_count}).`
      : `Some tests failed (${resp.passed_count}/${resp.passed_count + resp.failed_count} passed).`;
  } catch (e) {
    setError("testError", String(e.message || e));
  } finally {
    $("btnRunTests").disabled = false;
  }
}

async function onFeedback() {
  setError("feedbackError", "");
  if (!currentQuestionId) {
    setError("feedbackError", "Generate a question first.");
    return;
  }

  const learner_code = $("code").value;
  $("btnFeedback").disabled = true;
  try {
    const resp = await apiPost("/get-feedback", {
      question_id: currentQuestionId,
      learner_code,
    });
    $("feedback").textContent = resp.feedback || "";
  } catch (e) {
    setError("feedbackError", String(e.message || e));
  } finally {
    $("btnFeedback").disabled = false;
  }
}

function init() {
  $("btnGenerate").addEventListener("click", onGenerate);
  $("btnRunTests").addEventListener("click", onRunTests);
  $("btnFeedback").addEventListener("click", onFeedback);
}

init();

