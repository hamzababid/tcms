import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M8a journeys: the import wizard (TCMS-134, AC-IMP-01) and exports (AC-IMP-02). Each worker makes its
// own project.

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

async function as(browser: Browser, user: "ayesha" | "bilal" | "sana"): Promise<Page> {
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

let projectKey: string | null = null;

async function project(browser: Browser): Promise<string> {
  if (projectKey) return projectKey;
  const ayesha = await as(browser, "ayesha");
  const key = `I${run.slice(-8)}`.replace(/[^A-Z0-9]/g, "X").slice(0, 10);
  await call(ayesha, "POST", "/api/v1/projects", { key, name: uniq("Imports") });
  await ayesha.context().close();
  projectKey = key;
  return key;
}

async function projectId(page: Page, key: string): Promise<string> {
  const all = await call<{ id: string; key: string }[]>(page, "GET", "/api/v1/projects");
  return all.find((p) => p.key === key)?.id ?? "";
}

const CSV = [
  "ID,Summary,Module,Prio,Step,Expected",
  ",Pay by card,Checkout/Payments,P1,Open checkout,Form shown",
  ",,,,Enter card,Accepted",
  ",Pay by voucher,Checkout/Payments,Sometimes,Enter code,Discount applied",
].join("\n");

test("TCMS-134 / AC-IMP-01: the wizard maps, reports the bad row, imports the rest", async ({ browser }) => {
  test.setTimeout(60_000);
  const key = await project(browser);
  const ayesha = await as(browser, "ayesha");
  await ayesha.goto(`/p/${key}/repository`);
  await ayesha.getByRole("button", { name: "Import", exact: true }).click();
  await expect(ayesha.getByRole("heading", { name: "Import test cases" })).toBeVisible();
  await ayesha.getByLabel("File to import").setInputFiles({
    name: "cases.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV),
  });
  const mapping = ayesha.getByRole("table", { name: "Column mapping" });
  await expect(ayesha.getByLabel("Field for column Summary")).toHaveValue("title");
  await expect(mapping).toContainText("Pay by card");
  await expectAccessible(ayesha);
  await ayesha.getByRole("button", { name: "Validate →" }).click();
  const counts = ayesha.getByLabel("Validation counts");
  await expect(counts).toContainText("Create 1");
  await expect(counts).toContainText("Errors 1");
  const errors = ayesha.getByRole("table", { name: "Import errors" });
  await expect(errors).toContainText("Sometimes");
  await expect(ayesha.getByRole("button", { name: /^Import 1 cases/ })).toBeDisabled();
  await expectAccessible(ayesha);
  await ayesha.getByLabel("Skip rows with errors").check();
  await expect(ayesha.getByRole("button", { name: /^Import 1 cases/ })).toBeEnabled();
  await ayesha.getByRole("button", { name: /^Import 1 cases/ }).click();
  await expect(ayesha.getByRole("status").filter({ hasText: "1 created" })).toBeVisible({ timeout: 20_000 });
  await expect(ayesha.getByRole("link", { name: "Download the import report" })).toBeVisible();
  await ayesha.getByRole("link", { name: "Open the repository" }).click();
  await ayesha.getByRole("treeitem", { name: /Payments/ }).click();
  await expect(ayesha.getByText("Pay by card")).toBeVisible();
});

test("AC-IMP-02: export the repository and the requirement references", async ({ browser }) => {
  const key = await project(browser);
  const ayesha = await as(browser, "ayesha");
  const p = await call<{ id: string }>(ayesha, "GET", `/api/v1/projects/${await projectId(ayesha, key)}`);
  const folder = await call<{ id: string }>(ayesha, "POST", `/api/v1/projects/${p.id}/folders`, {
    name: uniq("Export"),
  });
  await call(ayesha, "POST", `/api/v1/projects/${p.id}/test-cases`, {
    folder_id: folder.id,
    content: {
      format: "steps",
      title: uniq("Exported case"),
      steps: [{ action: "Do", expected_result: "Done" }],
    },
  });
  await ayesha.goto(`/p/${key}/repository`);
  const download = ayesha.waitForEvent("download");
  await ayesha.getByRole("button", { name: "Export", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(new RegExp(`^${key}-test-cases-.*\\.xlsx$`));
  await ayesha.goto(`/p/${key}/requirements`);
  const refs = ayesha.waitForEvent("download");
  await ayesha.getByRole("button", { name: "Export", exact: true }).click();
  expect((await refs).suggestedFilename()).toMatch(/requirements-.*\.xlsx$/);
  await expect(ayesha.getByRole("link", { name: "Import", exact: true })).toBeVisible();
});
