// P6 Cycle creation (docs/08 §9): one cycle from a folder of 5,000 cases. Over the inline limit the runs are
// created by the `cycle.create_runs` job; the time is until `runs_pending` is false. Pass: < 60 s.
import { check, fail, sleep } from "k6";
import { Trend } from "k6/metrics";
import { get, json, login, send, spark } from "./lib.js";

const created = new Trend("cycle_runs_created_ms", true);

export const options = {
  insecureSkipTLSVerify: true,
  noCookiesReset: true, // a VU signs in once and keeps its session, like a browser
  scenarios: { cycle: { executor: "shared-iterations", vus: 1, iterations: 1, maxDuration: "5m" } },
  thresholds: { cycle_runs_created_ms: ["max<60000"], checks: ["rate==1"] },
};

export default function () {
  login("ayesha@acme.test");
  const { pid, env, areas } = spark();
  const t0 = Date.now();
  const r = json(send("POST", `/api/v1/projects/${pid}/cycles`, {
    name: `k6 P6 ${t0}`, environment_id: env, selection: { folder_ids: [areas[0]] },
  }, "create", 202), "cycle"); // 202: runs are created by the job
  let cycle = r.cycle;
  while (cycle.runs_pending) {
    if (Date.now() - t0 > 240000) fail("runs still pending after 4 minutes");
    sleep(1);
    cycle = json(get(`/api/v1/cycles/${cycle.id}`, "poll"), "cycle");
  }
  created.add(Date.now() - t0);
  const runs = json(get(`/api/v1/cycles/${cycle.id}/runs?page_size=1`, "runs"), "runs");
  console.log(`P6: ${runs.total} runs in ${Date.now() - t0} ms (inline: ${r.added ?? "?"})`);
  check(runs.total, { "5,000 runs": (n) => n === 5000 });
}
