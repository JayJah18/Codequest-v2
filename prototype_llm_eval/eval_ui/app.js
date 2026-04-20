const statusBar = document.getElementById("statusBar");
const progressBar = document.getElementById("progressBar");
const keyboardHints = document.getElementById("keyboardHints");
const taskSelect = document.getElementById("taskSelect");
const answerSelect = document.getElementById("answerSelect");
const markerModelSelect = document.getElementById("markerModelSelect");
const positionLabel = document.getElementById("positionLabel");
const taskMeta = document.getElementById("taskMeta");
const questionText = document.getElementById("questionText");
const studentCode = document.getElementById("studentCode");
const markingMeta = document.getElementById("markingMeta");
const markingSummary = document.getElementById("markingSummary");
const humanControls = document.getElementById("humanControls");
const notesInput = document.getElementById("notesInput");
const saveBtn = document.getElementById("saveBtn");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const llmDetails = document.getElementById("llmDetails");

let state = {
  tasks: [],
  answersByTask: {},
  markingRows: [],
  humanRows: [],
};

function setStatus(msg) {
  statusBar.textContent = msg;
}

function loadKeyList() {
  const keys = [];
  for (const t of state.tasks) {
    const answers = state.answersByTask[t.task_id] || [];
    for (const a of answers) keys.push({ taskId: t.task_id, answerId: a.answer_id });
  }
  return keys;
}

function currentKeyIndex() {
  const keys = loadKeyList();
  return keys.findIndex((k) => k.taskId === taskSelect.value && k.answerId === answerSelect.value);
}

function selectedTask() {
  return state.tasks.find((t) => t.task_id === taskSelect.value) || null;
}

function selectedAnswer() {
  const task = selectedTask();
  if (!task) return null;
  const answers = state.answersByTask[task.task_id] || [];
  return answers.find((a) => a.answer_id === answerSelect.value) || null;
}

function findMarkingRow(taskId, answerId, markerModel) {
  return state.markingRows.find(
    (r) => r.task_id === taskId && r.answer_id === answerId && r.marker_model === markerModel
  );
}

function findHumanRows(taskId, answerId) {
  return state.humanRows.filter((r) => r.task_id === taskId && r.answer_id === answerId);
}

function setSelection(taskId, answerId) {
  taskSelect.value = taskId;
  populateAnswers();
  answerSelect.value = answerId;
  renderAll();
}

function populateMarkerModels() {
  const fromData = [...new Set(state.markingRows.map((r) => r.marker_model).filter(Boolean))];
  const models = fromData.length ? fromData.sort() : ["gemini", "llama", "mistral"];
  const previous = markerModelSelect.value;
  markerModelSelect.innerHTML = "";
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    markerModelSelect.appendChild(opt);
  }
  if (models.includes(previous)) markerModelSelect.value = previous;
}

function updateProgress() {
  const keys = loadKeyList();
  let completed = 0;
  for (const k of keys) {
    const rows = findHumanRows(k.taskId, k.answerId);
    if (rows.length === 5 && rows.every((r) => humanMarkChoice(r.human_mark))) completed += 1;
  }
  const pct = keys.length ? Math.round((completed / keys.length) * 100) : 0;
  const subtasksDone = completed * 5;
  const subtasksTotal = keys.length * 5;
  progressBar.textContent = `Progress: ${completed}/${keys.length} answer attempts (${pct}%) — ${subtasksDone}/${subtasksTotal} subtask labels saved`;
}

function updatePositionLabel() {
  const keys = loadKeyList();
  const idx = currentKeyIndex();
  if (idx < 0) {
    positionLabel.textContent = "";
    return;
  }
  const task = selectedTask();
  const answer = selectedAnswer();
  let extra = "";
  if (task && answer) {
    const complete = task.subtasks.every((st) =>
      humanControls.querySelector(`input[name="hm_${st.subtask_id}"]:checked`)
    );
    if (!complete) extra = " · subtasks incomplete";
  }
  positionLabel.textContent = `Answer ${idx + 1} / ${keys.length}${extra}`;
}

