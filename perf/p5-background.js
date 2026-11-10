// P5 Background (docs/08 §9, NFR-PERF-06): import 5,000 cases / 20,000 steps and export 100,000 runs while
// 30 VUs browse. Pass: the import commits < 2 min, the export completes, and the browse p95 stays within
// +20 % of a P1 run without background work (compare with p1-browse.js in docs/ops/performance.md).
import http from "k6/http";
import { check, fail, sleep } from "k6";
import { Trend } from "k6/metrics";
import { browse } from "./p1-browse.js";
import { BASE, get, json, login, send, spark } from "./lib.js";

const importMs = new Trend("import_total_ms", true);
const exportMs = new Trend("export_total_ms", true);

export const options = {
  insecureSkipTLSVerify: true,
  noCookiesReset: true, // a VU signs in once and keeps its session, like a browser
  setupTimeout: "2m",
  scenarios: {
    browse: { executor: "constant-vus", exec: "browse", vus: 30, duration: __ENV.DURATION || "4m", startTime: "0s" },
    background: { executor: "shared-iterations", exec: "background", vus: 1, iterations: 1, startTime: "30s", maxDuration: "12m" },
  },
  thresholds: {
    import_total_ms: ["max<120000"],
    "http_req_duration{name:list}": ["p(95)<300"],
    "checks{scenario:background}": ["rate==1"],
  },
};

export function setup() {
  login("ayesha@acme.test");
  return spark();
}

function csv() {
  const rows = ["Title,Folder,Priority,Step,Expected"];
  for (let i = 0; i < 5000; i++) {
    rows.push(`k6 import ${i},k6 import/Area ${i % 20},medium,Step 1,OK`);
    for (let n = 2; n <= 4; n++) rows.push(`,,,Step ${n},OK`);
  }
  return rows.join("\n");
}

function csrf() {
  const c = http.cookieJar().cookiesForURL(BASE).tcms_csrf;
  return c ? c[0] : "";
}

function waitFor(id, done, what) {
  for (let i = 0; i < 600; i++) {
    const t = json(get(`/api/v1/data-transfers/${id}`, "poll"), what);
    if (done.includes(t.status)) return t;
    if (t.status === "failed") fail(`${what} failed: ${JSON.stringify(t.errors).slice(0, 300)}`);
    sleep(1);
  }
  fail(`${what} did not finish`);
}

export function background(data) {
  login("ayesha@acme.test");
  const { pid } = data;

  const t0 = Date.now();
  const up = http.post(`${BASE}/api/v1/projects/${pid}/imports`, {
    entity: "test_case",
    file: http.file(csv(), "k6-import.csv", "text/csv"),
  }, { headers: { "X-CSRF-Token": csrf() }, tags: { name: "import-upload" } });
  const uploaded = json(up, "upload");
  send("POST", `/api/v1/data-transfers/${uploaded.transfer_id}/validate`, {
    mapping: uploaded.sheets[0].suggested_mapping,
  }, "import-validate", 202);
  const validated = waitFor(uploaded.transfer_id, ["validated"], "validate");
  check(validated.summary.counts, { "5,000 cases to create": (c) => c.create === 5000 });
  send("POST", `/api/v1/data-transfers/${uploaded.transfer_id}/commit`, undefined, "import-commit", 202);
  waitFor(uploaded.transfer_id, ["committed"], "commit");
  importMs.add(Date.now() - t0);

  const t1 = Date.now();
  // About 100,000 attempts: the last 24 days of the xlarge seed (EXPORT_DAYS overrides).
  const from = new Date(Date.now() - Number(__ENV.EXPORT_DAYS || 24) * 86400000).toISOString().slice(0, 10);
  const ex = send("POST", `/api/v1/projects/${pid}/reports/results-history/export`, {
    format: "csv", filters: { date_from: from },
  }, "export", 202);
  check(ex, { "export runs in the background": (r) => r.status === 202 });
  if (ex.status === 202) {
    const t = waitFor(ex.json().transfer_id, ["ready", "committed"], "export");
    exportMs.add(Date.now() - t1);
    console.log(`P5: export of ${t.summary.rows} rows in ${Date.now() - t1} ms; import in ${Date.now() - t0 - (Date.now() - t1)} ms`);
    check(t.summary.rows, { "≥ 100,000 rows": (n) => n >= 100000 });
  }
}

export { browse };
