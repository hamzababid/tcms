import AxeBuilder from "@axe-core/playwright";
import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

// Seed credentials (docs/ops/local-setup.md; local/CI stacks only).
const PASSWORD = "Passw0rd!Passw0rd";
const ADMIN = { email: "zain@acme.test", totp: "ASSAYLOCALDEVTOTPSECRETONLY23456" };
const run = Date.now().toString(36);

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

type SeedUser = "bilal" | "sana";

/** A page signed in as a seed user (session from e2e/auth.setup.ts). */
async function as(browser: Browser, user: SeedUser): Promise<Page> {
  const context = await browser.newContext({ storageState: `e2e/.auth/${user}.json` });
  return context.newPage();
}

/** JSON API call in the page's session (CSRF header like the SPA). */
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

async function projectId(page: Page, key: string): Promise<string> {
  const projects = await call<{ id: string; key: string }[]>(page, "GET", "/api/v1/projects");
  const p = projects.find((x) => x.key === key);
  if (!p) throw new Error(`project ${key} not visible`);
  return p.id;
}

interface CaseRef {
  id: string;
  key: string;
  row_version: number;
}

async function apiFolder(page: Page, pid: string, name: string): Promise<string> {
  return (await call<{ id: string }>(page, "POST", `/api/v1/projects/${pid}/folders`, { name })).id;
}

async function apiCase(page: Page, pid: string, folderId: string, title: string): Promise<CaseRef> {
  const r = await call<{ case: CaseRef }>(page, "POST", `/api/v1/projects/${pid}/test-cases`, {
    folder_id: folderId,
    content: {
      format: "steps",
      title,
      steps: [
        { action: "Open the sign-in page", expected_result: "Form is displayed" },
        { action: "Sign in", expected_result: "Dashboard within 3 s" },
      ],
    },
  });
  return r.case;
}

