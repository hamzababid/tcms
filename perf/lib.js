// Shared helpers for the k6 scenarios P1–P6 (docs/08 §9, M8 D13). Each VU signs in once and keeps its own
// session cookie (k6 keeps a cookie jar per VU), like a browser tab.
import http from "k6/http";
import { check, fail } from "k6";

export const BASE = __ENV.BASE_URL || "https://localhost";
export const PASSWORD = "Passw0rd!Passw0rd"; // seed users (docs/ops/local-setup.md); never a real system
export const TESTERS = ["sana@acme.test", "bilal@acme.test", "ayesha@acme.test"];

export function login(email) {
  const r = http.post(`${BASE}/api/v1/auth/login`, JSON.stringify({ email, password: PASSWORD }), {
    headers: { "Content-Type": "application/json" },
    tags: { name: "login" },
  });
  if (r.status !== 200) fail(`sign-in ${email}: ${r.status} ${r.body}`);
}

let signedIn = false; // per VU (each VU has its own module instance)

/** Sign in when this VU has no session yet, or lost it (a 401 resets the flag). */
export function ensureLogin(email) {
  if (!signedIn) {
    login(email);
    signedIn = true;
  }
}

function csrf() {
  const c = http.cookieJar().cookiesForURL(BASE).tcms_csrf;
  return c ? c[0] : "";
}

export function get(path, name, expected = 200) {
  const r = http.get(`${BASE}${path}`, { tags: { name } });
  if (r.status === 401) signedIn = false;
  check(r, { [`${name} ${expected}`]: (x) => x.status === expected });
  return r;
}

export function send(method, path, body, name, expected) {
  const r = http.request(method, `${BASE}${path}`, body === undefined ? null : JSON.stringify(body), {
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
    tags: { name },
  });
  if (expected !== undefined) check(r, { [`${name} ${expected}`]: (x) => x.status === expected });
  return r;
}

export function json(r, what) {
  if (r.status >= 300) fail(`${what}: ${r.status} ${r.body}`);
  return r.json();
}

/** SPARK's id and its large-seed data: leaf folders, an active release, a few case ids. */
export function spark() {
  const projects = json(get("/api/v1/projects", "setup"), "projects");
  const p = projects.find((x) => x.key === "SPARK");
  if (!p) fail("no SPARK project: seed the xlarge profile first");
  const folders = json(get(`/api/v1/projects/${p.id}/folders`, "setup"), "folders");
  const leaves = folders.filter((f) => f.depth === 3).map((f) => f.id);
  const areas = folders.filter((f) => f.depth === 1).map((f) => f.id);
  const releases = json(get(`/api/v1/projects/${p.id}/releases`, "setup"), "releases");
  const active = releases.filter((r) => r.status === "active").map((r) => r.id);
  const envs = json(get(`/api/v1/projects/${p.id}/environments`, "setup"), "environments");
  return { pid: p.id, leaves, areas, active, env: envs[0].id };
}

export function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}