function populateTasks() {
  taskSelect.innerHTML = "";
  for (const t of state.tasks) {
    const opt = document.createElement("option");
    opt.value = t.task_id;
    opt.textContent = `${t.task_id} · ${t.concept}`;
    taskSelect.appendChild(opt);
  }
}

function populateAnswers() {
  const task = selectedTask();
  answerSelect.innerHTML = "";
  if (!task) return;
  const answers = state.answersByTask[task.task_id] || [];
  for (const a of answers) {
    const opt = document.createElement("option");
    opt.value = a.answer_id;
    opt.textContent = `${a.variant_type.replace(/_/g, " ")} (${a.answer_id})`;
    answerSelect.appendChild(opt);
  }
}

function renderTaskPanel(task, answer) {
  taskMeta.textContent = `${task.task_id} · ${task.concept} · ${task.difficulty} · variant: ${answer.variant_type}`;
  questionText.textContent = task.question_text;
  studentCode.textContent = answer.code;
}

function renderMarkingPanel(task, answer) {
  const markerModel = markerModelSelect.value;
  const row = findMarkingRow(task.task_id, answer.answer_id, markerModel);
  if (!row) {
    markingMeta.textContent = `No LLM row for “${markerModel}” — run marking with this model or pick another.`;
    markingSummary.textContent = "";
    return;
  }
  const err = String(row.reasoning || "").startsWith("MARKING_ERROR:");
  markingMeta.textContent = err
    ? `LLM ${markerModel} (${row.actual_model_name || "n/a"}): marking failed — expand JSON for details.`
    : `LLM ${markerModel} (${row.actual_model_name || "n/a"}) · score ${row.overall_score}/${row.max_score} · stars ${row.star_rating}`;
  let parsed = [];
  try {
    parsed = JSON.parse(row.subtask_results_json || "[]");
  } catch {
    parsed = [];
  }
  markingSummary.textContent = JSON.stringify(
    {
      subtask_results: parsed,
      reasoning: row.reasoning,
      marking_prompt_version: row.marking_prompt_version,
      run_timestamp: row.run_timestamp,
    },
    null,
    2
  );
}

function refreshDisagreeHighlights() {
  const task = selectedTask();
  const answer = selectedAnswer();
  if (!task || !answer) return;
  const markerModel = markerModelSelect.value;
  const llmRow = findMarkingRow(task.task_id, answer.answer_id, markerModel);
  let llmBySub = {};
  if (llmRow) {
    try {
      const arr = JSON.parse(llmRow.subtask_results_json || "[]");
      for (const x of arr) {
        if (x && x.subtask_id) {
          llmBySub[x.subtask_id] = {
            mark: x.correct ? "correct" : "incorrect",
          };
        }
      }
    } catch {
      llmBySub = {};
    }
  }
  for (const st of task.subtasks) {
    const row = humanControls.querySelector(`.subtask-row[data-subtask-id="${CSS.escape(st.subtask_id)}"]`);
    if (!row) continue;
    const chosen = humanControls.querySelector(`input[name="hm_${CSS.escape(st.subtask_id)}"]:checked`);
    const choice = chosen ? String(chosen.value) : "";
    const llmMark = llmBySub[st.subtask_id]?.mark || "";
    const disagree = !!(choice && llmMark && choice !== llmMark);
    row.classList.toggle("has-disagree", disagree);
  }
}

