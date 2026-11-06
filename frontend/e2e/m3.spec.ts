import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M3 journeys: plans and cycles (docs/08 TCMS-050…060, AC-PLN-01/02). Seed users from e2e/auth.setup.ts.
const run = Date.now().toString(36);
let seq = 0;
// Workers are separate processes: add randomness so names stay unique across them.
const uniq = (label: string) => `${label} ${run}${Math.random().toString(36).slice(2, 6)}-${++seq}`;

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

interface Ref {
  id: string;
  key: string;
}

async function spark(page: Page): Promise<string> {
  const projects = await call<Ref[]>(page, "GET", "/api/v1/projects");
  const p = projects.find((x) => x.key === "SPARK");
  if (!p) throw new Error("SPARK not visible");
  return p.id;
}

async function environment(page: Page, pid: string): Promise<{ id: string; name: string }> {
  const envs = await call<{ id: string; name: string; archived: boolean }[]>(
    page,
    "GET",
    `/api/v1/projects/${pid}/environments`,
  );
  const env = envs.find((e) => !e.archived);
  if (!env) throw new Error("SPARK has no environment");
  return env;
}

async function folder(page: Page, pid: string, name: string): Promise<string> {
  return (await call<{ id: string }>(page, "POST", `/api/v1/projects/${pid}/folders`, { name })).id;
}

async function testCase(
  page: Page,
  pid: string,
  folderId: string,
  title: string,
): Promise<Ref & { row_version: number }> {
  const r = await call<{ case: Ref & { row_version: number } }>(
    page,
    "POST",
    `/api/v1/projects/${pid}/test-cases`,
    {
      folder_id: folderId,
      content: { format: "steps", title, steps: [{ action: "Do it", expected_result: "It works" }] },
    },
  );
  return r.case;
}

async function plan(page: Page, pid: string, caseIds: string[]): Promise<Ref & { name: string }> {
  const name = uniq("Plan");
  const p = await call<Ref & { name: string }>(page, "POST", `/api/v1/projects/${pid}/test-plans`, {
    name,
    type: "regression",
  });
  if (caseIds.length) await call(page, "POST", `/api/v1/test-plans/${p.id}/cases`, { case_ids: caseIds });
  return p;
}

async function cycle(
  page: Page,
  pid: string,
  body: { plan_id?: string; selection: Record<string, unknown> },
): Promise<Ref & { name: string }> {
  const env = await environment(page, pid);
  const name = uniq("Cycle");
  const r = await call<{ cycle: Ref & { name: string } }>(page, "POST", `/api/v1/projects/${pid}/cycles`, {
    name,
    environment_id: env.id,
    ...body,
  });
  return r.cycle;
}

test("TCMS-050: create a plan with exit criteria and risks, then activate it", async ({ browser }) => {
  const page = await as(browser, "bilal");
  await page.goto("/p/SPARK/plans");
  await expect(page.getByRole("heading", { name: "Test plans" })).toBeVisible();
  await expectAccessible(page);

  const name = uniq("Release plan");
  await page.getByRole("button", { name: "New plan" }).click();
  const dialog = page.getByRole("dialog", { name: "New test plan" });
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Type").selectOption("regression");
  await dialog.getByLabel("Start date").fill("2026-11-03");
  await dialog.getByLabel("End date").fill("2026-11-14");
  await dialog.getByLabel("Objectives").fill("Verify the **v2.5** release");
  await dialog.getByLabel("Add exit rule").selectOption("min_execution_progress");
  await dialog.getByLabel("Add exit rule").selectOption("max_failed");
  await dialog.getByLabel("Rule 2 threshold").fill("0");
  await dialog.getByRole("button", { name: "Risk", exact: true }).click();
  await dialog.getByLabel("Risk 1 description").fill("Telemetry feed unstable");
  await dialog.getByLabel("Risk 1 impact").selectOption("high");
  await dialog.getByLabel("Risk 1 mitigation").fill("Replay recorded data");
  await expectAccessible(page);
  await dialog.getByRole("button", { name: "Create" }).click();

  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.locator("[data-status=draft]").first()).toBeVisible();
  await expect(page.getByText("Execution progress ≥ 100%")).toBeVisible();
  await expect(page.getByText("No failed runs")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Telemetry feed unstable" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "High" })).toBeVisible();

  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.locator("[data-status=active]").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark completed" })).toBeVisible();
  await expectAccessible(page);
});

