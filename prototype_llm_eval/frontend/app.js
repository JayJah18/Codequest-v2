let currentTask = null;
let currentMarking = null;

const taskOutput = document.getElementById("taskOutput");
const markOutput = document.getElementById("markOutput");
const feedbackOutput = document.getElementById("feedbackOutput");

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

document.getElementById("generateTaskBtn").addEventListener("click", async () => {
  const concept = document.getElementById("concept").value;
  const difficulty = document.getElementById("difficulty").value;
  feedbackOutput.textContent = "";
  markOutput.textContent = "";
  currentMarking = null;

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
  } catch (error) {
    taskOutput.textContent = `Error: ${error.message}`;
  }
});

document.getElementById("markAnswerBtn").addEventListener("click", async () => {
  if (!currentTask) {
    markOutput.textContent = "Error: generate a task first.";
    return;
  }
  const student_answer = document.getElementById("studentAnswer").value.trim();
  if (!student_answer) {
    markOutput.textContent = "Error: provide a student answer.";
    return;
  }

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
  } catch (error) {
    markOutput.textContent = `Error: ${error.message}`;
  }
});

document.getElementById("feedbackBtn").addEventListener("click", async () => {
  if (!currentTask) {
    feedbackOutput.textContent = "Error: generate a task first.";
    return;
  }
  if (!currentMarking) {
    feedbackOutput.textContent = "Error: mark an answer first.";
    return;
  }

  const student_answer = document.getElementById("studentAnswer").value.trim();
  if (!student_answer) {
    feedbackOutput.textContent = "Error: provide a student answer.";
    return;
  }

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
  } catch (error) {
    feedbackOutput.textContent = `Error: ${error.message}`;
  }
});