function renderHumanPanel(task, answer) {
  const existing = findHumanRows(task.task_id, answer.answer_id);
  const bySub = {};
  for (const r of existing) bySub[r.subtask_id] = r;
  const markerModel = markerModelSelect.value;
  const llmRow = findMarkingRow(task.task_id, answer.answer_id, markerModel);
  let llmBySub = {};
  if (llmRow) {
    try {
      const arr = JSON.parse(llmRow.subtask_results_json || "[]");
      for (const x of arr) {
        if (x && x.subtask_id) {
          llmBySub[x.subtask_id] = {
            mark: x.correct ? "correct" : "incorrect",
            reason: String(x.reason || "").slice(0, 160),
          };
        }
      }
    } catch {
      llmBySub = {};
    }
  }

  humanControls.innerHTML = "";
  for (const st of task.subtasks) {
    const choice = humanMarkChoice(bySub[st.subtask_id]?.human_mark);
    const llm = llmBySub[st.subtask_id];
    const llmMark = llm ? llm.mark : "";
    const disagree = choice && llmMark && (choice !== llmMark);
    const reasonHtml = llm && llm.reason ? `<div class="reason-snippet" title="${escapeAttr(llm.reason)}">LLM note: ${escapeHtml(llm.reason)}</div>` : "";

    const row = document.createElement("div");
    row.className = disagree ? "subtask-row has-disagree" : "subtask-row";
    row.dataset.subtaskId = st.subtask_id;
    row.innerHTML = `
      <div class="subtask-head">
        <span class="subtask-id">${st.subtask_id}</span>
        <span class="subtask-label">${escapeHtml(st.label)}</span>
      </div>
      <div class="llm-line">LLM (${escapeHtml(markerModel)}): <strong>${llmMark || "—"}</strong>${disagree ? '<span class="disagree">≠ your mark</span>' : ""}</div>
      ${reasonHtml}
      <div class="quick-mark">
        <button type="button" class="btn-correct${choice === "correct" ? " is-selected" : ""}" data-subtask-id="${escapeAttr(st.subtask_id)}" data-mark="correct">Correct</button>
        <button type="button" class="btn-incorrect${choice === "incorrect" ? " is-selected" : ""}" data-subtask-id="${escapeAttr(st.subtask_id)}" data-mark="incorrect">Incorrect</button>
      </div>
      <div class="sr-only">
        <label><input type="radio" name="hm_${st.subtask_id}" value="correct" ${choice === "correct" ? "checked" : ""} /> correct</label>
        <label><input type="radio" name="hm_${st.subtask_id}" value="incorrect" ${choice === "incorrect" ? "checked" : ""} /> incorrect</label>
      </div>
    `;
    humanControls.appendChild(row);
  }

  notesInput.value = existing[0]?.notes || "";
}

function humanMarkChoice(mark) {
  const t = String(mark || "").trim().toLowerCase();
  if (t === "correct" || t === "1" || t === "true" || t === "y" || t === "yes") return "correct";
  if (t === "incorrect" || t === "0" || t === "false" || t === "n" || t === "no") return "incorrect";
  return "";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

function renderAll() {
  const task = selectedTask();
  const answer = selectedAnswer();
  if (!task || !answer) return;
  renderTaskPanel(task, answer);
  renderMarkingPanel(task, answer);
  renderHumanPanel(task, answer);
  updateProgress();
  updatePositionLabel();
}

function syncQuickMarkButtons(row, selectedValue) {
  const correctBtn = row.querySelector(".btn-correct");
  const incorrectBtn = row.querySelector(".btn-incorrect");
  if (correctBtn) correctBtn.classList.toggle("is-selected", selectedValue === "correct");
  if (incorrectBtn) incorrectBtn.classList.toggle("is-selected", selectedValue === "incorrect");
}

humanControls.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-mark]");
  if (!btn) return;
  e.preventDefault();
  const row = btn.closest(".subtask-row");
  if (!row) return;
  const sid = btn.getAttribute("data-subtask-id");
  const val = btn.getAttribute("data-mark");
  if (!sid || !val) return;
  const inp = row.querySelector(`input[name="hm_${CSS.escape(sid)}"][value="${CSS.escape(val)}"]`);
  if (inp) {
    inp.checked = true;
    inp.dispatchEvent(new Event("change", { bubbles: true }));
  } else {
    syncQuickMarkButtons(row, val);
  }
  refreshDisagreeHighlights();
  updateProgress();
  updatePositionLabel();
});

humanControls.addEventListener("change", (e) => {
  const t = e.target;
  if (!(t instanceof HTMLInputElement) || t.type !== "radio") return;
  const row = t.closest(".subtask-row");
  if (row) syncQuickMarkButtons(row, t.value);
  refreshDisagreeHighlights();
  updateProgress();
  updatePositionLabel();
});