test("TCMS-051 + AC-PLN-01: add cases to a plan, then create a cycle from it with skipped cases", async ({
  browser,
}) => {
  const page = await as(browser, "bilal");
  const pid = await spark(page);
  const folderName = uniq("Plan cases");
  const f = await folder(page, pid, folderName);
  const cases = [
    await testCase(page, pid, f, uniq("Login works")),
    await testCase(page, pid, f, uniq("Logout works")),
    await testCase(page, pid, f, uniq("Retired flow")),
  ];
  const p = await plan(page, pid, []);
  await page.goto(`/p/SPARK/plans/${p.key}`);
  await page.getByRole("tab", { name: /Cases/ }).click();
  await page.getByRole("button", { name: "Add cases" }).first().click();
  let dialog = page.getByRole("dialog", { name: `Add cases to ${p.key}` });
  await dialog.getByRole("checkbox", { name: folderName }).check();
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog.getByText("Added 3 cases")).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("tab", { name: /Cases/ })).toContainText("3");

  // Adding again skips them with a reason (BR-12 duplicates).
  await page.getByRole("button", { name: "Add cases" }).first().click();
  dialog = page.getByRole("dialog", { name: `Add cases to ${p.key}` });
  await dialog.getByRole("checkbox", { name: folderName }).check();
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog.getByText("Added 0 cases · skipped 3")).toBeVisible();
  await expect(dialog.getByText("already in the plan").first()).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();

  // One plan case is archived before the cycle is built: it is skipped (BR-13).
  const retired = cases[2] as Ref;
  await call(page, "POST", `/api/v1/projects/${pid}/test-cases/bulk`, {
    action: "archive",
    case_ids: [retired.id],
  });

  await page.getByRole("tab", { name: /Cycles/ }).click();
  await page.getByRole("button", { name: "Create cycle" }).first().click();
  const create = page.getByRole("dialog", { name: "New cycle" });
  await expect(create.getByLabel("Name")).toHaveValue(`${p.name} – Cycle 1`);
  await expect(create.getByRole("combobox", { name: "Plan", exact: true })).toHaveValue(p.id);
  const env = await environment(page, pid);
  await create.getByLabel("Environment").selectOption(env.id);
  await expectAccessible(page);
  await create.getByRole("button", { name: "Create" }).click();

  const result = page.getByRole("dialog", { name: /SPARK-CY-\d+ created/ });
  await expect(result.getByText("Added 2 runs · skipped 1")).toBeVisible();
  await expect(result.getByText(retired.key)).toBeVisible();
  await expect(result.getByText("archived", { exact: true })).toBeVisible();
  await result.getByRole("button", { name: "Open cycle" }).click();

  await expect(page.getByRole("heading", { name: `${p.name} – Cycle 1` })).toBeVisible();
  await expect(page.getByText(/Executed/).first()).toBeVisible();
  await expect(page.getByRole("table", { name: "Runs" }).locator("tbody tr")).toHaveCount(2);
  await expectAccessible(page);
});

