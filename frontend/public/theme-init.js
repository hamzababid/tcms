// Applies the saved colour theme before the app renders, so a dark-theme user never sees a white flash
// (docs/07 §6.1). A separate file because the CSP allows same-origin scripts only. Keep in step with
// src/lib/theme.ts (key and values).
(function () {
  var choice = "system";
  try {
    choice = localStorage.getItem("assay.theme") || "system";
  } catch (e) {
    /* storage blocked: follow the device */
  }
  var dark =
    choice === "dark" ||
    (choice !== "light" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();