async function saveMarks() {
  const task = selectedTask();
  const answer = selectedAnswer();
  if (!task || !answer) return;
  const markerModel = markerModelSelect.value;
  const llmRow = findMarkingRow(task.task_id, answer.answer_id, markerModel);
  let llmMarks = {};
  if (llmRow) {
    try {
      const arr = JSON.parse(llmRow.subtask_results_json || "[]");
      for (const x of arr) llmMarks[x.subtask_id] = x.correct ? "correct" : "incorrect";
    } catch {
      llmMarks = {};
    }
  }
  const subtasks = [];
  for (const st of task.subtasks) {
    const chosen = humanControls.querySelector(`input[name="hm_${st.subtask_id}"]:checked`);
    if (!chosen) {
      setStatus(`Pick Correct or Incorrect for ${st.subtask_id}.`);
      return;
    }
    subtasks.push({
      subtask_id: st.subtask_id,
      subtask_label: st.label,
      human_mark: chosen.value,
      llm_mark_for_subtask: llmMarks[st.subtask_id] || "",
    });
  }

  saveBtn.disabled = true;
  try {
    const res = await fetch("/api/eval/human-marks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: task.task_id,
        concept: task.concept,
        answer_id: answer.answer_id,
        variant_type: answer.variant_type,
        student_answer_code: answer.code,
        llm_marker_model: markerModel,
        notes: notesInput.value.trim(),
        subtasks,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Save failed");
    setStatus(`Saved 5 rows → human_marks.csv`);
    await initData();
    const keys = loadKeyList();
    const idx = currentKeyIndex();
    if (idx >= 0 && idx + 1 < keys.length) {
      setSelection(keys[idx + 1].taskId, keys[idx + 1].answerId);
    } else {
      renderAll();
    }
  } catch (err) {
    setStatus(`Save failed: ${err.message}`);
  } finally {
    saveBtn.disabled = false;
  }
}

function move(offset) {
  const keys = loadKeyList();
  const idx = currentKeyIndex();
  if (idx < 0) return;
  const next = idx + offset;
  if (next < 0 || next >= keys.length) return;
  setSelection(keys[next].taskId, keys[next].answerId);
}

async function initData() {
  const res = await fetch("/api/eval/data");
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to load eval data");
  state = {
    tasks: data.tasks || [],
    answersByTask: data.answers_by_task || {},
    markingRows: data.marking_rows || [],
    humanRows: data.human_rows || [],
  };
}

taskSelect.addEventListener("change", () => {
  populateAnswers();
  renderAll();
});
answerSelect.addEventListener("change", renderAll);
markerModelSelect.addEventListener("change", renderAll);
saveBtn.addEventListener("click", saveMarks);
prevBtn.addEventListener("click", () => move(-1));
nextBtn.addEventListener("click", () => move(1));

document.addEventListener("keydown", (e) => {
  const inNotes = e.target === notesInput;
  const inSelect = e.target instanceof HTMLSelectElement;

  if (inNotes && e.ctrlKey && e.key === "Enter") {
    e.preventDefault();
    saveMarks();
    return;
  }
  if (inNotes) return;

  if (e.altKey && e.code === "KeyN") {
    e.preventDefault();
    move(1);
    return;
  }
  if (e.altKey && e.code === "KeyP") {
    e.preventDefault();
    move(-1);
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    saveMarks();
    return;
  }
  if (inSelect) return;
});

(async () => {
  keyboardHints.textContent =
    "Shortcuts: Alt+N next answer · Alt+P previous · Ctrl+Enter save & next (works in notes too).";

  try {
    await initData();
    if (!state.tasks.length) {
      setStatus("No tasks. Check fixed dataset and pilot env (TASK_IDS / TASK_LIMIT / CONCEPT_FILTER) on the API server.");
      return;
    }
    populateTasks();
    populateAnswers();
    populateMarkerModels();
    setStatus("Ready — start marking.");
    llmDetails.open = false;
    renderAll();
  } catch (err) {
    setStatus(`Load failed: ${err.message}`);
  }
})();
