import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

// Seed credentials (docs/ops/local-setup.md; local/CI stacks only).
const PASSWORD = "Passw0rd!Passw0rd";
const ADMIN = { email: "zain@acme.test", totp: "ASSAYLOCALDEVTOTPSECRETONLY23456" };
const run = Date.now().toString(36);

function totp(secret: string): string {
  return new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 }).generate();
}

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

async function csrf(context: BrowserContext): Promise<Record<string, string>> {
  const cookie = (await context.cookies()).find((c) => c.name === "tcms_csrf");
  return cookie ? { "X-CSRF-Token": cookie.value } : {};
}

async function signIn(page: Page, email: string, password = PASSWORD, { expectSuccess = true } = {}) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  if (expectSuccess) await page.waitForURL((u) => u.pathname !== "/login");
}

/** Admin API session for setup steps (TOTP codes are single use: wait for a fresh step on replay). */
async function adminApi(request: APIRequestContext): Promise<void> {
  const login = await request.post("/api/v1/auth/login", {
    data: { email: ADMIN.email, password: PASSWORD },
  });
  expect(login.ok()).toBe(true);
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await request.post("/api/v1/auth/mfa/verify", { data: { code: totp(ADMIN.totp) } });
    if (r.status() === 204) return;
    await new Promise((resolve) => setTimeout(resolve, 31_000));
  }
  throw new Error("admin MFA verification failed");
}

test("TCMS-001: a member signs in and lands on their project (review K5)", async ({ page }) => {
  await signIn(page, "sana@acme.test");
  // With one project she lands on it; with several (and none remembered) on the project list.
  await expect(page).toHaveURL(/\/(p\/SPARK\/activity|projects)$/);
  await page.goto("/p/SPARK/activity");
  await expect(page.getByRole("heading", { name: /SPARK Platform · Activity/ })).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Settings" }),
  ).toHaveCount(0);
  await expectAccessible(page);
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await signIn(page, "sana@acme.test");
  await expect(page).toHaveURL(/\/p\/SPARK\/activity$/); // the last project is remembered
});

test("wrong password shows the generic message", async ({ page }) => {
  await signIn(page, "sana@acme.test", "definitely-wrong-1", { expectSuccess: false });
  await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
  await expectAccessible(page);
});

test("TCMS-008 + TCMS-004 + TCMS-005: invited admin enrols MFA, then signs in with a code", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  const email = `admin-${run}@acme.test`;
  const setup = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  await adminApi(setup.request);
  const invite = await setup.request.post("/api/v1/organization/invitations", {
    data: { email, is_org_admin: true },
    headers: await csrf(setup),
  });
  expect(invite.status(), await invite.text()).toBe(201);
  const acceptUrl = new URL(((await invite.json()) as { accept_url: string }).accept_url);
  await setup.close();

  // TCMS-008: accept the invitation.
  await page.goto(acceptUrl.pathname);
  await expect(page.getByRole("heading", { name: "Join ACME Energy" })).toBeVisible();
  await expectAccessible(page);
  await page.getByLabel(/^Your name/).fill("New Admin");
  await page.getByLabel(/^Password/).fill("Brand-New-Admin-Pass-1");
  await page.getByLabel(/^Confirm password/).fill("Brand-New-Admin-Pass-1");
  await page.getByRole("button", { name: "Accept and continue" }).click();

  // TCMS-004: forced enrolment before anything else.
  await expect(page).toHaveURL(/\/setup-mfa$/);
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/setup-mfa$/);
  const secret = (await page.getByLabel("Manual setup key").textContent())?.trim() ?? "";
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  await expectAccessible(page);
  await page.getByLabel("Verification code").fill(totp(secret));
  await page.getByRole("button", { name: "Verify and enable" }).click();
  await expect(page.getByRole("list", { name: "Recovery codes" }).getByRole("listitem")).toHaveCount(10);
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  await page.getByLabel("I've saved these codes").check();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/projects$/);

  // TCMS-005: sign out, sign in again with the authenticator code (next 30 s step to avoid replay).
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await new Promise((resolve) => setTimeout(resolve, 31_000));
  await signIn(page, email, "Brand-New-Admin-Pass-1");
  await expect(page).toHaveURL(/\/login\/mfa/);
  await expectAccessible(page);
  await page.getByLabel("Verification code").fill(totp(secret)); // auto-submits on 6 digits
  await expect(page).toHaveURL(/\/(projects|p\/)/);
});

test("TCMS-020: a QA Manager creates a project and becomes its QA Manager", async ({ page }) => {
  const key = `E${run
    .slice(-6)
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")}`.slice(0, 10);
  await signIn(page, "ayesha@acme.test");
  await page.goto("/projects");
  await expectAccessible(page);
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Key").fill(key.toLowerCase());
  await page.getByLabel("Name").fill(`E2E ${run}`);
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(new RegExp(`/p/${key}/settings$`));
  await expectAccessible(page);
  await page.getByRole("tab", { name: "Members" }).click();
  await expect(page.getByRole("combobox", { name: "Role of Ayesha Raza" })).toHaveValue("qa_manager");
  await page.getByRole("tab", { name: "Environments" }).click();
  await expect(page.getByText("QA", { exact: true })).toBeVisible();
  await expect(page.getByText("Staging", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Members" }).click();
  await page.getByLabel("Add a person").selectOption({ label: "Sana Malik · sana@acme.test" });
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Role of Sana Malik" })).toHaveValue("viewer"); // BR-29
  await page.getByRole("link", { name: "Activity" }).click();
  await expect(page.getByText(/added Sana Malik as Viewer/)).toBeVisible();
});