test("TCMS-030: create nested folders and move a folder", async ({ browser }) => {
  const page = await as(browser, "bilal");
  await page.goto("/p/SPARK/repository");
  await expect(page.getByRole("heading", { name: "Repository" })).toBeVisible();
  const tree = page.getByRole("tree", { name: "Repository folders" });

  await page.getByRole("button", { name: "+ Folder" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill(`E2E ${run}`);
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  const parent = tree.getByRole("treeitem", { name: new RegExp(`E2E ${run}`) });
  await expect(parent).toHaveAttribute("aria-selected", "true");

  await parent.hover();
  await page.getByRole("button", { name: `Folder actions for E2E ${run}` }).click();
  await page.getByRole("menuitem", { name: "New subfolder" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill(`Child ${run}`);
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  const child = tree.getByRole("treeitem", { name: new RegExp(`Child ${run}`) });
  await expect(child).toHaveAttribute("aria-level", "2");

  // "+ Folder" creates inside the selected folder: select the root first.
  await tree.getByRole("treeitem", { name: "All cases" }).click();
  await page.getByRole("button", { name: "+ Folder" }).click();
  await expect(page.getByRole("dialog", { name: "New folder" })).toBeVisible();
  await page.getByRole("dialog").getByLabel("Name").fill(`Target ${run}`);
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  const target = tree.getByRole("treeitem", { name: new RegExp(`Target ${run}`) });
  await expect(target).toHaveAttribute("aria-level", "1");

  await child.dragTo(target);
  const names = async () => tree.getByRole("treeitem").allTextContents();
  await expect
    .poll(async () => {
      const list = await names();
      const t = list.findIndex((n) => n.includes(`Target ${run}`));
      return t >= 0 && (list[t + 1] ?? "").includes(`Child ${run}`);
    })
    .toBe(true);
  await expectAccessible(page);
});

test("TCMS-033 + TCMS-046: author a 10-step case from the keyboard", async ({ browser }) => {
  const page = await as(browser, "bilal");
  const pid = await projectId(page, "SPARK");
  const folder = await apiFolder(page, pid, `Keyboard ${run}`);
  await page.goto(`/p/SPARK/repository?folder=${folder}`);
  await expect(page.getByRole("button", { name: /New case/ })).toBeVisible();
  await page.keyboard.press("c");
  await expect(page.getByRole("heading", { name: "New test case" })).toBeVisible();
  await expect(page.getByLabel("Title")).toBeFocused();
  await page.keyboard.type(`Keyboard authored ${run}`);

  await page.getByLabel("Step 1 action", { exact: true }).focus();
  for (let i = 1; i <= 10; i++) {
    await page.keyboard.type(`Action ${i}`);
    await page.keyboard.press("Tab");
    await page.keyboard.type(`Result ${i}`);
    if (i < 10) await page.keyboard.press("Enter");
  }
  await expect(page.getByLabel("Step 10 action", { exact: true })).toHaveValue("Action 10");
  await page.keyboard.press("Control+s");

  const panel = page.getByRole("complementary", { name: /SPARK-TC-\d+ details/ });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("heading", { name: `Keyboard authored ${run}` })).toBeVisible();
  await expect(panel.getByText("Steps (10)")).toBeVisible();
  await expect(panel.locator("header").getByText("v1", { exact: true })).toBeVisible();
  await expectAccessible(page);
});

test("TCMS-036: compare two versions", async ({ browser }) => {
  const page = await as(browser, "bilal");
  const pid = await projectId(page, "SPARK");
  const folder = await apiFolder(page, pid, `Compare ${run}`);
  const c = await apiCase(page, pid, folder, `Compare me ${run}`);
  await call(page, "PUT", `/api/v1/test-cases/${c.id}/content`, {
    row_version: c.row_version,
    change_note: "Tightened timing",
    content: {
      format: "steps",
      title: `Compare me ${run}`,
      steps: [
        { action: "Open the sign-in page", expected_result: "Form is displayed" },
        { action: "Sign in", expected_result: "Dashboard within 2 s" },
      ],
    },
  });
  await page.goto(`/p/SPARK/repository?folder=${folder}&case=${c.key}`);
  const panel = page.getByRole("complementary", { name: `${c.key} details` });
  await panel.getByRole("tab", { name: /Versions/ }).click();
  await panel.getByLabel("Compare v1").check();
  await panel.getByLabel("Compare v2").check();
  await panel.getByRole("button", { name: "Compare v1 ↔ v2" }).click();
  const diff = panel.getByLabel("Changes from v1 to v2");
  await expect(diff.locator("[data-change=changed]")).toHaveCount(1);
  await expect(diff.locator("ins")).toContainText("2");
  await expect(diff.getByText("1 unchanged step hidden")).toBeVisible();
  await expectAccessible(page);
});

test("TCMS-038: submit, return with comment, resubmit and approve", async ({ browser, request }) => {
  test.setTimeout(120_000);
  // Setup through the admin API: a project with approval on, Sana authors, Bilal reviews.
  await adminLogin(request);
  const key = `AP${run.slice(-6).toUpperCase()}`;
  const created = await request.post("/api/v1/projects", {
    data: { key, name: `Approval ${run}` },
    headers: await csrfFrom(request),
  });
  expect(created.ok(), await created.text()).toBe(true);
  const project = (await created.json()) as { id: string; row_version: number };
  const members = (await (await request.get("/api/v1/organization/members")).json()) as {
    user: { id: string; email: string };
  }[];
  for (const [email, role] of [
    ["sana@acme.test", "qa_engineer"],
    ["bilal@acme.test", "qa_lead"],
  ] as const) {
    const id = members.find((m) => m.user.email === email)?.user.id;
    const r = await request.post(`/api/v1/projects/${project.id}/members`, {
      data: { user_id: id, role_code: role },
      headers: await csrfFrom(request),
    });
    expect(r.ok(), await r.text()).toBe(true);
  }
  const patched = await request.patch(`/api/v1/projects/${project.id}`, {
    data: { settings: { approval_required: true }, row_version: project.row_version },
    headers: await csrfFrom(request),
  });
  expect(patched.ok(), await patched.text()).toBe(true);

  const bilal = await as(browser, "bilal");
  const folder = await apiFolder(bilal, project.id, "Login"); // folder.manage: QA Lead
  const sana = await as(browser, "sana");
  const c = await apiCase(sana, project.id, folder, `Review me ${run}`);
  await sana.goto(`/p/${key}/repository?case=${c.key}`);
  const sanaPanel = sana.getByRole("complementary", { name: `${c.key} details` });
  await expect(sanaPanel.locator("[data-status=draft]")).toBeVisible();
  await sanaPanel.getByRole("button", { name: "Case actions" }).click();
  await sana.getByRole("menuitem", { name: "Submit for review…" }).click();
  await sana.getByRole("dialog").getByRole("button", { name: "Submit" }).click();
  await expect(sanaPanel.locator("[data-status=in_review]").first()).toBeVisible();

  await bilal.goto(`/p/${key}/repository?case=${c.key}`);
  const bilalPanel = bilal.getByRole("complementary", { name: `${c.key} details` });
  await expect(bilalPanel.getByText(/is waiting for review/)).toBeVisible();
  await bilalPanel.getByRole("button", { name: "Return…" }).click();
  await bilal.getByRole("dialog").getByLabel("What needs to change?").fill("Add the lockout step");
  await bilal.getByRole("dialog").getByRole("button", { name: "Return" }).click();
  await expect(bilalPanel.locator("[data-status=draft]")).toBeVisible();

  await sana.reload();
  await sanaPanel.getByRole("tab", { name: /Comments/ }).click();
  await expect(sanaPanel.getByText("Add the lockout step")).toBeVisible();
  await sanaPanel.getByRole("button", { name: "Case actions" }).click();
  await sana.getByRole("menuitem", { name: "Submit for review…" }).click();
  await sana.getByRole("dialog").getByRole("button", { name: "Submit" }).click();
  await expect(sanaPanel.locator("[data-status=in_review]").first()).toBeVisible();

  await bilal.reload();
  await bilalPanel.getByRole("button", { name: "Approve" }).click();
  await expect(bilalPanel.locator("[data-status=approved]")).toBeVisible();
  await expectAccessible(bilal);
});

test("TCMS-047: a concurrent edit shows the conflict dialog", async ({ browser }) => {
  const page = await as(browser, "bilal");
  const pid = await projectId(page, "SPARK");
  const folder = await apiFolder(page, pid, `Conflict ${run}`);
  const c = await apiCase(page, pid, folder, `Conflict me ${run}`);
  await page.goto(`/p/SPARK/cases/${c.key}/edit`);
  await expect(page.getByRole("heading", { name: "Edit test case" })).toBeVisible();
  // Someone else changes the case meanwhile.
  await call(page, "PATCH", `/api/v1/test-cases/${c.id}`, {
    priority: "critical",
    row_version: c.row_version,
  });
  await page.getByLabel("Title").fill(`Conflict me ${run} (edited)`);
  await page.keyboard.press("Control+s");
  const dialog = page.getByRole("dialog", { name: "Someone else changed this" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Reload latest" }).click();
  await expect(page.getByLabel("Priority")).toHaveValue("critical");
});

// -- admin API session (TOTP codes are single use: wait for a fresh step on replay) ---------------

function totp(secret: string): string {
  return new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 }).generate();
}

async function csrfFrom(request: APIRequestContext): Promise<Record<string, string>> {
  const state = await request.storageState();
  const cookie = state.cookies.find((c) => c.name === "tcms_csrf");
  return cookie ? { "X-CSRF-Token": cookie.value } : {};
}

async function adminLogin(request: APIRequestContext): Promise<void> {
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
