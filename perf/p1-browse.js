// P1 Browse repository (docs/08 §9): 30 VUs open the tree, list a folder, open a case and search.
// Pass: p95 < 300 ms for list and detail (NFR-PERF-01), tree < 1 s (NFR-PERF-02), search < 500 ms
// (NFR-PERF-05), no failed requests.
import { sleep } from "k6";
import { ensureLogin, get, json, login, pick, spark, TESTERS } from "./lib.js";

export const options = {
  insecureSkipTLSVerify: true,
  noCookiesReset: true, // a VU signs in once and keeps its session, like a browser
  scenarios: {
    browse: { executor: "constant-vus", vus: Number(__ENV.VUS || 30), duration: __ENV.DURATION || "5m" },
  },
  thresholds: {
    "http_req_duration{name:tree}": ["p(95)<1000"],
    "http_req_duration{name:list}": ["p(95)<300", "p(99)<1000"],
    "http_req_duration{name:case}": ["p(95)<300", "p(99)<1000"],
    "http_req_duration{name:search}": ["p(95)<500"],
    checks: ["rate>0.999"],
  },
};

export function setup() {
  login("ayesha@acme.test");
  return spark();
}

export function browse(data) {
  const { pid, leaves } = data;
  ensureLogin(TESTERS[__VU % TESTERS.length]);
  get(`/api/v1/projects/${pid}/folders`, "tree");
  const page = json(get(`/api/v1/projects/${pid}/test-cases?folder_id=${pick(leaves)}&page_size=50`, "list"), "list");
  if (page.items.length) get(`/api/v1/test-cases/${pick(page.items).id}`, "case");
  get(`/api/v1/search?q=${encodeURIComponent(`Generated case ${1 + Math.floor(Math.random() * 99000)}`)}&project_id=${pid}`, "search");
  sleep(1);
}

export default browse;
