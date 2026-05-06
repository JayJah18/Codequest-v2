(() => {
  document.getElementById("btn-logout")?.addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    } catch {
      /* ignore */
    }
    window.location.href = "/login";
  });
})();
