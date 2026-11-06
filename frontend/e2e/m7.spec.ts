import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M7a journeys: UJ-8 release readiness and a recorded decision (TCMS-116), the Overview (TCMS-115),
// report export with formula escaping (TCMS-117), quality dashboard and My Work additions.
// Each worker makes its own project with a release.

const run = (Date.now().toString(36) + Math.random().toString(36).slice(2, 6)).toUpperCase();
let seq = 0;
const uniq = (label: string) => `${label} ${run}-${++seq}`;

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    serious,
    JSON.stringify(
      serious.map((v) => [v.id, v.nodes.map((n) => n.target)]),
      null,
      2,
    ),
  ).toEqual([]);
}

type SeedUser = "ayesha" | "bilal" | "sana";

async function as(browser: Browser, user: SeedUser): Promise<Page> {
  const context = await browser.newContext({ storageState: `e2e/.auth/${user}.json` });
  return context.newPage();
}

async function call<T>(page: Page, method: string, url: string, data?: unknown): Promise<T> {
  const cookie = (await page.context().cookies()).find((c) => c.name === "tcms_csrf");
  const r = await page.request.fetch(url, {
    method,
    data,
    headers: cookie ? { "X-CSRF-Token": cookie.value } : {},
  });
  expect(r.ok(), `${method} ${url}: ${r.status()} ${await r.text()}`).toBe(true);
  return (r.status() === 204 ? null : await r.json()) as T;
}

interface Space {
  pid: string;
  key: string;
  release: { id: string; name: string };
  folder: string;
  env: string;
  sana: string;
}

let space: Space | null = null;

async function project(browser: Browser): Promise<Space> {
  if (space) return space;
  const ayesha = await as(browser, "ayesha");
  const key = `M${run.slice(-8)}`.replace(/[^A-Z0-9]/g, "X").slice(0, 10);
  const p = await call<{ id: string; key: string }>(ayesha, "POST", "/api/v1/projects", {
    key,
    name: uniq("Readiness"),
  });
  const people = await call<{ id: string; email: string }[]>(
    ayesha,
    "GET",
    `/api/v1/projects/${p.id}/member-candidates`,
  );
  let sana = "";
  for (const [email, role] of [
    ["bilal@acme.test", "qa_lead"],
    ["sana@acme.test", "qa_engineer"],
  ] as const) {
    const u = people.find((x) => x.email === email);
    if (!u) throw new Error(`${email} cannot be added`);
    if (email === "sana@acme.test") sana = u.id;
    await call(ayesha, "POST", `/api/v1/projects/${p.id}/members`, { user_id: u.id, role_code: role });
  }
  const rel = await call<{ id: string; name: string; row_version: number }>(
    ayesha,
    "POST",
    `/api/v1/projects/${p.id}/releases`,
    { name: `v${run.slice(-3)}` },
  );
  await call(ayesha, "PATCH", `/api/v1/releases/${rel.id}`, {
    status: "active",
    row_version: rel.row_version,
  });
  const folder = await call<{ id: string }>(ayesha, "POST", `/api/v1/projects/${p.id}/folders`, {
    name: "Billing",
  });
  const envs = await call<{ id: string }[]>(ayesha, "GET", `/api/v1/projects/${p.id}/environments`);
  await ayesha.context().close();
  space = { pid: p.id, key: p.key, release: rel, folder: folder.id, env: envs[0]?.id ?? "", sana };
  return space;
}

async function newCase(page: Page, sp: Space, title: string): Promise<{ id: string; key: string }> {
  const r = await call<{ case: { id: string; key: string } }>(
    page,
    "POST",
    `/api/v1/projects/${sp.pid}/test-cases`,
    {
      folder_id: sp.folder,
      content: { format: "steps", title, steps: [{ action: "Do it", expected_result: "Done" }] },
    },
  );
  return r.case;
}

async function execute(page: Page, runId: string, status: "passed" | "failed") {
  const res = await call<{ id: string; steps: { step_id: string }[] }>(
    page,
    "POST",
    `/api/v1/runs/${runId}/results`,
    {},
  );
  await call(page, "PATCH", `/api/v1/results/${res.id}/steps/${res.steps[0]?.step_id ?? ""}`, {
    status,
    ...(status === "failed" ? { actual_result: "Wrong total" } : {}),
  });
  await call(page, "POST", `/api/v1/results/${res.id}/finalize`, {});
}

/** A plan of the release with rules and a started cycle from it → run ids. */
async function planWithCycle(
  page: Page,
  sp: Space,
  cases: string[],
): Promise<{ key: string; runs: string[] }> {
  const plan = await call<{ id: string; key: string }>(
    page,
    "POST",
    `/api/v1/projects/${sp.pid}/test-plans`,
    {
      name: uniq("Release plan"),
      type: "regression",
      release_id: sp.release.id,
      exit_rules: [
        { type: "min_execution_progress", threshold: 1 },
        { type: "max_failed", threshold: 0 },
      ],
    },
  );
  await call(page, "POST", `/api/v1/test-plans/${plan.id}/cases`, { case_ids: cases });
  const cyc = await call<{ cycle: { id: string } }>(page, "POST", `/api/v1/projects/${sp.pid}/cycles`, {
    name: uniq("Cycle"),
    environment_id: sp.env,
    release_id: sp.release.id,
    plan_id: plan.id,
    selection: { from_plan: true },
    default_assignee_id: sp.sana,
  });
  await call(page, "POST", `/api/v1/cycles/${cyc.cycle.id}/start`);
  const runs = await call<{ items: { id: string }[] }>(page, "GET", `/api/v1/cycles/${cyc.cycle.id}/runs`);
  return { key: plan.key, runs: runs.items.map((r) => r.id) };
}

