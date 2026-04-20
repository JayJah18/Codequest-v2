(() => {
  const form = document.getElementById("login-form");
  const err = document.getElementById("login-error");

  function params() {
    return new URLSearchParams(window.location.search);
  }

  function safeNext() {
    const n = params().get("next") || "/admin";
    if (!n.startsWith("/") || n.startsWith("//")) return "/admin";
    return n;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    err.textContent = "";
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d = data.detail;
        err.textContent = typeof d === "string" ? d : d ? JSON.stringify(d) : `Login failed (${res.status})`;
        err.hidden = false;
        return;
      }
      window.location.href = safeNext();
    } catch (ex) {
      err.textContent = String(ex);
      err.hidden = false;
    }
  });
})();
