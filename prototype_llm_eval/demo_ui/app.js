(() => {
  const $ = (id) => document.getElementById(id);

  const VARIANT_TITLE = {
    fully_correct: "Fully correct",
    partly_correct: "Partly correct",
    fully_incorrect: "Fully incorrect",
  };

  let currentTask = null;
  let lastMarking = null;
  let currentVariants = [];

  function setProgressionNote() {
    const el = $("progression-note");
    el.innerHTML =
      "Learner progression (unlocks, completed-task state, “next task” for a user) is <strong>not implemented</strong> in this prototype. " +
      "There is no progression API or stored learner profile. For an honest verification page aimed at supervisors, open " +
      "<code>/progress-ui</code>. The progress bar on <code>/eval-ui</code> counts <em>human research labelling</em> only.";
  }

  async function loadServerHint() {
    try {
      const res = await fetch("/api/demo/config");
      if (!res.ok) return;
      const cfg = await res.json();
      const el = $("server-hint");
      const qg = cfg.question_generation_provider || "gemini";
      const qm = cfg.question_generation_model || "";
      if (qg === "gemini" && !cfg.gemini_api_key_configured) {
        el.textContent =
          "GEMINI_API_KEY is not set — live generation with provider \"gemini\" will return 503. Set it in prototype_llm_eval/local.env, or set QUESTION_GENERATION_PROVIDER=llama with Ollama running. Frozen sample still works without a key.";
        el.classList.add("status-warn");
        return;
      }
      el.classList.remove("status-warn");
      const mp = cfg.marking_provider || "gemini";
      const mm = cfg.marking_model || "";
      const fp = cfg.feedback_provider || "gemini";
      const fm = cfg.feedback_model || "";
      const u = cfg.use_fixed_dataset;
      const tail = ` Marking uses "${mp}" (${mm}); feedback uses "${fp}" (${fm}). If those are gemini and the key is invalid, submit will return 502/503 with a clear API-key message.`;
      el.textContent = u
        ? `Live generation uses "${qg}" (${qm}).${tail} USE_FIXED_DATASET=true affects /generate-task only; this page calls /api/demo/generate-live-task.`
        : `Live generation uses "${qg}" (${qm}).${tail} USE_FIXED_DATASET=false: /generate-task uses the same question provider.`;
    } catch {
      /* ignore */
    }
  }

  function setValidationBanner(validation, mode) {
    const el = $("validation-banner");
    if (!mode || !validation) {
      el.classList.add("hidden");
      el.textContent = "";
      el.className = "validation-banner hidden";
      return;
    }
    el.classList.remove("hidden");
    if (validation.ok) {
      el.className = "validation-banner ok";
      el.textContent =
        "Task structure checks passed (same shape as the frozen benchmark: five subtasks, question text, model answer).";
      return;
    }
    el.className = "validation-banner bad";
    el.innerHTML = "";
    const p = document.createElement("p");
    p.textContent = "This generated task did not pass structure checks:";
    el.appendChild(p);
    const ul = document.createElement("ul");
    (validation.checks || []).forEach((c) => {
      if (c.passed) return;
      const li = document.createElement("li");
      li.textContent = `${c.id}: ${c.detail || ""}`;
      ul.appendChild(li);
    });
    if (!ul.children.length) {
      const li = document.createElement("li");
      li.textContent = "See server response for details.";
      ul.appendChild(li);
    }
    el.appendChild(ul);
  }

  function renderVariantButtons() {
    const wrap = $("variant-bar-wrap");
    const bar = $("variant-buttons");
    const noteEl = $("variants-note");
    bar.innerHTML = "";
    noteEl.textContent = "";
    noteEl.classList.add("hidden");

    if (!currentVariants.length) {
      wrap.classList.add("hidden");
      return;
    }
    wrap.classList.remove("hidden");
    currentVariants.forEach((v, idx) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "variant-btn";
      const vt = v.variant_type || "";
      b.textContent = VARIANT_TITLE[vt] || vt || `Variant ${idx + 1}`;
      b.title = v.answer_id || "";
      b.addEventListener("click", () => {
        $("student-code").value = v.code || "";
        bar.querySelectorAll(".variant-btn").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
      });
      bar.appendChild(b);
    });
  }

  function setVariants(variants, note) {
    currentVariants = Array.isArray(variants) ? variants : [];
    renderVariantButtons();
    if (note) {
      $("variants-note").textContent = note;
      $("variants-note").classList.remove("hidden");
    }
  }

  function renderTask(task, sourceLabel, answerVariants, variantsNote, taskKind) {
    currentTask = task;
    lastMarking = null;
    $("task-source").textContent = sourceLabel || "";
    const kindEl = $("task-kind");
    kindEl.classList.remove("hidden", "kind-live", "kind-frozen");
    if (taskKind === "live") {
      kindEl.classList.add("kind-live");
      kindEl.textContent =
        "Task source: live model output (same JSON schema as the benchmark). Not loaded from fixed_tasks_with_answers.json.";
    } else if (taskKind === "frozen") {
      kindEl.classList.add("kind-frozen");
      kindEl.textContent =
        "Task source: fixed benchmark on disk (reproducible evaluation set). Not a fresh Gemini / local LLM generation.";
    } else {
      kindEl.classList.add("hidden");
      kindEl.textContent = "";
    }
    $("task-meta").textContent = `${task.task_id} · ${task.concept} · ${task.difficulty}`;
    $("question-text").textContent = task.question_text || "";
    const ol = $("subtask-list");
    ol.innerHTML = "";
    (task.subtasks || []).forEach((st) => {
      const li = document.createElement("li");
      li.textContent = `${st.subtask_id}: ${st.label}`;
      ol.appendChild(li);
    });

    const ref = $("reference-block");
    const ma = task.model_answer || "";
    if (ma) {
      ref.classList.remove("hidden");
      $("model-answer-pre").textContent = ma;
    } else {
      ref.classList.add("hidden");
      $("model-answer-pre").textContent = "";
    }

    setVariants(answerVariants, variantsNote || "");
    $("student-code").value = "";
    $("marking-summary").textContent = "";
    $("subtask-marks").innerHTML = "";
    $("feedback-text").textContent = "";
    $("status").textContent = "";
  }

  async function generateLive() {
    const concept = $("concept-select").value;
    const difficulty = $("difficulty-select").value;
    $("status").textContent = "Generating task and three example answers (may take a minute)…";
    setValidationBanner(null, null);
    try {
      const res = await fetch("/api/demo/generate-live-task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept, difficulty, include_answer_variants: true }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail || data;
        let msg =
          typeof detail === "string" ? detail : `Request failed (${res.status}). See console.`;
        if ((res.status === 503 || res.status === 502) && typeof detail === "string") {
          msg = detail;
        }
        $("status").textContent = msg;
        if (detail && typeof detail === "object" && detail.validation) {
          setValidationBanner(detail.validation, "bad");
        } else {
          setValidationBanner(null, null);
        }
        console.warn(detail);
        return;
      }
      const task = data.task || data;
      setValidationBanner(data.validation, "ok");
      const src = data.task_source || "live";
      const provider = String(src).replace(/^live_/, "") || "configured provider";
      const note = data.variants_note || "";
      renderTask(
        task,
        `Live-generated task (${src}) — provider: ${provider}`,
        data.answer_variants || [],
        note,
        "live",
      );
      $("task-id-input").value = task.task_id || "";
      const n = (data.answer_variants || []).length;
      $("status").textContent =
        n >= 3
          ? "Ready: task and example learner answers loaded. Pick a variant or write your own, then submit."
          : "Task ready. Example answers missing or partial — write your own code or try a frozen sample.";
    } catch (e) {
      $("status").textContent = `Network error: ${e}`;
    }
  }

  async function loadFrozenSample() {
    const tid = $("task-id-input").value.trim() || null;
    $("status").textContent = "Loading frozen sample…";
    setValidationBanner(null, null);
    const q = tid ? `?task_id=${encodeURIComponent(tid)}` : "";
    const res = await fetch(`/api/demo/task${q}`);
    if (!res.ok) {
      $("status").textContent = `Could not load (${res.status}).`;
      return;
    }
    const data = await res.json();
    const variants = data.answer_variants || [];
    const { task_source, validation, answer_variants, variants_note, ...task } = data;
    renderTask(
      task,
      `Fixed benchmark task (${task_source || "frozen_benchmark_sample"})`,
      variants,
      variants && variants.length ? "" : "No rows in generated_answers.json for this task id.",
      "frozen",
    );
    $("status").textContent =
      variants.length >= 3
        ? "Loaded from fixed_tasks_with_answers.json + example variants from generated_answers.json."
        : "Loaded task; add or regenerate generated_answers.json for full variant buttons.";
  }

  function renderMarking(data) {
    lastMarking = data;
    const max = data.max_score ?? "—";
    const score = data.overall_score ?? "—";
    const stars = data.star_rating ?? "—";
    $("marking-summary").textContent = `Overall score: ${score} / ${max} · Star rating: ${stars}`;
    const ul = $("subtask-marks");
    ul.innerHTML = "";
    (data.subtask_results || []).forEach((r) => {
      const li = document.createElement("li");
      const badge = document.createElement("span");
      const ok = !!r.correct;
      badge.className = `badge ${ok ? "ok" : "bad"}`;
      badge.textContent = ok ? "Correct" : "Incorrect";
      const span = document.createElement("span");
      span.textContent = `${r.subtask_id}: ${r.reason || ""}`;
      li.appendChild(badge);
      li.appendChild(span);
      ul.appendChild(li);
    });
  }

  $("btn-generate-live").addEventListener("click", () => generateLive());
  $("btn-load-fixed").addEventListener("click", () => loadFrozenSample());

  $("btn-submit").addEventListener("click", async () => {
    if (!currentTask) {
      $("status").textContent = "Generate a live task or load a frozen sample first.";
      return;
    }
    const code = $("student-code").value;
    if (!code.trim()) {
      $("status").textContent = "Enter some code before submitting.";
      return;
    }
    $("status").textContent = "Marking…";
    $("feedback-text").textContent = "";
    try {
      const mRes = await fetch("/api/demo/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: currentTask.task_id, student_answer: code }),
      });
      if (!mRes.ok) {
        const err = await mRes.json().catch(() => ({}));
        $("status").textContent = err.detail || `Marking failed (${mRes.status}).`;
        return;
      }
      const marking = await mRes.json();
      renderMarking(marking);
      $("status").textContent = "Fetching feedback…";
      const fRes = await fetch("/api/demo/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: currentTask.task_id,
          student_answer: code,
          marking_result: marking,
        }),
      });
      if (!fRes.ok) {
        const err = await fRes.json().catch(() => ({}));
        $("status").textContent = err.detail || `Feedback failed (${fRes.status}).`;
        return;
      }
      const fb = await fRes.json();
      $("feedback-text").textContent = fb.feedback || "";
      $("status").textContent = "Done.";
    } catch (e) {
      $("status").textContent = `Network error: ${e}`;
    }
  });

  setProgressionNote();
  loadServerHint();
  loadFrozenSample();
})();
