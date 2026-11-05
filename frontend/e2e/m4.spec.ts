import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

// M4 journeys: the runner and My Work (docs/08 TCMS-070…090). Seed users from e2e/auth.setup.ts.
const run = Date.now().toString(36);
let seq = 0;
const uniq = (label: string) => `${label} ${run}${Math.random().toString(36).slice(2, 6)}-${++seq}`;
const PNG = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000500010d0a2db40000000049454e44ae426082",
  "hex",
);

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

async function spark(page: Page): Promise<string> {
  const projects = await call<Ref[]>(page, "GET", "/api/v1/projects");
  const p = projects.find((x) => x.key === "SPARK");
  if (!p) throw new Error("SPARK not visible");
  return p.id;
}

async function userId(page: Page, pid: string, email: string): Promise<string> {
  const members = await call<{ user: { id: string; email: string } }[]>(
    page,
    "GET",
    `/api/v1/projects/${pid}/members`,
  );
  const m = members.find((x) => x.user.email === email);
  if (!m) throw new Error(`${email} is not a member`);
  return m.user.id;
}

async function stepsCase(
  page: Page,
  pid: string,
  folder: string,
  steps: number,
): Promise<Ref & { row_version: number }> {
  const r = await call<{ case: Ref & { row_version: number } }>(
    page,
    "POST",
    `/api/v1/projects/${pid}/test-cases`,
    {
      folder_id: folder,
      content: {
        format: "steps",
        title: uniq("Runner case"),
        preconditions: "User `qa.user@acme.test` exists",
        steps: Array.from({ length: steps }, (_, i) => ({
          action: `Do step ${i + 1}`,
          expected_result: `Result ${i + 1}`,
        })),
      },
    },
  );
  return r.case;
}

/** A cycle of fresh cases assigned to Sana → cycle and run ids in position order. */
async function assignedCycle(
  bilal: Page,
  cases: { steps?: number; text?: boolean }[],
): Promise<{ cycle: Ref & { name: string }; runs: string[]; caseKeys: string[]; caseIds: string[] }> {
  const pid = await spark(bilal);
  const folder = (
    await call<{ id: string }>(bilal, "POST", `/api/v1/projects/${pid}/folders`, { name: uniq("Runner") })
  ).id;
  const made: Ref[] = [];
  for (const c of cases) {
    if (c.text) {
      const r = await call<{ case: Ref }>(bilal, "POST", `/api/v1/projects/${pid}/test-cases`, {
        folder_id: folder,
        content: { format: "text", title: uniq("Explore checkout"), text_body: "Try odd carts and coupons." },
      });
      made.push(r.case);
    } else made.push(await stepsCase(bilal, pid, folder, c.steps ?? 2));
  }
  const envs = await call<{ id: string; archived: boolean }[]>(
    bilal,
    "GET",
    `/api/v1/projects/${pid}/environments`,
  );
  const sana = await userId(bilal, pid, "sana@acme.test");
  const created = await call<{ cycle: Ref & { name: string } }>(
    bilal,
    "POST",
    `/api/v1/projects/${pid}/cycles`,
    {
      name: uniq("Runner cycle"),
      environment_id: envs.find((e) => !e.archived)?.id,
      selection: { case_ids: made.map((c) => c.id) },
      default_assignee_id: sana,
    },
  );
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
    caseIds: made.map((c) => c.id),
  };
}

const runnerUrl = (cycleKey: string, runId: string) => `/p/SPARK/cycles/${cycleKey}/run/${runId}`;

/** Click Start (or Retest) and wait until the step grid of the new draft is shown. */
async function begin(page: Page, button: RegExp = /^Start/) {
  await page.getByRole("button", { name: button }).click();
  await expect(page.getByRole("button", { name: /Finish run/ })).toBeVisible();
}

