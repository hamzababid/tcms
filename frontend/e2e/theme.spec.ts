import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Dark theme (docs/07 §6.1): Light, Dark or System from the account menu or Profile › Appearance; saved
// with the profile; every screen stays accessible in dark.

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious, JSON.stringify(serious.map((v) => [v.id, v.nodes.map((n) => n.target)]))).toEqual([]);
}

const theme = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme);

async function setProfileTheme(page: Page, value: string) {
  const csrf = (await page.context().cookies()).find((c) => c.name === "tcms_csrf")?.value ?? "";
  const r = await page.request.patch("/api/v1/auth/me", {
    data: { theme: value },
    headers: { "X-CSRF-Token": csrf },
  });
  expect(r.ok()).toBe(true);
}

// Both tests change the same user's saved theme: run them one after the other.
test.describe.configure({ mode: "serial" });
test.use({ storageState: "e2e/.auth/bilal.json" });

test.afterEach(async ({ page }) => {
  await setProfileTheme(page, "system");
});

test("pick Dark from the account menu; it stays after a reload and screens pass axe", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/my-work");
  await expect(page.getByRole("heading", { name: "My Work", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect.poll(() => theme(page)).toBe("dark");
  await expect
    .poll(async () =>
      (await page.request.get("/api/v1/auth/me")).json().then((m: { theme: string }) => m.theme),
    )
    .toBe("dark");

  await page.reload();
  await expect(page.getByRole("heading", { name: "My Work", level: 1 })).toBeVisible();
  expect(await theme(page)).toBe("dark");
  await expectAccessible(page);
  for (const url of [
    "/p/SPARK/repository",
    "/p/SPARK/cycles/SPARK-CY-1",
    "/p/SPARK/reports",
    "/admin/users",
  ]) {
    await page.goto(url);
    await expect(page.locator("main h1").first()).toBeVisible();
    expect(await theme(page)).toBe("dark");
    await expectAccessible(page);
  }
});

test("System follows the device; Profile › Appearance switches it", async ({ browser }) => {
  const context = await browser.newContext({ storageState: "e2e/.auth/bilal.json", colorScheme: "dark" });
  const page = await context.newPage();
  await setProfileTheme(page, "system");
  await page.goto("/profile");
  await expect(page.getByRole("group", { name: "Theme" })).toBeVisible();
  await expect.poll(() => theme(page)).toBe("dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => theme(page)).toBe("light");

  await page.getByRole("radio", { name: /Dark/ }).check({ force: true });
  await expect.poll(() => theme(page)).toBe("dark");
  await expect(page.getByRole("radio", { name: /Dark/ })).toBeChecked();
  await page.getByRole("radio", { name: /Light/ }).check({ force: true });
  await expect.poll(() => theme(page)).toBe("light");
  await expectAccessible(page);
  await context.close();
});
