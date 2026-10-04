/* Shared helpers for In a Tree */
async function api(method, url, data) {
  const opts = { method, headers: {} };
  if (data !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(data);
  }
  const res = await fetch(url, opts);
  let body = null;
  try { body = await res.json(); } catch (e) { /* no json */ }
  if (!res.ok) throw new Error((body && body.error) || ("Request failed (" + res.status + ")"));
  return body;
}
const get = (url) => api("GET", url);
const post = (url, data) => api("POST", url, data);
const put = (url, data) => api("PUT", url, data);
const del = (url) => api("DELETE", url);

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

let ME = null;
async function loadMe() {
  try {
    const r = await get("/api/me");
    ME = r.user;
  } catch (e) { ME = null; }
  applyAuthUI();
  return ME;
}

function applyAuthUI() {
  const loggedIn = !!ME;
  document.querySelectorAll("[data-auth]").forEach((el) => {
    const kind = el.getAttribute("data-auth");
    let show = false;
    if (kind === "in") show = loggedIn;
    else if (kind === "out") show = !loggedIn;
    else if (kind === "admin") show = loggedIn && ME.is_admin;
    el.style.display = show ? "" : "none";
  });
}

async function doLogout() {
  await post("/api/logout");
  location.href = "/";
}

/* Age gate: once per browser, on every page */
(function ageGate() {
  if (localStorage.getItem("lsh_age_ok") === "1") return;
  const gate = document.getElementById("agegate");
  if (!gate) return;
  gate.classList.remove("hidden");
  document.getElementById("age-yes").addEventListener("click", () => {
    localStorage.setItem("lsh_age_ok", "1");
    gate.classList.add("hidden");
  });
})();

document.addEventListener("DOMContentLoaded", () => {
  loadMe();
  const lb = document.getElementById("logout-btn");
  if (lb) lb.addEventListener("click", doLogout);
});
