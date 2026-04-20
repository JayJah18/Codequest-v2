(async () => {
  const pre = document.getElementById("config-pre");
  try {
    const res = await fetch("/api/demo/config");
    const data = await res.json();
    pre.textContent = res.ok
      ? JSON.stringify(
          {
            use_fixed_dataset: data.use_fixed_dataset,
            question_generation_provider: data.question_generation_provider,
            marking_provider: data.marking_provider,
            feedback_provider: data.feedback_provider,
            notes: (data.notes && data.notes.frozen_benchmark) || undefined,
          },
          null,
          2
        )
      : `Could not load config (${res.status}).`;
  } catch (e) {
    pre.textContent = `Config fetch failed: ${e}`;
  }
})();
