import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M6 journeys: requirement references and traceability (ADR-024; TCMS-110…112), global search and the command
// palette (TCMS-118/119), saved views (TCMS-120). Each worker makes its own project with a release.
const run = (Date.now().toString(36) + Math.random().toString(36).slice(2, 6)).toUpperCase();
let seq = 0;
const uniq = (label: string) => `${label} ${run}-${++seq}`;
const ref = (p = "REQ") => `${p}-${run.slice(-4)}${++seq}`;

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
}

let space: Space | null = null;

/** Ayesha's project with Bilal (QA Lead) and Sana (QA Engineer), a release and a folder. */
async function project(browser: Browser): Promise<Space> {
  if (space) return space;
  const ayesha = await as(browser, "ayesha");
  const key = `R${run.slice(-8)}`.replace(/[^A-Z0-9]/g, "X").slice(0, 10);
  const p = await call<{ id: string; key: string }>(ayesha, "POST", "/api/v1/projects", {
    key,
    name: uniq("Traceability"),
  });
  const people = await call<{ id: string; email: string }[]>(
    ayesha,
    "GET",
    `/api/v1/projects/${p.id}/member-candidates`,
  );
  for (const [email, role] of [
    ["bilal@acme.test", "qa_lead"],
    ["sana@acme.test", "qa_engineer"],
  ] as const) {
    const u = people.find((x) => x.email === email);
    if (!u) throw new Error(`${email} cannot be added`);
    await call(ayesha, "POST", `/api/v1/projects/${p.id}/members`, { user_id: u.id, role_code: role });
  }
  const rel = await call<{ id: string; name: string }>(ayesha, "POST", `/api/v1/projects/${p.id}/releases`, {
    name: `v${run.slice(-3)}`,
  });
  const folder = await call<{ id: string }>(ayesha, "POST", `/api/v1/projects/${p.id}/folders`, {
    name: "Checkout",
  });
  await ayesha.context().close();
  space = { pid: p.id, key: p.key, release: rel, folder: folder.id };
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

test("UJ-7 / TCMS-110…112: a plan lists requirements, the matrix shows the gap, linking and running closes it", async ({
  browser,
}) => {
  test.setTimeout(60_000);
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const covered = ref();
  const gap = ref();
  const c = await newCase(bilal, sp, uniq("Pay with card"));
  const plan = await call<{ id: string; key: string }>(
    bilal,
    "POST",
    `/api/v1/projects/${sp.pid}/test-plans`,
    {
      name: uniq("Release plan"),
      type: "regression",
      release_id: sp.release.id,
    },
  );

  // The plan's Requirements tab: paste two references (TCMS-110 from the plan side).
  await bilal.goto(`/p/${sp.key}/plans/${plan.key}`);
  await bilal.getByRole("tab", { name: /Requirements/ }).click();
  await bilal.getByRole("button", { name: "Add requirements" }).click();
  const dialog = bilal.getByRole("dialog", { name: "Link requirements" });
  await dialog.getByLabel(/Requirement references/).fill(`${covered}, ${gap}`);
  await dialog.getByRole("button", { name: "Link" }).click();
  const planTable = bilal.getByRole("table", { name: "Plan requirements" });
  await expect(planTable.getByRole("row")).toHaveCount(3);
  await expect(planTable.getByText("Not covered")).toHaveCount(2);
  await expectAccessible(bilal);

  // Link the case from the case page (TCMS-110 from the case side).
  await bilal.goto(`/p/${sp.key}/cases/${c.key}`);
  await bilal.getByRole("tab", { name: "Requirements" }).click();
  await bilal.getByRole("button", { name: "Link requirement" }).click();
  const link = bilal.getByRole("dialog", { name: "Link requirements" });
  await link.getByLabel(/Requirement references/).fill(covered);
  await link.getByRole("button", { name: "Link" }).click();
  await expect(bilal.getByText(covered, { exact: true })).toBeVisible();

  // TCMS-112: the matrix for the release shows the gap and the not-yet-run requirement.
  await bilal.goto(`/p/${sp.key}/traceability`);
  await bilal.getByLabel("Release", { exact: true }).selectOption(sp.release.id);
  const matrix = bilal.getByRole("table", { name: "Traceability matrix" });
  const coveredRow = matrix.getByRole("row", { name: new RegExp(covered) });
  const gapRow = matrix.getByRole("row", { name: new RegExp(gap) });
  await expect(coveredRow.getByRole("cell").nth(2)).toHaveText(/Not run/);
  await expect(gapRow.getByRole("cell").nth(2)).toHaveText(/Not covered/);
  await expect(bilal.getByLabel("Coverage summary")).toContainText("Coverage 1 of 2 (50%)");
  await bilal.getByLabel("Uncovered only").check();
  await expect(matrix.getByRole("row")).toHaveCount(2);
  await bilal.getByLabel("Uncovered only").uncheck();
  await expectAccessible(bilal);

  // Execute the case in a cycle of the release: the requirement passes.
  const envs = await call<{ id: string }[]>(bilal, "GET", `/api/v1/projects/${sp.pid}/environments`);
  const cyc = await call<{ cycle: { id: string } }>(bilal, "POST", `/api/v1/projects/${sp.pid}/cycles`, {
    name: uniq("Cycle"),
    environment_id: envs[0]?.id,
    release_id: sp.release.id,
    selection: { case_ids: [c.id] },
  });
  const runs = await call<{ items: { id: string }[] }>(bilal, "GET", `/api/v1/cycles/${cyc.cycle.id}/runs`);
  const res = await call<{ id: string; steps: { step_id: string }[] }>(
    bilal,
    "POST",
    `/api/v1/runs/${runs.items[0]?.id ?? ""}/results`,
    {},
  );
  await call(bilal, "PATCH", `/api/v1/results/${res.id}/steps/${res.steps[0]?.step_id ?? ""}`, {
    status: "passed",
  });
  await call(bilal, "POST", `/api/v1/results/${res.id}/finalize`, {});
  await bilal.reload();
  await bilal.getByLabel("Release", { exact: true }).selectOption(sp.release.id);
  await expect(coveredRow.getByRole("cell").nth(2)).toHaveText(/Passed/);
  await expect(bilal.getByLabel("Coverage summary")).toContainText("Verified 1 of 2 (50%)");

  // "Link cases" on the uncovered row opens the requirement with the case picker.
  await gapRow.getByRole("button", { name: /Link cases/ }).click();
  await expect(bilal.getByRole("dialog", { name: gap })).toBeVisible();
});

test("Requirements page: paste many, open one, see its cases", async ({ browser }) => {
  const sp = await project(browser);
  const ayesha = await as(browser, "ayesha");
  const a = ref("SPK");
  const b = ref("SPK");
  await ayesha.goto(`/p/${sp.key}/requirements`);
  await ayesha.getByRole("button", { name: "Add requirements" }).click();
  const dialog = ayesha.getByRole("dialog", { name: "Add requirements" });
  await dialog.getByLabel(/References/).fill(`${a}\n${b}`);
  await dialog.getByRole("button", { name: "Add" }).click();
  await expect(ayesha.getByText(/Added 2/)).toBeVisible();
  await ayesha.getByPlaceholder("Reference or title").fill(a);
  await ayesha.getByRole("table", { name: "Requirements" }).getByRole("row").filter({ hasText: a }).click();
  await expect(ayesha.getByRole("dialog", { name: a })).toContainText("No case covers this requirement yet.");
  await expectAccessible(ayesha);
});

test("TCMS-118 + palette: search by key opens the case; > lists actions", async ({ browser }) => {
  const sp = await project(browser);
  const sana = await as(browser, "sana");
  const c = await newCase(sana, sp, uniq("Refund a failed payment"));
  await sana.goto(`/p/${sp.key}/repository`);
  await expect(sana.getByRole("button", { name: /Search or type/ })).toBeVisible();
  await sana.keyboard.press("/");
  const search = sana.getByRole("dialog", { name: "Search" });
  await search.getByLabel("Search").fill(c.key);
  await expect(search.getByRole("option").first()).toContainText(c.key);
  await expectAccessible(sana);
  await sana.keyboard.press("Enter");
  await expect(sana).toHaveURL(new RegExp(`/cases/${c.key}$`));
  await sana.keyboard.press("/");
  await search.getByLabel("Search").fill("> trace");
  await expect(search.getByRole("option", { name: "Go to Traceability" })).toBeVisible();
  await sana.keyboard.press("Enter");
  await expect(sana).toHaveURL(/\/traceability$/);
});

test("TCMS-120: save a repository view, reopen it as the default", async ({ browser }) => {
  const sp = await project(browser);
  const sana = await as(browser, "sana");
  const title = uniq("Coupon edge case");
  await newCase(sana, sp, title);
  await newCase(sana, sp, uniq("Unrelated case"));
  await sana.goto(`/p/${sp.key}/repository`);
  await sana.getByPlaceholder("Key or text").first().fill("Coupon");
  await expect(sana.getByText(title)).toBeVisible();
  await expect(sana.getByText(/Unrelated case/)).toHaveCount(0);
  await sana.getByRole("button", { name: /Saved views/ }).click();
  await sana.getByRole("menuitem", { name: "Save current view…" }).click();
  const save = sana.getByRole("dialog", { name: "Save view" });
  await save.getByLabel("Name").fill("Coupons");
  await save.getByLabel("Open this list with this view").check();
  await save.getByRole("button", { name: "Save" }).click();
  await expect(sana.getByRole("button", { name: /Saved views/ })).toContainText("Coupons");
  await sana.reload();
  await expect(sana.getByRole("button", { name: /Saved views/ })).toContainText("Coupons");
  await expect(sana.getByText(/Unrelated case/)).toHaveCount(0);
  await expectAccessible(sana);
});
