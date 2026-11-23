"use strict";
let token = null;           // kept in memory only: closing the tab logs you out
let timer = null;
const $ = (id) => document.getElementById(id);

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;   // plain text only: nothing can inject markup
  if (cls) e.className = cls;
  return e;
}

async function api(path, options = {}) {
  const headers = Object.assign({"Content-Type": "application/json"}, options.headers || {});
  if (token) headers.Authorization = "Bearer " + token;
  const res = await fetch(path, Object.assign({}, options, {headers}));
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (res.status === 401 && token) { logout("Session ended. Please log in again."); }
  return {ok: res.ok, status: res.status, data};
}

function logout(message) {
  token = null;
  clearInterval(timer);
  $("panel").hidden = true; $("login").hidden = false; $("logout").hidden = true; $("who").textContent = "";
  $("loginmsg").textContent = message || "";
}

async function refreshFast() {
  const h = await api("/api/health");
  const ul = $("services"); ul.replaceChildren();
  if (h.ok) {
    for (const [name, state] of Object.entries(h.data.services)) {
      const li = el("li"); li.append(el("span", name), el("span", state, state)); ul.append(li);
    }
  }
  const k = await api("/api/kill");
  if (k.ok) {
    $("killstate").textContent = k.data.engaged ? "ENGAGED: new buying is stopped (" + k.data.reason + ")" : "Not engaged: trading is allowed through the risk checks.";
  } else { $("killstate").textContent = "Cannot read the kill switch state."; }
}

async function refreshSlow() {
  const u = await api("/api/users");
  const t = $("users"); t.replaceChildren();
  if (u.ok) {
    const head = el("tr"); for (const c of ["ID", "Email", "2FA", "Locked"]) head.append(el("th", c)); t.append(head);
    for (const r of u.data) {
      const tr = el("tr");
      tr.append(el("td", String(r.id)), el("td", r.email), el("td", r.totp_enabled ? "on" : "off"), el("td", r.locked ? "yes" : "no"));
      t.append(tr);
    }
  }
  const a = await api("/api/audit");
  if (a.ok) $("audit").textContent = a.data.map((x) => x.time + "  " + x.admin + "  " + x.action + (x.detail ? "  " + x.detail : "")).reverse().join("\n") || "Nothing yet.";
}

$("loginform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("loginmsg").textContent = "";
  const body = {email: $("email").value, password: $("password").value, totp_code: $("code").value || null};
  const r = await api("/api/login", {method: "POST", body: JSON.stringify(body)});
  $("password").value = ""; $("code").value = "";
  if (!r.ok) { $("loginmsg").textContent = r.data && r.data.detail === "totp_required" ? "Enter your 2FA code." : "Login failed."; return; }
  token = r.data.access_token;
  const probe = await api("/api/health");
  if (probe.status === 403) { logout("This account is not an admin."); return; }
  $("login").hidden = true; $("panel").hidden = false; $("logout").hidden = false; $("who").textContent = body.email;
  await refreshFast(); await refreshSlow();
  timer = setInterval(() => { refreshFast(); }, 5000);
});

$("logout").addEventListener("click", () => logout("Logged out."));

$("engage").addEventListener("click", async () => {
  $("killmsg").textContent = "";
  const r = await api("/api/kill/engage", {method: "POST", body: JSON.stringify({reason: $("reason").value || "manual stop"})});
  $("killmsg").textContent = r.ok ? "" : "FAILED: " + ((r.data && r.data.detail) || "unknown error") + " Treat trading as NOT stopped.";
  await refreshFast(); await refreshSlow();
});

$("release").addEventListener("click", async () => {
  if (!window.confirm("Release the kill switch? New buys will be allowed through the risk checks again.")) return;
  $("killmsg").textContent = "";
  const r = await api("/api/kill/release", {method: "POST"});
  if (!r.ok) $("killmsg").textContent = "FAILED: " + ((r.data && r.data.detail) || "unknown error");
  await refreshFast(); await refreshSlow();
});