test("TCMS-055 + TCMS-056: assign a folder to a tester, then a tester claims a pool run", async ({
  browser,
}) => {
  const bilal = await as(browser, "bilal");
  const pid = await spark(bilal);
  const fa = await folder(bilal, pid, uniq("Assign A"));
  const fb = await folder(bilal, pid, uniq("Assign B"));
  const a1 = await testCase(bilal, pid, fa, uniq("A one"));
  const a2 = await testCase(bilal, pid, fa, uniq("A two"));
  const b1 = await testCase(bilal, pid, fb, uniq("B one"));
  const c = await cycle(bilal, pid, { selection: { from_plan: false, folder_ids: [fa, fb] } });
  await call(bilal, "POST", `/api/v1/cycles/${c.id}/start`);

  await bilal.goto(`/p/SPARK/cycles/${c.key}`);
  await expect(bilal.getByRole("heading", { name: c.name })).toBeVisible();
  await bilal.getByRole("button", { name: "Assign" }).first().click();
  await bilal.getByRole("menuitem", { name: "Assign a folder…" }).click();
  const dialog = bilal.getByRole("dialog", { name: `Assign a folder in ${c.key}` });
  await dialog.getByLabel("Folder").selectOption(fa);
  await dialog.getByLabel("Assignee").selectOption({ label: "Sana Malik" });
  await dialog.getByRole("button", { name: "Assign" }).click();
  await expect(bilal.getByText("Assigned 2 runs to Sana Malik")).toBeVisible();

  const runs = bilal.getByRole("table", { name: "Runs" });
  await expect(runs.getByRole("row", { name: new RegExp(a1.key) })).toContainText("Sana Malik");
  await expect(runs.getByRole("row", { name: new RegExp(a2.key) })).toContainText("Sana Malik");
  await expect(runs.getByRole("row", { name: new RegExp(b1.key) })).toContainText("— pool —");
  await expectAccessible(bilal);

  const sana = await as(browser, "sana");
  await sana.goto(`/p/SPARK/cycles/${c.key}`);
  await sana.getByRole("button", { name: `Claim ${b1.key}` }).click();
  await expect(sana.getByText(`${b1.key} is yours`)).toBeVisible();
  await expect(
    sana.getByRole("table", { name: "Runs" }).getByRole("row", { name: new RegExp(b1.key) }),
  ).toContainText("Sana Malik");
  // Filter "Me" shows all three now.
  await sana.getByLabel("Filter Assignee").selectOption("me");
  await expect(sana.getByRole("table", { name: "Runs" }).locator("tbody tr")).toHaveCount(3);
  await expectAccessible(sana);
});

test("TCMS-058 + TCMS-059 + TCMS-060: close, reopen with a reason, and clone a cycle", async ({
  browser,
}) => {
  const bilal = await as(browser, "bilal");
  const pid = await spark(bilal);
  const f = await folder(bilal, pid, uniq("Lifecycle"));
  await testCase(bilal, pid, f, uniq("Lifecycle one"));
  await testCase(bilal, pid, f, uniq("Lifecycle two"));
  const c = await cycle(bilal, pid, { selection: { from_plan: false, folder_ids: [f] } });

  await bilal.goto(`/p/SPARK/cycles/${c.key}`);
  await bilal.getByRole("button", { name: "Start cycle" }).click();
  await expect(bilal.locator("[data-status=active]").first()).toBeVisible();

  await bilal.getByRole("button", { name: "More cycle actions" }).click();
  await bilal.getByRole("menuitem", { name: "Close cycle" }).click();
  const close = bilal.getByRole("dialog", { name: `Close ${c.key}?` });
  await expect(close.getByText("2 runs are not run yet and stay not run.")).toBeVisible();
  await close.getByRole("button", { name: "Close cycle" }).click();
  await expect(bilal.getByText(/Closed by Bilal Khan on/)).toBeVisible();
  await expect(bilal.getByRole("button", { name: "Add cases" })).toHaveCount(0);
  // QA Leads cannot reopen (cycle.reopen is QA Manager only).
  await expect(bilal.getByRole("button", { name: "Reopen" })).toHaveCount(0);
  await expectAccessible(bilal);

  const ayesha = await as(browser, "ayesha");
  await ayesha.goto(`/p/SPARK/cycles/${c.key}`);
  await ayesha.getByRole("button", { name: "Reopen" }).first().click();
  const reopen = ayesha.getByRole("dialog", { name: `Reopen ${c.key}` });
  await reopen.getByLabel("Reason").fill("Hotfix build 2.5.1 needs a re-run");
  await reopen.getByRole("button", { name: "Reopen" }).click();
  await expect(ayesha.locator("[data-status=active]").first()).toBeVisible();
  await ayesha.getByRole("tab", { name: "History" }).click();
  await expect(ayesha.getByRole("table", { name: "History" })).toContainText(/reopen/i);

  await bilal.reload();
  await bilal.getByRole("button", { name: "More cycle actions" }).click();
  await bilal.getByRole("menuitem", { name: "Clone cycle" }).click();
  const clone = bilal.getByRole("dialog", { name: `Clone ${c.key}` });
  const cloneName = uniq("Clone");
  await clone.getByLabel("Name").fill(cloneName);
  await clone.getByLabel("Not run").check();
  await clone.getByRole("button", { name: "Clone" }).click();
  const done = bilal.getByRole("dialog", { name: /SPARK-CY-\d+ created/ });
  await expect(done.getByText("Added 2 runs")).toBeVisible();
  await done.getByRole("button", { name: "Open cycle" }).click();
  await expect(bilal.getByRole("heading", { name: cloneName })).toBeVisible();
  await expect(bilal.locator("[data-status=planned]").first()).toBeVisible();
});

