// P3 Dashboards (docs/08 §9, NFR-PERF-04): 10 VUs open the manager dashboard, the quality dashboard and
// traceability for an active release (5,000 requirement references in the xlarge seed). Pass: p95 < 2 s.
import { sleep } from "k6";
import { ensureLogin, get, login, pick, spark, TESTERS } from "./lib.js";

export const options = {
  insecureSkipTLSVerify: true,
  noCookiesReset: true, // a VU signs in once and keeps its session, like a browser
  scenarios: {
    dashboards: { executor: "constant-vus", vus: Number(__ENV.VUS || 10), duration: __ENV.DURATION || "3m" },
  },
  thresholds: {
    "http_req_duration{name:manager}": ["p(95)<2000"],
    "http_req_duration{name:quality}": ["p(95)<2000"],
    "http_req_duration{name:traceability}": ["p(95)<2000"],
    checks: ["rate>0.999"],
  },
};

export function setup() {
  login("ayesha@acme.test");
  return spark();
}

export function dashboards(data) {
  ensureLogin(TESTERS[__VU % TESTERS.length]);
  const release = pick(data.active);
  get(`/api/v1/projects/${data.pid}/dashboards/manager?release_id=${release}`, "manager");
  get(`/api/v1/projects/${data.pid}/dashboards/quality?release_id=${release}`, "quality");
  get(`/api/v1/projects/${data.pid}/traceability?release_id=${release}`, "traceability");
  sleep(2);
}

export default dashboards;
