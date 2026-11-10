// P2 Execution (docs/08 §9, NFR-PERF-03/07): 50 testers each run cases with 10 steps: start the attempt,
// save every step (2 s think time), finish. Pass: p95 step save < 200 ms, no failed request, and the
// post-check finds exactly one final result per executed run (no lost updates).
import { check, fail, sleep } from "k6";
import { Counter } from "k6/metrics";
import { get, json, login, send, spark, TESTERS } from "./lib.js";

const VUS = Number(__ENV.VUS || 50);
const RUNS_PER_VU = Number(__ENV.RUNS_PER_VU || 3);
const finished = new Counter("runs_finished");

export const options = {
  insecureSkipTLSVerify: true,
  noCookiesReset: true, // a VU signs in once and keeps its session, like a browser
  setupTimeout: "10m",
  scenarios: {
    execute: { executor: "per-vu-iterations", vus: VUS, iterations: RUNS_PER_VU, maxDuration: "20m" },
  },
  thresholds: {
    "http_req_duration{name:step}": ["p(95)<200"],
    "http_req_duration{name:start}": ["p(95)<300"],
    "http_req_duration{name:finish}": ["p(95)<300"],
    "http_req_failed{scenario:execute}": ["rate==0"],
    checks: ["rate==1"],
  },
};

export function setup() {
  login("ayesha@acme.test");
  const { pid, env } = spark();
  const stamp = Date.now();
  const folder = json(send("POST", `/api/v1/projects/${pid}/folders`, { name: `k6 P2 ${stamp}` }, "setup"), "folder");
  const steps = Array.from({ length: 10 }, (_, i) => ({ action: `Step ${i + 1}`, expected_result: "OK" }));
  const ids = [];
  for (let i = 0; i < VUS * RUNS_PER_VU; i++) {
    const c = send("POST", `/api/v1/projects/${pid}/test-cases`, {
      folder_id: folder.id,
      content: { format: "steps", title: `k6 execution ${stamp}-${i}`, steps },
    }, "setup");
    ids.push(json(c, "case").case.id);
  }
  const cycle = json(send("POST", `/api/v1/projects/${pid}/cycles`, {
    name: `k6 P2 ${stamp}`, environment_id: env, selection: { case_ids: ids },
  }, "setup"), "cycle").cycle;
  const runs = allRuns(cycle.id).map((r) => r.id);
  if (runs.length !== ids.length) fail(`expected ${ids.length} runs, got ${runs.length}`);
  return { cycle: cycle.id, runs };
}

function allRuns(cycleId) {
  const out = [];
  for (let page = 1; ; page++) {
    const r = json(get(`/api/v1/cycles/${cycleId}/runs?page=${page}&page_size=100`, "setup"), "runs");
    out.push(...r.items);
    if (out.length >= r.total || r.items.length === 0) return out;
  }
}

export function execute(data) {
  if (__ITER === 0) login(TESTERS[__VU % TESTERS.length]);
  const run = data.runs[(__VU - 1) * RUNS_PER_VU + __ITER];
  const started = send("POST", `/api/v1/runs/${run}/results`, undefined, "start", 201);
  if (started.status !== 201) return;
  const attempt = started.json();
  for (const step of attempt.steps) {
    sleep(2);
    send("PATCH", `/api/v1/results/${attempt.id}/steps/${step.step_id}`, { status: "passed" }, "step", 200);
  }
  const done = send("POST", `/api/v1/results/${attempt.id}/finalize`, {}, "finish", 200);
  if (done.status === 200) finished.add(1);
}

export function teardown(data) {
  login("ayesha@acme.test");
  const runs = allRuns(data.cycle);
  const passed = runs.filter((r) => r.status === "passed").length;
  console.log(`post-check: ${passed} of ${runs.length} runs passed`);
  check(passed, { "every executed run is passed (no lost updates)": (n) => n === VUS * RUNS_PER_VU });
}

export default execute;