test("TCMS-053: sync from plan adds the plan's new cases", async ({ browser }) => {
  const page = await as(browser, "bilal");
  const pid = await spark(page);
  const f = await folder(page, pid, uniq("Sync"));
  const first = await testCase(page, pid, f, uniq("Sync one"));
  const p = await plan(page, pid, [first.id]);
  const c = await cycle(page, pid, { plan_id: p.id, selection: { from_plan: true } });
  const second = await testCase(page, pid, f, uniq("Sync two"));
  await call(page, "POST", `/api/v1/test-plans/${p.id}/cases`, { case_ids: [second.id] });

  await page.goto(`/p/SPARK/cycles/${c.key}`);
  await expect(page.getByRole("link", { name: p.key })).toBeVisible();
  const runs = page.getByRole("table", { name: "Runs" });
  await expect(runs.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "More cycle actions" }).click();
  await page.getByRole("menuitem", { name: "Sync from plan" }).click();
  await expect(page.getByText(`Added 1 new case from ${p.key}`)).toBeVisible();
  await expect(runs.getByRole("row", { name: new RegExp(second.key) })).toBeVisible();

  // The plan shows the cycle with its progress.
  await page.getByRole("link", { name: p.key }).click();
  await page.getByRole("tab", { name: /Cycles/ }).click();
  await expect(page.getByRole("table", { name: "Cycles from this plan" })).toContainText(c.key);
  await expectAccessible(page);
});

test("BR-04: a not-run run moves to the newer case version from the run panel", async ({ browser }) => {
  const page = await as(browser, "bilal");
  const pid = await spark(page);
  const f = await folder(page, pid, uniq("Versions"));
  const tc = await testCase(page, pid, f, uniq("Versioned"));
  const c = await cycle(page, pid, { selection: { from_plan: false, case_ids: [tc.id] } });
  await call(page, "PUT", `/api/v1/test-cases/${tc.id}/content`, {
    row_version: tc.row_version,
    change_note: "Clarified the expected result",
    content: {
      format: "steps",
      title: "Versioned v2",
      steps: [{ action: "Do it", expected_result: "It works fast" }],
    },
  });

  await page.goto(`/p/SPARK/cycles/${c.key}`);
  const row = page.getByRole("table", { name: "Runs" }).getByRole("row", { name: new RegExp(tc.key) });
  await expect(row).toContainText("v1↑");
  await row.getByText(tc.key).click();
  const panel = page.getByRole("complementary", { name: `${tc.key} details` });
  await expect(panel.getByText("v2 available (you are on v1)")).toBeVisible();
  await expectAccessible(page);
  await panel.getByRole("button", { name: "Update to v2" }).click();
  await expect(page.getByText("Updated to v2")).toBeVisible();
  await expect(row).toContainText("v2");
  await expect(row).not.toContainText("↑");
  await expect(page).toHaveURL(/\?run=/);
});

