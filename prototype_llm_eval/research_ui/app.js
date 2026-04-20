function fmtPct(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return (100 * x).toFixed(1) + "%";
}

function fmtNum(x, d = 3) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return Number(x).toFixed(d);
}

function el(tag, attrs = {}, children = []) {
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "className") n.className = v;
    else if (k === "textContent") n.textContent = v;
    else n.setAttribute(k, v);
  });
  children.forEach((c) => n.appendChild(c));
  return n;
}

function showSection(id, show) {
  const s = document.getElementById(id);
  if (s) s.classList.toggle("hidden", !show);
}

const qrState = {
  tasks: [],
  index: 0,
  summary: {},
  file: "",
};
let qrListenersBound = false;

function fmtQrPct(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return (100 * x).toFixed(1) + "%";
}

function currentQrTask() {
  return qrState.tasks[qrState.index] || null;
}

function renderQrSummary() {
  const host = document.getElementById("qr-summary");
  if (!host) return;
  const s = qrState.summary || {};
  const pc = s.per_concept || {};
  host.innerHTML = "";
  const p = el("p", {
    className: "sub",
    textContent: `Review file: ${qrState.file || "evaluation/results/question_generation_review.csv"}`,
  });
  host.appendChild(p);
  host.appendChild(
    el("p", {
      className: "sub",
      textContent: `Total tasks: ${s.total_tasks ?? qrState.tasks.length}. Reviewed (labelled): ${s.reviewed ?? 0}. Appropriate: ${
        s.appropriate_count ?? 0
      }. % appropriate (of reviewed): ${fmtQrPct(s.percent_appropriate)}.`,
    })
  );
  const keys = Object.keys(pc);
  if (keys.length) {
    const t = el("table", {}, [
      el("thead", {}, [
        el("tr", {}, ["Concept", "Tasks", "Reviewed", "Appropriate", "% appr. (reviewed)"].map((h) => el("th", { textContent: h }))),
      ]),
    ]);
    const tb = el("tbody", {}, []);
    keys
      .sort()
      .forEach((k) => {
        const v = pc[k] || {};
        const n = v.n ?? 0;
        const rev = v.reviewed ?? 0;
        const ok = v.appropriate ?? 0;
        const pct = rev ? ok / rev : null;
        tb.appendChild(
          el("tr", {}, [
            el("td", { textContent: k }),
            el("td", { textContent: String(n) }),
            el("td", { textContent: String(rev) }),
            el("td", { textContent: String(ok) }),
            el("td", { textContent: fmtQrPct(pct) }),
          ])
        );
      });
    t.appendChild(tb);
    host.appendChild(t);
  }
}

function renderQrDetail() {
  const host = document.getElementById("qr-detail");
  if (!host) return;
  const t = currentQrTask();
  host.innerHTML = "";
  if (!t) {
    host.appendChild(el("p", { className: "sub", textContent: "No task loaded." }));
    return;
  }
  host.appendChild(
    el("p", {
      className: "qr-meta",
      textContent: `${t.task_id} · ${t.concept} · ${t.difficulty} · model_answer: ${t.has_model_answer ? "present" : "missing"}`,
    })
  );
  host.appendChild(el("h3", { textContent: "Question" }));
  host.appendChild(el("p", { className: "qtext", textContent: t.question_text || "" }));
  host.appendChild(el("h3", { textContent: "Subtasks (5)" }));
  const ol = el("ol", {}, []);
  (t.subtasks || []).forEach((st) => {
    const id = st && st.subtask_id != null ? String(st.subtask_id) : "";
    const lab = st && st.label != null ? String(st.label) : "";
    ol.appendChild(el("li", { textContent: `${id}: ${lab}` }));
  });
  host.appendChild(ol);
}

function syncQrFormFromTask() {
  const t = currentQrTask();
  const label = document.getElementById("qr-label");
  const notes = document.getElementById("qr-notes");
  const lf = document.getElementById("qr-level-fit");
  const tf = document.getElementById("qr-topic-fit");
  const cl = document.getElementById("qr-clarity");
  if (!t || !label || !notes || !lf || !tf || !cl) return;
  const hl = String(t.human_question_label || "").toLowerCase();
  label.value = hl === "appropriate" || hl === "inappropriate" ? hl : "";
  notes.value = t.notes || "";
  lf.value = t.level_fit || "";
  tf.value = t.topic_fit || "";
  cl.value = t.clarity || "";
}

