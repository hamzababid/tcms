import { expect, test as setup } from "@playwright/test";

// One sign-in per seed user for the M2+ journeys; they reuse the session (storageState) so the
// suite stays under the public auth rate limit (RATE_LIMIT_AUTH_PER_MIN, docs/ops/environment.md).
const PASSWORD = "Passw0rd!Passw0rd"; // documented seed credential (docs/ops/local-setup.md)

for (const user of ["bilal", "sana"]) {
  setup(`sign in ${user}`, async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(`${user}@acme.test`);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL((u) => u.pathname !== "/login");
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    await page.context().storageState({ path: `e2e/.auth/${user}.json` });
  });
}