test("seeded demo: SPARK-PL-1 and SPARK-CY-1 open from the lists", async ({ browser }) => {
  const page = await as(browser, "sana");
  await page.goto("/p/SPARK/plans");
  // Other journeys add plans and cycles: filter to the seeded ones.
  await page.getByLabel("Filter Name").fill("SPARK v2.5 regression");
  await page
    .getByRole("table", { name: "Test plans" })
    .getByRole("row", { name: /SPARK-PL-1\b/ })
    .click();
  await expect(page).toHaveURL(/\/plans\/SPARK-PL-1$/);
  await expect(page.getByRole("tab", { name: /Cases/ })).toBeVisible();
  await expect(page.getByText("Exit criteria")).toBeVisible();
  // Sana (QA Engineer) cannot manage plans.
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);

  await page.keyboard.press("g");
  await page.keyboard.press("c");
  await expect(page).toHaveURL(/\/p\/SPARK\/cycles$/);
  await page.getByLabel("Filter Name").fill("Regression Cycle 1");
  await page
    .getByRole("table", { name: "Test cycles" })
    .getByRole("row", { name: /SPARK-CY-1\b/ })
    .click();
  await expect(page).toHaveURL(/\/cycles\/SPARK-CY-1$/);
  await expect(page.getByRole("list", { name: "Runs by status" })).toBeVisible();
  await page.getByRole("button", { name: "By assignee" }).click();
  await expect(page.getByRole("table", { name: "Progress by assignee" })).toContainText("Sana Malik");
  await expectAccessible(page);
});

test("repository bulk actions: add selected cases to a plan and to a cycle", async ({ browser }) => {
  const page = await as(browser, "bilal");
  const pid = await spark(page);
  const f = await folder(page, pid, uniq("Bulk add"));
  const one = await testCase(page, pid, f, uniq("Bulk one"));
  const two = await testCase(page, pid, f, uniq("Bulk two"));
  const p = await plan(page, pid, []);
  const c = await cycle(page, pid, { selection: { from_plan: false } });

  await page.goto(`/p/SPARK/repository?folder=${f}`);
  await page.getByLabel(`Select ${one.key}`).check();
  await page.getByLabel(`Select ${two.key}`).check();
  const bar = page.getByRole("region", { name: "Bulk actions" });

  await bar.getByRole("button", { name: "Add to plan" }).click();
  let dialog = page.getByRole("dialog", { name: "Add 2 cases to a plan" });
  await dialog.getByLabel("Plan").selectOption(p.id);
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog.getByText("Added 2 cases")).toBeVisible();
  await expectAccessible(page);
  await dialog.getByRole("button", { name: "Done" }).click();

  await page.getByLabel(`Select ${one.key}`).check();
  await page
    .getByRole("region", { name: "Bulk actions" })
    .getByRole("button", { name: "Add to cycle" })
    .click();
  dialog = page.getByRole("dialog", { name: "Add 1 case to a cycle" });
  await dialog.getByLabel("Cycle (not closed)").selectOption(c.id);
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog.getByText("Added 1 run")).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();

  const plans = await call<{ total: number }>(page, "GET", `/api/v1/test-plans/${p.id}/cases`);
  expect(plans.total).toBe(2);
  const runs = await call<{ total: number }>(page, "GET", `/api/v1/cycles/${c.id}/runs`);
  expect(runs.total).toBe(1);
});
