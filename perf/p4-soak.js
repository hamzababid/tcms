// P4 Mixed soak (docs/08 §9): 50 VUs mix browsing (35) and dashboards (15) for DURATION (2 h on staging,
// 20 min locally, M8 D13). Pass: error rate < 0.1 %; memory growth < 10 % is read from `docker stats`
// before and after (docs/ops/performance.md).
import { browse, setup } from "./p1-browse.js";
import { dashboards } from "./p3-dashboards.js";

const DURATION = __ENV.DURATION || "20m";

export const options = {
  insecureSkipTLSVerify: true,
  noCookiesReset: true, // a VU signs in once and keeps its session, like a browser
  scenarios: {
    browse: { executor: "constant-vus", exec: "browse", vus: 35, duration: DURATION },
    dashboards: { executor: "constant-vus", exec: "dashboards", vus: 15, duration: DURATION },
  },
  thresholds: {
    http_req_failed: ["rate<0.001"],
    "http_req_duration{name:list}": ["p(95)<300"],
    "http_req_duration{name:manager}": ["p(95)<2000"],
  },
};

export { browse, dashboards, setup };
