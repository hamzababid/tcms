import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M7b journeys: the notification bell (US-170, AC-NTF-01) and email opt-outs (US-171, AC-NTF-02/03).

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

test("AC-NTF-01: runs assigned to Sana show in her bell; opening one marks it read", async ({ browser }) => {
  test.setTimeout(60_000);
  const ayesha = await as(browser, "ayesha");
  const key = `N${run.slice(-8)}`.replace(/[^A-Z0-9]/g, "X").slice(0, 10);
  const p = await call<{ id: string; key: string }>(ayesha, "POST", "/api/v1/projects", {
    key,
    name: uniq("Bell"),
  });
  const people = await call<{ id: string; email: string }[]>(
    ayesha,
    "GET",
    `/api/v1/projects/${p.id}/member-candidates`,
  );
  const sanaId = people.find((x) => x.email === "sana@acme.test")?.id ?? "";
  await call(ayesha, "POST", `/api/v1/projects/${p.id}/members`, {
    user_id: sanaId,
    role_code: "qa_engineer",
  });
  const folder = await call<{ id: string }>(ayesha, "POST", `/api/v1/projects/${p.id}/folders`, {
    name: "Suite",
  });
  const c = await call<{ case: { id: string } }>(ayesha, "POST", `/api/v1/projects/${p.id}/test-cases`, {
    folder_id: folder.id,
    content: {
      format: "steps",
      title: uniq("Bell case"),
      steps: [{ action: "Do", expected_result: "Done" }],
    },
  });
  const envs = await call<{ id: string }[]>(ayesha, "GET", `/api/v1/projects/${p.id}/environments`);

  const sana = await as(browser, "sana");
  await call(sana, "POST", "/api/v1/me/notifications/read", { all: true });
  const cyc = await call<{ cycle: { id: string; key: string } }>(
    ayesha,
    "POST",
    `/api/v1/projects/${p.id}/cycles`,
    {
      name: uniq("Cycle"),
      environment_id: envs[0]?.id,
      selection: { case_ids: [c.case.id] },
      default_assignee_id: sanaId,
    },
  );
  await sana.goto("/my-work");
  const bell = sana.getByRole("button", { name: /^Notifications/ });
  // Other test files assign runs to Sana in parallel, so check this cycle's notification, not the totals.
  await expect(bell).toHaveAccessibleName(/^Notifications, \d+ unread$/);
  await bell.click();
  const item = sana
    .getByRole("list", { name: "Latest notifications" })
    .getByRole("button")
    .filter({ hasText: `in ${cyc.cycle.key}` });
  await expect(item).toContainText(`1 run assigned to you in ${cyc.cycle.key}`);
  await expectAccessible(sana);
  await item.click();
  await expect(sana).toHaveURL(new RegExp(`/cycles/${cyc.cycle.key}$`));
  await expect
    .poll(async () => {
      const page = await call<{ items: { title: string; read_at: string | null }[] }>(
        sana,
        "GET",
        "/api/v1/me/notifications",
      );
      return page.items.find((n) => n.title.includes(cyc.cycle.key))?.read_at ?? null;
    })
    .not.toBeNull();
});

test("AC-NTF-02/03: Sana switches email notifications off in her account", async ({ browser }) => {
  const sana = await as(browser, "sana");
  await sana.goto("/profile?tab=notifications");
  const mentions = sana.getByLabel("Email me when someone mentions me");
  const digest = sana.getByLabel("Daily summary of runs assigned to me");
  await expect(mentions).toBeVisible();
  const before = await digest.isChecked();
  await digest.setChecked(!before);
  await expect(sana.getByText("Email settings saved")).toBeVisible();
  await expectAccessible(sana);
  await sana.reload();
  await expect(digest).toBeChecked({ checked: !before });
  await digest.setChecked(before); // leave the seed user as it was
  await expect(sana.getByText("Email settings saved").first()).toBeVisible();
});
