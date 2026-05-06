let currentTask = null;
let currentMarking = null;

const taskOutput = document.getElementById("taskOutput");
const markOutput = document.getElementById("markOutput");
const feedbackOutput = document.getElementById("feedbackOutput");
const statusBar = document.getElementById("statusBar");
const generateTaskBtn = document.getElementById("generateTaskBtn");
const markAnswerBtn = document.getElementById("markAnswerBtn");
const feedbackBtn = document.getElementById("feedbackBtn");
const clearBtn = document.getElementById("clearBtn");

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setStatus(message) {
  statusBar.textContent = message;
}

function setBusy(busy) {
  generateTaskBtn.disabled = busy;
  markAnswerBtn.disabled = busy;
  feedbackBtn.disabled = busy;
  clearBtn.disabled = busy;
}

generateTaskBtn.addEventListener("click", async () => {
  const concept = document.getElementById("concept").value;
  const difficulty = document.getElementById("difficulty").value;
  feedbackOutput.textContent = "";
  markOutput.textContent = "";
  currentMarking = null;
  setBusy(true);
  setStatus("Generating next task...");

  try {
    const response = await fetch("/generate-task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept, difficulty }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Task generation failed");
    currentTask = data;
    taskOutput.textContent = pretty(data);
    setStatus(`Task ready: ${data.task_id}`);
  } catch (error) {
    taskOutput.textContent = `Error: ${error.message}`;
    setStatus("Task generation failed.");
  } finally {
    setBusy(false);
  }
});

markAnswerBtn.addEventListener("click", async () => {
  if (!currentTask) {
    markOutput.textContent = "Error: generate a task first.";
    setStatus("No task to mark yet.");
    return;
  }
  const student_answer = document.getElementById("studentAnswer").value.trim();
  if (!student_answer) {
    markOutput.textContent = "Error: provide a student answer.";
    setStatus("Student answer is required.");
    return;
  }
  setBusy(true);
  setStatus("Marking answer...");

  try {
    const response = await fetch("/mark-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: currentTask.task_id,
        student_answer,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Marking failed");
    currentMarking = data;
    markOutput.textContent = pretty(data);
    setStatus("Marking complete.");
  } catch (error) {
    markOutput.textContent = `Error: ${error.message}`;
    setStatus("Marking failed.");
  } finally {
    setBusy(false);
  }
});

feedbackBtn.addEventListener("click", async () => {
  if (!currentTask) {
    feedbackOutput.textContent = "Error: generate a task first.";
    setStatus("No task available for feedback.");
    return;
  }
  if (!currentMarking) {
    feedbackOutput.textContent = "Error: mark an answer first.";
    setStatus("Marking is required before feedback.");
    return;
  }

  const student_answer = document.getElementById("studentAnswer").value.trim();
  if (!student_answer) {
    feedbackOutput.textContent = "Error: provide a student answer.";
    setStatus("Student answer is required.");
    return;
  }
  setBusy(true);
  setStatus("Generating feedback...");

  try {
    const response = await fetch("/generate-feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task_id: currentTask.task_id,
        student_answer,
        marking_result: currentMarking,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Feedback generation failed");
    feedbackOutput.textContent = pretty(data);
    setStatus("Feedback ready.");
  } catch (error) {
    feedbackOutput.textContent = `Error: ${error.message}`;
    setStatus("Feedback generation failed.");
  } finally {
    setBusy(false);
  }
});

clearBtn.addEventListener("click", () => {
  currentTask = null;
  currentMarking = null;
  taskOutput.textContent = "";
  markOutput.textContent = "";
  feedbackOutput.textContent = "";
  document.getElementById("studentAnswer").value = "";
  setStatus("Cleared. Ready.");
});