test("UJ-8 / TCMS-116: readiness is Not ready, the retest makes it Ready, Go is recorded with a snapshot", async ({
  browser,
}) => {
  test.setTimeout(60_000);
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const sana = await as(browser, "sana");
  const a = await newCase(bilal, sp, uniq("Invoice total"));
  const b = await newCase(bilal, sp, uniq("Invoice tax"));
  const plan = await planWithCycle(bilal, sp, [a.id, b.id]);
  await execute(sana, plan.runs[0] ?? "", "passed");
  await execute(sana, plan.runs[1] ?? "", "failed");

  const ayesha = await as(browser, "ayesha");
  await ayesha.goto(`/p/${sp.key}/releases`);
  const list = ayesha.getByRole("table", { name: "Releases" });
  await expect(list.getByRole("row", { name: new RegExp(sp.release.name) })).toContainText("Not ready");
  await expectAccessible(ayesha);
  await list.getByRole("link", { name: sp.release.name }).click();
  const rules = ayesha.getByRole("table", { name: "Readiness rules" });
  await expect(rules.getByRole("row")).toHaveCount(3);
  await expect(rules.getByRole("row", { name: /No failed runs/ })).toContainText("Not met");
  await expect(rules.getByRole("row", { name: /Execution progress/ })).toContainText("2 of 2 (100%)");
  await expectAccessible(ayesha);

  // The plan Overview shows the same rules (L25).
  await bilal.goto(`/p/${sp.key}/plans/${plan.key}`);
  await expect(
    bilal.getByRole("table", { name: "Readiness rules" }).getByRole("row", { name: /No failed runs/ }),
  ).toContainText("Not met");

  // Retest passes: Ready; Ayesha records Go and sees it in the timeline with its snapshot.
  await execute(sana, plan.runs[1] ?? "", "passed");
  await ayesha.reload();
  await expect(ayesha.getByRole("main").getByText("Ready", { exact: true }).first()).toBeVisible();
  await ayesha.getByRole("button", { name: "Record decision…" }).click();
  const dialog = ayesha.getByRole("dialog", { name: /Record decision/ });
  await dialog.getByLabel("Go", { exact: true }).check();
  await dialog.getByLabel(/Comment/).fill("All exit rules met after the retest.");
  await dialog.getByRole("button", { name: "Record decision" }).click();
  await ayesha.getByRole("tab", { name: /Decisions/ }).click();
  const timeline = ayesha.getByRole("list", { name: "Decisions" });
  await expect(timeline).toContainText("All exit rules met after the retest.");
  await timeline.getByRole("button", { name: "Show snapshot" }).click();
  await expect(timeline.getByRole("table", { name: "Readiness rules" }).getByRole("row")).toHaveCount(3);
  await expectAccessible(ayesha);
});

test("TCMS-115: the Overview shows execution, bugs, team and readiness for the release", async ({
  browser,
}) => {
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const sana = await as(browser, "sana");
  const c = await newCase(bilal, sp, uniq("Refund"));
  const plan = await planWithCycle(bilal, sp, [c.id]);
  await execute(sana, plan.runs[0] ?? "", "failed");
  await bilal.goto(`/p/${sp.key}`);
  await bilal.getByLabel("Release", { exact: true }).selectOption(sp.release.id);
  await expect(bilal.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(bilal.getByRole("table", { name: "Team progress" })).toContainText("Sana Malik");
  await expect(bilal.getByText("Failures without a bug")).toBeVisible();
  await expect(bilal.getByText(/rules met/)).toBeVisible();
  await expectAccessible(bilal);
  await bilal.getByRole("button", { name: "View data" }).first().click();
  await expect(bilal.getByRole("table", { name: "Status by cycle data" })).toBeVisible();
});

test("TCMS-117: export the cycle execution report; formulas are escaped", async ({ browser }) => {
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const c = await newCase(bilal, sp, `=SUM(1,2) ${uniq("x")}`);
  await planWithCycle(bilal, sp, [c.id]);
  await bilal.goto(`/p/${sp.key}/reports?tab=cycle-execution`);
  const table = bilal.getByRole("table", { name: "Cycle execution report" });
  await expect(table).toContainText(c.key);
  await expectAccessible(bilal);
  const download = bilal.waitForEvent("download");
  await bilal.getByRole("button", { name: "CSV" }).click();
  const file = await download;
  const text = await (await file.createReadStream()).toArray();
  const csv = Buffer.concat(text as Buffer[]).toString("utf8");
  expect(csv).toContain("'=SUM(1,2)");
  await bilal.goto(`/p/${sp.key}/reports`);
  await expect(bilal.getByRole("table", { name: "Release-wise quality" })).toBeVisible();
  await expectAccessible(bilal);
});

test("My Work lists my failed runs and what I did today", async ({ browser }) => {
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const sana = await as(browser, "sana");
  const c = await newCase(bilal, sp, uniq("Discount code"));
  const plan = await planWithCycle(bilal, sp, [c.id]);
  await execute(sana, plan.runs[0] ?? "", "failed");
  await sana.goto("/my-work");
  await expect(sana.getByRole("heading", { name: /Failed, blocked or to retest/ })).toBeVisible();
  await expect(sana.getByRole("link", { name: c.key })).toBeVisible();
  await expectAccessible(sana);
});