test("TCMS-070 + TCMS-086 + TCMS-084: from My Work, execute a run with the keyboard only", async ({
  browser,
}) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs, caseKeys } = await assignedCycle(bilal, [{ steps: 3 }, { steps: 1 }]);
  const sana = await as(browser, "sana");
  await sana.goto("/my-work");
  await expect(sana.getByRole("heading", { name: "My Work", level: 1 })).toBeVisible();
  await expectAccessible(sana);
  await sana.getByRole("button", { name: `Start ${cycle.key}` }).click();
  await expect(sana).toHaveURL(new RegExp(`/cycles/${cycle.key}/run/${runs[0]}$`));
  await expect(sana.getByText("Run 1 of 2")).toBeVisible();

  await sana.keyboard.press("Space"); // BR-30: starts the planned cycle too
  const steps = sana.getByRole("list", { name: "Steps" });
  await expect(steps.getByRole("button", { name: /Pass/ }).first()).toBeVisible();
  await expectAccessible(sana);
  for (let i = 0; i < 3; i++) await sana.keyboard.press("p");
  await expect(sana.locator("[data-preview=passed]")).toHaveText("Passed");
  await expect(steps.getByText("Saved")).toHaveCount(3);
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(new RegExp(`${caseKeys[0]} Passed · Next: ${caseKeys[1]}`))).toBeVisible();
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[1]}$`)); // auto-advance after 1 s

  const finished = await call<{ status: string }>(bilal, "GET", `/api/v1/runs/${runs[0]}`);
  expect(finished.status).toBe("passed");
  const c = await call<{ status: string; summary: { passed: number } }>(
    bilal,
    "GET",
    `/api/v1/cycles/${cycle.id}`,
  );
  expect([c.status, c.summary.passed]).toEqual(["active", 1]);
});

test("TCMS-072 + TCMS-074: a failed step needs an actual result; block a run with a reason", async ({
  browser,
}) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs } = await assignedCycle(bilal, [{ steps: 2 }, { steps: 2 }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  await sana.keyboard.press("p");
  await sana.keyboard.press("f"); // focuses the actual result
  const actual = sana.getByLabel("Actual result");
  await expect(actual).toBeFocused();
  await sana.keyboard.type("Dashboard took 9 s to load");
  await sana.keyboard.press("Escape");
  await expect(sana.locator("[data-preview=failed]")).toBeVisible();
  await sana.getByRole("button", { name: /Finish run/ }).click();
  await expect(sana.getByText(/Failed · Next/)).toBeVisible();

  await expect(sana).toHaveURL(new RegExp(`/run/${runs[1]}$`));
  await begin(sana);
  await sana.keyboard.press("p");
  await sana.getByRole("button", { name: "Block run…" }).click();
  const dialog = sana.getByRole("dialog", { name: "Block run" });
  await dialog.getByLabel("Reason").fill("QA environment is down");
  await dialog.getByRole("button", { name: "Finish run" }).click();
  await expect(sana.getByText(/Blocked · Queue done/)).toBeVisible();
  await sana.reload();
  await expect(sana.getByRole("region", { name: "History" })).toContainText("QA environment is down");
  const failed = await call<{ status: string }>(bilal, "GET", `/api/v1/runs/${runs[0]}`);
  expect(failed.status).toBe("failed");
});

test("TCMS-087: paste a screenshot into the actual result", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs } = await assignedCycle(bilal, [{ steps: 1 }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  await sana.keyboard.press("f");
  await expect(sana.getByLabel("Actual result")).toBeFocused();
  await sana.evaluate((hex) => {
    const bytes = new Uint8Array(hex.match(/../g)?.map((h) => parseInt(h, 16)) ?? []);
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], "screenshot-1.png", { type: "image/png" }));
    document.activeElement?.dispatchEvent(
      new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }),
    );
  }, PNG.toString("hex"));
  await expect(sana.getByRole("link", { name: "screenshot-1.png" })).toBeVisible();
  // Attaching through the file picker works too.
  await sana
    .getByLabel("Attach evidence to step 1")
    .setInputFiles({ name: "log.png", mimeType: "image/png", buffer: PNG });
  await expect(sana.getByRole("link", { name: "log.png" })).toBeVisible();
  await sana.getByLabel("Actual result").fill("Spinner never stops");
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(/Failed · Queue done/)).toBeVisible();
  const run = await call<{ history: { id: string }[] }>(
    bilal,
    "GET",
    `/api/v1/runs/${runs[0]}?include=history`,
  );
  const result = await call<{ steps: { attachments: { file_name: string }[] }[] }>(
    bilal,
    "GET",
    `/api/v1/results/${run.history[0]?.id}`,
  );
  expect(result.steps[0]?.attachments.map((a) => a.file_name).sort()).toEqual([
    "log.png",
    "screenshot-1.png",
  ]);
});

test("TCMS-088: a failed save shows 'not saved' and recovers", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs } = await assignedCycle(bilal, [{ steps: 2 }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  let fail = true;
  await sana.route("**/api/v1/results/*/steps/*", async (route) => {
    if (fail && route.request().method() === "PATCH") await route.abort();
    else await route.continue();
  });
  await sana.keyboard.press("p");
  await expect(sana.getByText("Not saved – retrying")).toBeVisible();
  await expect(sana.getByRole("button", { name: /Finish run/ })).toBeDisabled();
  fail = false;
  await expect(sana.getByText("Not saved – retrying")).toHaveCount(0, { timeout: 12_000 });
  await expect(sana.getByRole("list", { name: "Steps" }).getByText("Saved")).toHaveCount(1);
  const r = await call<{ draft: { steps: { status: string }[] } }>(
    bilal,
    "GET",
    `/api/v1/runs/${runs[0]}?include=draft`,
  );
  expect(r.draft.steps[0]?.status).toBe("passed");
});

test("TCMS-079 + TCMS-081: retest keeps the history; the run stays on its pinned version", async ({
  browser,
}) => {
  test.setTimeout(60_000);
  const bilal = await as(browser, "bilal");
  const { cycle, runs, caseIds } = await assignedCycle(bilal, [{ steps: 1 }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  await sana.keyboard.press("f");
  await expect(sana.getByLabel("Actual result")).toBeFocused();
  await sana.keyboard.type("Wrong total");
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(/Failed · Queue done/)).toBeVisible();
  await expect
    .poll(async () => (await call<{ status: string }>(bilal, "GET", `/api/v1/runs/${runs[0]}`)).status)
    .toBe("failed");

  // The case moves on to v2 while the run keeps v1 (AC-EXE-08).
  const tc = await call<{ row_version: number; title: string }>(
    bilal,
    "GET",
    `/api/v1/test-cases/${caseIds[0]}`,
  );
  await call(bilal, "PUT", `/api/v1/test-cases/${caseIds[0]}/content`, {
    row_version: tc.row_version,
    content: {
      format: "steps",
      title: tc.title,
      steps: [{ action: "Changed action", expected_result: "New" }],
    },
  });
  await sana.reload();
  await expect(sana.getByText("v2 available (you are on v1)")).toBeVisible();
  await expect(sana.getByText("Do step 1")).toBeVisible();
  await expect(sana.getByRole("button", { name: /Update to v2/ })).toHaveCount(0);

  await begin(sana, /^Retest/);
  await sana.keyboard.press("p");
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(/Passed · Queue done/)).toBeVisible();
  await sana.reload();
  const history = sana.getByRole("region", { name: "History" });
  await expect(history.getByRole("listitem")).toHaveCount(2);
  await expect(history).toContainText("Attempt 1");
  await expect(history).toContainText("Attempt 2");
  await expectAccessible(sana);
});

test("TCMS-089: execute a text-format case", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs } = await assignedCycle(bilal, [{ text: true }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  await expect(sana.getByText("Try odd carts and coupons.")).toBeVisible();
  await sana.getByRole("button", { name: "Failed", exact: true }).click();
  await sana.getByRole("button", { name: /Finish run/ }).click();
  await expect(sana.getByText("Describe what failed")).toBeVisible();
  await sana.getByLabel(/^Comment/).fill("Coupon applied twice");
  await sana.getByRole("button", { name: /Finish run/ }).click();
  await expect(sana.getByText(/Failed · Queue done/)).toBeVisible();
  const r = await call<{ status: string }>(bilal, "GET", `/api/v1/runs/${runs[0]}`);
  expect(r.status).toBe("failed");
});

test("TCMS-058 with a live draft: closing lists the draft and discards it", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs, caseKeys } = await assignedCycle(bilal, [{ steps: 2 }, { steps: 1 }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  await sana.keyboard.press("p");
  await expect(sana.getByRole("list", { name: "Steps" }).getByText("Saved")).toHaveCount(1);

  await bilal.goto(`/p/SPARK/cycles/${cycle.key}`);
  await bilal.getByRole("button", { name: "More cycle actions" }).click();
  await bilal.getByRole("menuitem", { name: "Close cycle" }).click();
  const close = bilal.getByRole("dialog", { name: `Close ${cycle.key}?` });
  await close.getByRole("button", { name: "Close cycle" }).click();
  await expect(close.getByText(caseKeys[0] ?? "")).toBeVisible();
  await expect(close.getByText("Sana Malik")).toBeVisible();
  await close.getByRole("button", { name: "Discard 1 draft and close" }).click();
  await expect(bilal.getByText(/Closed by Bilal Khan/)).toBeVisible();
  const r = await call<{ status: string }>(bilal, "GET", `/api/v1/runs/${runs[0]}`);
  expect(r.status).toBe("not_run");
});

test("TCMS-083: replace a run that has a result with a run on the new version", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs, caseIds, caseKeys } = await assignedCycle(bilal, [{ steps: 1 }]);
  const sana = await as(browser, "sana");
  await sana.goto(runnerUrl(cycle.key, runs[0]));
  await begin(sana);
  await sana.keyboard.press("p");
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(/Passed/).first()).toBeVisible();
  const tc = await call<{ row_version: number; title: string }>(
    bilal,
    "GET",
    `/api/v1/test-cases/${caseIds[0]}`,
  );
  await call(bilal, "PUT", `/api/v1/test-cases/${caseIds[0]}/content`, {
    row_version: tc.row_version,
    content: {
      format: "steps",
      title: tc.title,
      steps: [{ action: "New flow", expected_result: "New result" }],
    },
  });

  await bilal.goto(`/p/SPARK/cycles/${cycle.key}?run=${runs[0]}`);
  const panel = bilal.getByRole("complementary", { name: `${caseKeys[0]} details` });
  await panel.getByRole("button", { name: "Replace with a new run on v2" }).click();
  await expect(bilal.getByText("New run at v2")).toBeVisible();
  const list = await call<{ items: { id: string; pinned_version_no: number; status: string }[] }>(
    bilal,
    "GET",
    `/api/v1/cycles/${cycle.id}/runs`,
  );
  expect(list.items.map((x) => [x.pinned_version_no, x.status])).toEqual([[2, "not_run"]]);
  const c = await call<{ summary: { passed: number; total: number } }>(
    bilal,
    "GET",
    `/api/v1/cycles/${cycle.id}`,
  );
  expect([c.summary.total, c.summary.passed]).toEqual([1, 0]); // BR-05: the old run is excluded
});

test("cycle 'Start testing' opens my first open run; Shift+N moves on", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const { cycle, runs } = await assignedCycle(bilal, [{ steps: 1 }, { steps: 1 }]);
  const sana = await as(browser, "sana");
  await sana.goto(`/p/SPARK/cycles/${cycle.key}`);
  await sana.getByRole("button", { name: "Start testing" }).click();
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[0]}$`));
  await expect(sana.getByRole("button", { name: /Next/ })).toBeEnabled();
  await sana.keyboard.press("Shift+N");
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[1]}$`));
  await sana.keyboard.press("?");
  await expect(sana.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
});
