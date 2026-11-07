import { expect, test as setup } from "@playwright/test";
import * as OTPAuth from "otpauth";

// One sign-in per seed user for the M2+ journeys; they reuse the session (storageState) so the
// suite stays under the public auth rate limit (RATE_LIMIT_AUTH_PER_MIN, docs/ops/environment.md).
const PASSWORD = "Passw0rd!Passw0rd"; // documented seed credential (docs/ops/local-setup.md)
const ADMIN_TOTP = "ASSAYLOCALDEVTOTPSECRETONLY23456"; // documented local-only MFA secret

// Ayesha (QA Manager) is needed for cycle reopen (cycle.reopen, M3).
for (const user of ["ayesha", "bilal", "sana"]) {
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

// Zain (Org Admin, MFA) for the Administration journeys (M8b). Signing in once here keeps the specs from
// competing for the same single-use TOTP code while they run in parallel.
setup("sign in zain", async ({ request }) => {
  setup.setTimeout(120_000);
  const login = await request.post("/api/v1/auth/login", {
    data: { email: "zain@acme.test", password: PASSWORD },
  });
  expect(login.ok(), await login.text()).toBe(true);
  for (let attempt = 0; attempt < 3; attempt++) {
    const code = new OTPAuth.TOTP({
      secret: OTPAuth.Secret.fromBase32(ADMIN_TOTP),
      digits: 6,
      period: 30,
    }).generate();
    const verified = await request.post("/api/v1/auth/mfa/verify", { data: { code } });
    if (verified.status() === 204) {
      await request.storageState({ path: "e2e/.auth/zain.json" });
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 31_000)); // this step's code was already used
  }
  throw new Error("admin MFA verification failed");
});
