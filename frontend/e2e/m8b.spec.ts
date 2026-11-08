import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M8b journeys: Administration (US-162…165, TCMS-133, TCMS-139) and the project audit log.

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

async function as(browser: Browser, user: "ayesha" | "sana" | "zain"): Promise<Page> {
  const context = await browser.newContext({ storageState: `e2e/.auth/${user}.json` });
  return context.newPage();
}

test("US-162…165: an administrator manages users, reads the audit log, reviews access and the system", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  const page = await as(browser, "zain"); // signed in with MFA by e2e/auth.setup.ts

  // Users (US-164): the sidebar opens Administration on its first tab.
  await page.goto("/my-work");
  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Administration" })
    .click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.getByRole("heading", { name: "Users", level: 1 })).toBeVisible();
  const users = page.getByRole("table", { name: "Users" });
  const email = page.getByLabel("Filter Email");
  await email.fill("sana@acme.test");
  const sana = users.getByRole("row").filter({ hasText: "sana@acme.test" });
  await expect(sana).toContainText("SPARK");
  await expect(sana).toContainText("QA Engineer");
  await expectAccessible(page);
  await email.fill("zain@acme.test");
  await users
    .getByRole("row")
    .filter({ hasText: "zain@acme.test" })
    .getByRole("button", { name: "Actions for Zain Ali" })
    .click();
  await expect(page.getByRole("menuitem", { name: /Deactivate/ })).toHaveAttribute("data-disabled", "");
  await expect(page.getByRole("menuitem", { name: /Deactivate/ })).toContainText(
    "You cannot deactivate yourself",
  );
  await page.keyboard.press("Escape");
  await email.fill("faisal@acme.test");
  await users
    .getByRole("row")
    .filter({ hasText: "faisal@acme.test" })
    .getByRole("button", { name: "Actions for Faisal Ahmed" })
    .click();
  await expect(page.getByRole("menuitem", { name: /Reset two-step/ })).toContainText("Not set up");
  await page.getByRole("menuitem", { name: "Sign out everywhere" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByText(/session\(s\) ended/)).toBeVisible();

  // Roles: the read-only matrix.
  const tabs = page.getByRole("navigation", { name: "Administration" });
  await tabs.getByRole("link", { name: "Roles" }).click();
  const matrix = page.getByRole("table", { name: "Role permissions" });
  await expect(matrix.getByRole("row", { name: /Execute runs/ })).toBeVisible();
  await expectAccessible(page);

  // Audit log (US-162): find the sign-out just recorded and open it.
  await tabs.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
  await page.getByLabel("Filter Event").fill("out everywhere");
  const event = page
    .getByRole("table", { name: "Audit events" })
    .getByRole("row", { name: /signed faisal@acme\.test out everywhere/ });
  await expect(page.getByText(/^\d+ events?$/)).toBeVisible();
  await expect(event.first()).toBeVisible();
  await expectAccessible(page);
  await event.first().click();
  const detail = page.getByRole("dialog");
  await expect(detail.getByRole("region", { name: "Request" })).toContainText("request id");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  const csv = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export CSV" }).click();
  expect((await csv).suggestedFilename()).toMatch(/^audit-log-.*\.csv$/);

  // Access review (TCMS-133).
  await tabs.getByRole("link", { name: "Access review" }).click();
  const review = page.getByRole("table", { name: "Access review" });
  await page.getByLabel("Filter Person").fill("sana@acme.test");
  const sanaRows = review.getByRole("row").filter({ hasText: "sana@acme.test" });
  await expect(sanaRows.filter({ hasText: "Organization" })).toContainText("Member");
  await page.getByLabel("Filter Scope").fill("SPARK Platform");
  await expect(sanaRows).toHaveCount(1);
  await expect(sanaRows).toContainText("QA Engineer");
  await expectAccessible(page);
  const xlsx = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export XLSX" }).click();
  expect((await xlsx).suggestedFilename()).toMatch(/^access-review-.*\.xlsx$/);

  // System (US-165, TCMS-139): health and the seeded failed job, retried.
  await tabs.getByRole("link", { name: "System" }).click();
  await expect(page.getByRole("list", { name: "Health checks" })).toContainText("Database: OK");
  const failed = page.getByRole("table", { name: "Failed jobs" });
  await expect(failed).toContainText("seed.example");
  await expectAccessible(page);
  await failed.getByRole("button", { name: "Retry seed.example" }).first().click();
  await expect(page.getByText("seed.example queued again")).toBeVisible();
});

test("project audit log: a QA Manager opens it from Activity; an engineer has no link", async ({
  browser,
}) => {
  const ayesha = await as(browser, "ayesha");
  await ayesha.goto("/p/SPARK/activity");
  await ayesha.getByRole("link", { name: "Audit log" }).click();
  await expect(ayesha).toHaveURL(/\/p\/SPARK\/audit$/);
  await expect(ayesha.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
  await expect(ayesha.getByRole("table", { name: "Audit events" }).getByRole("row").nth(1)).toBeVisible();
  await expect(ayesha.getByRole("columnheader", { name: "Project" })).toHaveCount(0);
  await expectAccessible(ayesha);

  const sana = await as(browser, "sana");
  await sana.goto("/p/SPARK/activity");
  await expect(sana.getByRole("heading", { name: "Activity", level: 1 })).toBeVisible();
  await expect(sana.getByRole("link", { name: "Audit log" })).toHaveCount(0);
});
