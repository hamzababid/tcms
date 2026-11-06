import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M5 journeys: bug links (docs/02 §8, ADR-023; TCMS-100…107). Each worker makes its own project with a
// Jira-style tracker template and "a failed result needs a bug link", so the shared SPARK project keeps
// its settings for the other suites.
// Workers load this file separately: the random part keeps their names and keys apart.
const run = (Date.now().toString(36) + Math.random().toString(36).slice(2, 6)).toUpperCase();
let seq = 0;
const uniq = (label: string) => `${label} ${run}-${++seq}`;
const ref = () => `BUG-${run.slice(-4)}-${++seq}`;
/** Matches the reference but not a longer one that starts with it (BUG-X-1 vs BUG-X-12). */
const refRe = (reference: string) => new RegExp(`${reference}(?![\\w-])`);
/** A data row of the Bugs list (the filter row holds the typed text too). */
const bugRow = (page: Page, reference: string) =>
  page.getByRole("row", { name: new RegExp(`^${reference} Open ${reference} in`) });
const TEMPLATE = "https://tracker.acme.test/browse/{ref}";

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

interface Ref {
  id: string;
  key: string;
}

interface Space {
  pid: string;
  key: string;
}

let space: Space | null = null;

/** A project of Ayesha's with Bilal (QA Lead) and Sana (QA Engineer), the tracker template and the rule. */
async function project(browser: Browser): Promise<Space> {
  if (space) return space;
  const ayesha = await as(browser, "ayesha");
  const key = `B${run.slice(-8)}`.replace(/[^A-Z0-9]/g, "X").slice(0, 10);
  const p = await call<{ id: string; key: string; row_version: number }>(ayesha, "POST", "/api/v1/projects", {
    key,
    name: uniq("Bug links"),
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
  const fresh = await call<{ row_version: number }>(ayesha, "GET", `/api/v1/projects/${p.id}`);
  await call(ayesha, "PATCH", `/api/v1/projects/${p.id}`, {
    row_version: fresh.row_version,
    settings: { bug_tracker_name: "Jira", bug_url_template: TEMPLATE, require_bug_link_for_failure: true },
  });
  await ayesha.context().close();
  space = { pid: p.id, key: p.key };
  return space;
}

/** A started cycle with one fresh steps case per entry, assigned to Sana → cycle and run ids. */
async function cycleWith(
  bilal: Page,
  sp: Space,
  steps: number[],
): Promise<{ cycle: Ref; runs: string[]; caseKeys: string[] }> {
  const folder = (
    await call<{ id: string }>(bilal, "POST", `/api/v1/projects/${sp.pid}/folders`, { name: uniq("Suite") })
  ).id;
  const made: Ref[] = [];
  for (const n of steps) {
    const r = await call<{ case: Ref }>(bilal, "POST", `/api/v1/projects/${sp.pid}/test-cases`, {
      folder_id: folder,
      content: {
        format: "steps",
        title: uniq("Checkout case"),
        steps: Array.from({ length: n }, (_, i) => ({
          action: `Do step ${i + 1}`,
          expected_result: `Ok ${i + 1}`,
        })),
      },
    });
    made.push(r.case);
  }
  const envs = await call<{ id: string }[]>(bilal, "GET", `/api/v1/projects/${sp.pid}/environments`);
  const members = await call<{ user: { id: string; email: string } }[]>(
    bilal,
    "GET",
    `/api/v1/projects/${sp.pid}/members`,
  );
  const sana = members.find((m) => m.user.email === "sana@acme.test")?.user.id;
  const created = await call<{ cycle: Ref }>(bilal, "POST", `/api/v1/projects/${sp.pid}/cycles`, {
    name: uniq("Bug cycle"),
    environment_id: envs[0]?.id,
    selection: { case_ids: made.map((c) => c.id) },
    default_assignee_id: sana,
  });
  await call(bilal, "POST", `/api/v1/cycles/${created.cycle.id}/start`);
  const runs = await call<{ items: { id: string; test_case: { key: string } }[] }>(
    bilal,
    "GET",
    `/api/v1/cycles/${created.cycle.id}/runs?sort=position&page_size=50`,
  );
  const byKey = new Map(runs.items.map((r) => [r.test_case.key, r.id]));
  return {
    cycle: created.cycle,
    runs: made.map((c) => byKey.get(c.key) ?? ""),
    caseKeys: made.map((c) => c.key),
  };
}

/** Record a failed attempt with a bug link through the API (setup for the retest journey). */
async function failWithBug(sana: Page, runId: string, reference: string): Promise<string> {
  const res = await call<{ id: string; steps: { step_id: string }[] }>(
    sana,
    "POST",
    `/api/v1/runs/${runId}/results`,
    {},
  );
  const step = res.steps[0]?.step_id ?? "";
  await call(sana, "PATCH", `/api/v1/results/${res.id}/steps/${step}`, {
    status: "failed",
    actual_result: "Broke",
  });
  await call(sana, "POST", `/api/v1/results/${res.id}/bug-links`, { reference, step_id: step });
  await call(sana, "POST", `/api/v1/results/${res.id}/finalize`, {});
  return res.id;
}

const runnerUrl = (sp: Space, cycleKey: string, runId: string) =>
  `/p/${sp.key}/cycles/${cycleKey}/run/${runId}`;

test("TCMS-100 + TCMS-106: link a bug from a failed step with the keyboard; it shows on the cycle and case", async ({
  browser,
}) => {
  test.setTimeout(60_000);
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const { cycle, runs, caseKeys } = await cycleWith(bilal, sp, [2]);
  const sana = await as(browser, "sana");
  const reference = ref();

  await sana.goto(runnerUrl(sp, cycle.key, runs[0] ?? ""));
  await sana.getByRole("button", { name: /^Start/ }).click();
  await expect(sana.getByRole("button", { name: /Finish run/ })).toBeVisible();
  await sana.keyboard.press("p");
  await sana.keyboard.press("f");
  await expect(sana.getByLabel("Actual result")).toBeFocused();
  await sana.keyboard.type("Total doubled");
  // TCMS-106: the project needs a bug link, so Finish asks for it and then finishes.
  await sana.keyboard.press("Control+Enter");
  const dialog = sana.getByRole("dialog", { name: "Link bug" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/step 2/)).toBeVisible();
  await expectAccessible(sana);
  await dialog.getByLabel(/Bug reference/).fill(reference);
  await expect(dialog.getByLabel("Link")).toHaveAttribute(
    "placeholder",
    TEMPLATE.replace("{ref}", reference),
  );
  await dialog.getByRole("button", { name: "Link bug" }).click();
  await expect(sana.getByText(/Failed · Queue done/)).toBeVisible();

  // The chip opens the tracker (AC-BUG-02) on the run history, the cycle and the case.
  const chip = sana.getByRole("region", { name: "History" }).getByRole("link", { name: refRe(reference) });
  await expect(chip).toHaveAttribute("href", TEMPLATE.replace("{ref}", reference));
  await bilal.goto(`/p/${sp.key}/cycles/${cycle.key}`);
  await expect(bilal.getByRole("link", { name: refRe(reference) })).toBeVisible();
  await expectAccessible(bilal);
  await bilal.goto(`/p/${sp.key}/cases/${caseKeys[0] ?? ""}`);
  await bilal.getByRole("tab", { name: "Bugs" }).click();
  await expect(bilal.getByRole("link", { name: refRe(reference) })).toBeVisible();
  await expect(bilal.getByText(new RegExp(`${cycle.key} · attempt 1 \\(failed\\) · step 2`))).toBeVisible();
  await expectAccessible(bilal);
});

test("TCMS-103 + TCMS-104: ready for retest flags the run; the retest clears it and keeps the bug", async ({
  browser,
}) => {
  test.setTimeout(60_000);
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const { cycle, runs } = await cycleWith(bilal, sp, [1]);
  const sana = await as(browser, "sana");
  const reference = ref();
  await failWithBug(sana, runs[0] ?? "", reference);

  await bilal.goto(`/p/${sp.key}/bugs`);
  await bilal.getByPlaceholder("Reference or title").fill(reference);
  const row = bugRow(bilal, reference);
  await expect(row).toBeVisible();
  await expectAccessible(bilal);
  await row.getByRole("button", { name: /Ready for retest/ }).click();
  const confirm = bilal.getByRole("dialog", { name: `${reference} ready for retest?` });
  await expect(confirm.getByText("1 of 1 linked run will be flagged ⟳ for retest.")).toBeVisible();
  await confirm.getByRole("button", { name: "Flag for retest" }).click();
  await expect(bilal.getByText("1 run flagged for retest")).toBeVisible();
  expect(
    (await call<{ needs_retest: boolean }>(bilal, "GET", `/api/v1/runs/${runs[0] ?? ""}`)).needs_retest,
  ).toBe(true);

  await sana.goto(runnerUrl(sp, cycle.key, runs[0] ?? ""));
  await sana.getByRole("button", { name: /^Retest/ }).click();
  await expect(sana.getByRole("button", { name: /Finish run/ })).toBeVisible();
  await sana.keyboard.press("p");
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(/Passed · Queue done/)).toBeVisible();
  await expect
    .poll(
      async () =>
        (await call<{ needs_retest: boolean }>(bilal, "GET", `/api/v1/runs/${runs[0] ?? ""}`)).needs_retest,
    )
    .toBe(false);
  await sana.reload();
  await expect(
    sana.getByRole("region", { name: "History" }).getByRole("link", { name: refRe(reference) }),
  ).toBeVisible();
});

test("TCMS-102 + TCMS-105: link a bug to a case directly; the Bugs list groups the reference", async ({
  browser,
}) => {
  const sp = await project(browser);
  const bilal = await as(browser, "bilal");
  const { caseKeys, runs } = await cycleWith(bilal, sp, [1]);
  const sana = await as(browser, "sana");
  const reference = ref();
  await failWithBug(sana, runs[0] ?? "", reference);

  await bilal.goto(`/p/${sp.key}/cases/${caseKeys[0] ?? ""}`);
  await bilal.getByRole("tab", { name: "Bugs" }).click();
  await bilal.getByRole("button", { name: "Link bug" }).click();
  const dialog = bilal.getByRole("dialog", { name: "Link bug" });
  await dialog.getByLabel(/Bug reference/).fill(`${reference}-UI`);
  await dialog.getByLabel("Title").fill("Copy typo");
  await dialog.getByRole("button", { name: "Link bug" }).click();
  await expect(bilal.getByText("On the case")).toBeVisible();

  await bilal.goto(`/p/${sp.key}/bugs`);
  await bilal.getByPlaceholder("Reference or title").fill(reference);
  await expect(bugRow(bilal, `${reference}-UI`)).toBeVisible();
  const linked = bugRow(bilal, reference);
  await linked.click();
  const detail = bilal.getByRole("dialog", { name: reference });
  await expect(detail.getByRole("link", { name: caseKeys[0] ?? "" })).toBeVisible();
  await expect(detail.getByRole("link", { name: "Open run" })).toBeVisible();
  await expectAccessible(bilal);
});

test("project options: tracker address validation and the bug-link rule", async ({ browser }) => {
  const sp = await project(browser);
  const ayesha = await as(browser, "ayesha");
  await ayesha.goto(`/p/${sp.key}/settings`);
  await ayesha.getByRole("tab", { name: "Options" }).click();
  await expect(ayesha.getByLabel("Tracker name")).toHaveValue("Jira");
  await expect(ayesha.getByLabel("Bug address")).toHaveValue(TEMPLATE);
  await expect(ayesha.getByLabel("A failed result needs a bug link")).toBeChecked();
  await ayesha.getByLabel("Bug address").fill("https://tracker.acme.test/browse/");
  await ayesha.getByRole("button", { name: "Save options" }).click();
  await expect(ayesha.getByText(/with \{ref\} where the bug reference goes/)).toBeVisible();
  await expectAccessible(ayesha);
});