function populateQrSelect() {
  const sel = document.getElementById("qr-task-select");
  if (!sel) return;
  sel.innerHTML = "";
  qrState.tasks.forEach((t, idx) => {
    const opt = document.createElement("option");
    opt.value = String(idx);
    const lab = String(t.human_question_label || "").toLowerCase();
    const tag = lab === "appropriate" || lab === "inappropriate" ? ` · ${lab}` : "";
    opt.textContent = `${t.task_id} · ${t.concept}${tag}`;
    sel.appendChild(opt);
  });
  sel.value = String(qrState.index);
}

function renderQrAll() {
  renderQrSummary();
  populateQrSelect();
  renderQrDetail();
  syncQrFormFromTask();
}

async function refreshQuestionReview() {
  const res = await fetch("/api/research/question-review");
  if (!res.ok) throw new Error(`question-review ${res.status}`);
  const data = await res.json();
  qrState.tasks = data.tasks || [];
  qrState.summary = data.summary || {};
  qrState.file = data.file || "";
  if (qrState.index >= qrState.tasks.length) qrState.index = Math.max(0, qrState.tasks.length - 1);
  renderQrAll();
}

function initQuestionReviewPanel() {
  const sec = document.getElementById("sec-question-review");
  const st = document.getElementById("qr-status");
  if (!sec) return;
  if (qrListenersBound) return;
  qrListenersBound = true;

  const sel = document.getElementById("qr-task-select");
  const prev = document.getElementById("qr-prev");
  const next = document.getElementById("qr-next");
  const save = document.getElementById("qr-save");

  if (sel) {
    sel.addEventListener("change", () => {
      const idx = Number(sel.value);
      if (!Number.isNaN(idx)) {
        qrState.index = idx;
        renderQrDetail();
        syncQrFormFromTask();
      }
    });
  }
  if (prev) {
    prev.addEventListener("click", () => {
      qrState.index = Math.max(0, qrState.index - 1);
      renderQrAll();
    });
  }
  if (next) {
    next.addEventListener("click", () => {
      qrState.index = Math.min(qrState.tasks.length - 1, qrState.index + 1);
      renderQrAll();
    });
  }
  if (save) {
    save.addEventListener("click", async () => {
      const t = currentQrTask();
      if (!t) return;
      const labelEl = document.getElementById("qr-label");
      const label = (labelEl && labelEl.value) || "";
      if (!label) {
        if (st) st.textContent = "Choose appropriate or inappropriate before saving.";
        return;
      }
      if (st) st.textContent = "Saving…";
      try {
        const res = await fetch("/api/research/question-review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_id: t.task_id,
            human_question_label: label,
            notes: document.getElementById("qr-notes")?.value || "",
            level_fit: document.getElementById("qr-level-fit")?.value || "",
            topic_fit: document.getElementById("qr-topic-fit")?.value || "",
            clarity: document.getElementById("qr-clarity")?.value || "",
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `save failed (${res.status})`);
        await refreshQuestionReview();
        if (st) st.textContent = `Saved → ${data.path || "question_generation_review.csv"}`;
      } catch (e) {
        if (st) st.textContent = `Save failed: ${e}`;
      }
    });
  }
}

