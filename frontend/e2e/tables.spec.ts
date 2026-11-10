import { expect, test, type Browser, type Page } from "@playwright/test";

// Lists across the app share one table: filters, search, rows per page and page buttons behave the same
// (docs/07 §4.1). Seed users from e2e/auth.setup.ts.

async function as(browser: Browser, user: "ayesha" | "zain"): Promise<Page> {
  const context = await browser.newContext({ storageState: `e2e/.auth/${user}.json` });
  return context.newPage();
}

/** The footer of a list: count, rows per page and page buttons. */
function pager(page: Page, label: string) {
  return {
    size: page.getByRole("combobox", { name: "Rows per page" }),
    nav: page.getByRole("navigation", { name: `${label} pages` }),
  };
}

test("Administration lists page and filter like every other list", async ({ browser }) => {
  test.setTimeout(90_000);
  const page = await as(browser, "zain");

  // Users: long project lists are cut to a few chips, so the footer stays on screen.
  await page.goto("/admin/users");
  const users = page.getByRole("table", { name: "Users" });
  await expect(users.getByRole("row").nth(2)).toBeVisible();
  const p = pager(page, "Users");
  await expect(p.size).toHaveValue("50");
  await expect(p.nav).toBeVisible();
  await page.getByLabel("Filter Email").fill("sana@acme.test");
  const sana = users.getByRole("row").filter({ hasText: "sana@acme.test" });
  await expect(sana).toHaveCount(1);
  const box = await sana.boundingBox();
  expect(box?.height ?? 999).toBeLessThanOrEqual(80); // at most two lines of chips
  const more = sana.getByRole("button", { name: /more: Projects of Sana Malik/ });
  if (await more.count()) {
    await more.click();
    await expect(page.getByRole("dialog", { name: /Projects of Sana Malik/ })).toContainText("SPARK");
    await page.keyboard.press("Escape");
  }
  await p.size.selectOption("10");
  await expect(p.size).toHaveValue("10");

  // Audit log: the page goes back to 1 when a filter changes.
  await page.goto("/admin/audit");
  const audit = pager(page, "Audit events");
  await expect(page.getByRole("table", { name: "Audit events" }).getByRole("row").nth(2)).toBeVisible();
  await audit.size.selectOption("10");
  await audit.nav.getByRole("button", { name: "Next page" }).click();
  await expect(audit.nav).toContainText("Page 2 of");
  await page.getByLabel("Filter Event").fill("signed");
  await expect(audit.nav).toContainText("Page 1 of");

  // System › Failed jobs: status and job type filters; no dead sort buttons.
  await page.goto("/admin/system");
  const jobs = page.getByRole("table", { name: "Failed jobs" });
  await expect(jobs.getByRole("columnheader", { name: "Job" }).getByRole("button")).toHaveCount(0);
  await page.getByLabel("Filter Job").fill("seed.");
  await expect(jobs).toContainText("seed.example");
  await page.getByLabel("Filter Status").selectOption("dead");
  await expect(jobs).toContainText("No jobs match these filters.");
  await page.getByRole("button", { name: /Clear filters/ }).click();
  await expect(jobs).toContainText("seed.example");
});

test("the repository with the case panel open does not scroll the page", async ({ browser }) => {
  const page = await as(browser, "ayesha");
  await page.goto("/p/SPARK/repository");
  await page.locator("tbody tr[data-case]").first().click();
  await expect(page.getByRole("complementary", { name: /details/ })).toBeVisible();
  // Screen-reader-only labels in compact cells used to hang off the page and give it a blank scroll.
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight))
    .toBeLessThanOrEqual(0);
});

test("organization dashboard, releases and traceability have the shared filters and pager", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  const page = await as(browser, "ayesha");

  await page.goto("/org");
  const projects = page.getByRole("table", { name: "Projects" });
  await expect(projects.getByRole("row").nth(2)).toBeVisible();
  await expect(pager(page, "Projects").nav).toBeVisible();
  await page.getByLabel("Filter Project").fill("SPARK");
  await expect(projects.getByRole("row").filter({ hasText: "SPARK Platform" })).toHaveCount(1);

  await page.goto("/p/SPARK/releases");
  const releases = page.getByRole("table", { name: "Releases" });
  await expect(releases.getByRole("row").nth(2)).toBeVisible();
  // Filter by the first release's status: every row left has it.
  const status = (await releases.locator("tbody tr").first().locator("td").nth(1).innerText()).trim();
  await page.getByLabel("Filter Status").selectOption({ label: status });
  const shown = releases.locator("tbody tr");
  await expect(shown.first()).toContainText(status);
  for (const row of await shown.all()) await expect(row.locator("td").nth(1)).toHaveText(status);

  await page.goto("/p/SPARK/traceability");
  const matrix = pager(page, "Traceability matrix");
  await expect(matrix.nav).toBeVisible();
  await expect(matrix.size).toHaveValue("50");
  await page.getByLabel("Find requirement").fill("SPK-105");
  await expect(page.getByRole("table", { name: "Traceability matrix" }).getByRole("row")).toHaveCount(2);
});
