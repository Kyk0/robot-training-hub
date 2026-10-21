const settings = window.WORKSHOP || {};
let launch;
try {
  const url = new URL(settings.url);
  if (url.protocol === "https:" && settings.ready)
    launch = url.origin + "/login";
} catch {}
for (const link of document.querySelectorAll("[data-launch]")) {
  if (launch) {
    link.href = launch;
    link.removeAttribute("aria-disabled");
  } else {
    link.removeAttribute("href");
    link.setAttribute("aria-disabled", "true");
    link.title = "The organizer is connecting the secure training server.";
  }
}
if (!launch)
  document.getElementById("access-note").textContent =
    "The secure training server is being connected. Please check back shortly.";