async function main() {
  const status = document.getElementById("load-status");
  let data;
  try {
    const res = await fetch("/api/research-summary");
    if (!res.ok) {
      status.textContent = "Failed to load summary: " + res.status;
      return;
    }
    data = await res.json();
  } catch (e) {
    status.textContent = "Network error: " + e;
    return;
  }
  status.textContent = "";
  status.classList.add("hidden");

  try {
    await refreshQuestionReview();
    showSection("sec-question-review", true);
    initQuestionReviewPanel();
  } catch (e) {
    showSection("sec-question-review", true);
    const st = document.getElementById("qr-status");
    if (st) st.textContent = `Could not load question review data: ${e}`;
    initQuestionReviewPanel();
  }

  const modes = data.system_modes;
  if (modes) {
    document.getElementById("modes-pre").textContent = JSON.stringify(modes, null, 2);
    showSection("sec-modes", true);
  }

  // Files
  const fs = data.file_status || {};
  const ul = document.getElementById("file-status");
  ul.innerHTML = "";
  Object.entries(fs).forEach(([k, ok]) => {
    ul.appendChild(el("li", { textContent: `${ok ? "OK" : "missing"} — ${k}` }));
  });
  showSection("sec-files", true);

  // Dataset
  const ds = data.dataset || {};
  const db = document.getElementById("dataset-body");
  db.innerHTML = "";
  [
    ["Total tasks", ds.total_tasks],
    ["Subtasks per benchmark (rubric rows)", ds.total_subtasks],
    ["Total answer variants", ds.total_answers],
    ["Expected subtask marks (answers × 5)", ds.total_subtask_marks_expected],
  ].forEach(([a, b]) => {
    db.appendChild(el("tr", {}, [el("td", { textContent: a }), el("td", { textContent: String(b) })]));
  });
  showSection("sec-dataset", true);

  // Marking table
  const mb = document.getElementById("marking-body");
  mb.innerHTML = "";
  (data.marking_summary || []).forEach((row) => {
    mb.appendChild(
      el("tr", {}, [
        el("td", { textContent: row.model }),
        el("td", { textContent: fmtNum(row.accuracy) }),
        el("td", { textContent: fmtNum(row.f1) }),
        el("td", { textContent: String(row.total ?? "—") }),
        el("td", { textContent: fmtPct(row.coverage) }),
      ])
    );
  });
  showSection("sec-marking", (data.marking_summary || []).length > 0);

  // Confusion
  const cw = document.getElementById("confusion-wrap");
  cw.innerHTML = "";
  const conf = data.confusion || {};
  const ckeys = Object.keys(conf);
  if (ckeys.length) {
    ckeys.forEach((model) => {
      const b = el("div", { className: "model-block" });
      b.appendChild(el("h3", { textContent: model }));
      const t = el("table", {}, [
        el("thead", {}, [
          el("tr", {}, ["TP", "TN", "FP", "FN"].map((h) => el("th", { textContent: h }))),
        ]),
      ]);
      const tbody = el("tbody", {}, []);
      const c = conf[model] || {};
      tbody.appendChild(
        el("tr", {}, [c.TP, c.TN, c.FP, c.FN].map((v) => el("td", { textContent: String(v ?? "—") })))
      );
      t.appendChild(tbody);
      b.appendChild(t);
      cw.appendChild(b);
    });
  }
  showSection("sec-confusion", ckeys.length > 0);

  // Per concept
  const conceptWrap = document.getElementById("concept-wrap");
  conceptWrap.innerHTML = "";
  const pc = data.per_concept || {};
  const pcm = Object.keys(pc);
  if (pcm.length) {
    pcm.forEach((model) => {
      const b = el("div", { className: "model-block" });
      b.appendChild(el("h3", { textContent: model }));
      const t = el("table", {}, [
        el("thead", {}, [
          el("tr", {}, ["Concept", "Accuracy", "n", "correct"].map((h) => el("th", { textContent: h }))),
        ]),
      ]);
      const tb = el("tbody", {}, []);
      Object.entries(pc[model] || {}).forEach(([concept, v]) => {
        tb.appendChild(
          el("tr", {}, [
            el("td", { textContent: concept }),
            el("td", { textContent: fmtNum(v.accuracy) }),
            el("td", { textContent: String(v.n) }),
            el("td", { textContent: String(v.correct) }),
          ])
        );
      });
      t.appendChild(tb);
      b.appendChild(t);
      conceptWrap.appendChild(b);
    });
  }
  showSection("sec-concept", pcm.length > 0);

  // Per variant
  const varWrap = document.getElementById("variant-wrap");
  varWrap.innerHTML = "";
  const pv = data.per_variant || {};
  const pvm = Object.keys(pv);
  if (pvm.length) {
    pvm.forEach((model) => {
      const b = el("div", { className: "model-block" });
      b.appendChild(el("h3", { textContent: model }));
      const t = el("table", {}, [
        el("thead", {}, [
          el("tr", {}, ["Variant", "Accuracy", "n", "correct"].map((h) => el("th", { textContent: h }))),
        ]),
      ]);
      const tb = el("tbody", {}, []);
      Object.entries(pv[model] || {}).forEach(([variant, v]) => {
        tb.appendChild(
          el("tr", {}, [
            el("td", { textContent: variant }),
            el("td", { textContent: fmtNum(v.accuracy) }),
            el("td", { textContent: String(v.n) }),
            el("td", { textContent: String(v.correct) }),
          ])
        );
      });
      t.appendChild(tb);
      b.appendChild(t);
      varWrap.appendChild(b);
    });
  }
  showSection("sec-variant", pvm.length > 0);

  // Question eval
  const qb = document.getElementById("question-body");
  const qe = data.question_eval || {};
  if (qe.file_present) {
    const pct = qe.percent_appropriate != null ? fmtPct(qe.percent_appropriate) : "— (no labels yet)";
    qb.innerHTML = "";
    qb.appendChild(
      el("p", {
        textContent: `Rows: ${qe.total}. Reviewed: ${qe.reviewed}. Appropriate: ${qe.appropriate_count}. % appropriate: ${pct}`,
      })
    );
    if (qe.sample_row) {
      qb.appendChild(el("p", { textContent: "Sample row:", className: "sub" }));
      qb.appendChild(el("pre", { className: "sample", textContent: JSON.stringify(qe.sample_row, null, 2) }));
    }
    showSection("sec-question", true);
  } else {
    showSection("sec-question", false);
  }

  // Feedback
  const fb = document.getElementById("feedback-body");
  const fe = data.feedback_eval || {};
  if (fe.file_present) {
    fb.innerHTML = "";
    fb.appendChild(
      el("p", {
        textContent: `Rows: ${fe.row_count}. Overall avg relevance / clarity / usefulness: ${fmtNum(fe.avg_relevance, 2)} / ${fmtNum(fe.avg_clarity, 2)} / ${fmtNum(fe.avg_usefulness, 2)}`,
      })
    );
    const by = fe.by_model || {};
    if (Object.keys(by).length) {
      fb.appendChild(el("p", { textContent: "By model:", className: "sub" }));
      const t = el("table", {}, [
        el("thead", {}, [
          el("tr", {}, ["Model", "Avg relevance", "Avg clarity", "Avg usefulness", "n scored"].map((h) => el("th", { textContent: h }))),
        ]),
      ]);
      const tb = el("tbody", {}, []);
      Object.entries(by).forEach(([m, v]) => {
        tb.appendChild(
          el("tr", {}, [
            el("td", { textContent: m }),
            el("td", { textContent: fmtNum(v.avg_relevance, 2) }),
            el("td", { textContent: fmtNum(v.avg_clarity, 2) }),
            el("td", { textContent: fmtNum(v.avg_usefulness, 2) }),
            el("td", { textContent: String(v.n_scored ?? "—") }),
          ])
        );
      });
      t.appendChild(tb);
      fb.appendChild(t);
    }
    showSection("sec-feedback", true);
  } else {
    showSection("sec-feedback", false);
  }

  // Speed
  const secSpeed = document.getElementById("sec-speed");
  const sp = document.getElementById("speed-body");
  sp.innerHTML = "";
  secSpeed.querySelectorAll(".speed-note").forEach((n) => n.remove());
  const se = data.speed_estimates || {};
  if (se.note) {
    const p = el("p", { className: "sub speed-note", textContent: String(se.note) });
    secSpeed.querySelector("h2").after(p);
  }
  Object.entries(se).forEach(([k, v]) => {
    if (k === "note") return;
    sp.appendChild(el("li", { textContent: `${k}: ${v}` }));
  });
  showSection("sec-speed", true);
}

main();
