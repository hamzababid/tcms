import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";

// M8c: keyboard-only regression of the repository and the runner (TCMS-143, NFR-UX-03) and the `?`
// shortcut help (docs/07 §10, L20). After `goto`, the journeys use the keyboard only: no clicks.
const run = Date.now().toString(36);
let seq = 0;
const uniq = (label: string) => `${label} ${run}${Math.random().toString(36).slice(2, 6)}-${++seq}`;

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

/** Press Tab until `target` has focus: proves it is reachable in the tab order. */
async function tabTo(page: Page, target: Locator, key: "Tab" | "Shift+Tab" = "Tab", max = 120) {
  const seen: string[] = [];
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press(key);
    seen.push(
      await page.evaluate(() => {
        const a = document.activeElement;
        if (!a) return "-";
        const name = a.getAttribute("aria-label") ?? (a.textContent || "").trim().slice(0, 30);
        return `${a.tagName.toLowerCase()}[${a.getAttribute("role") ?? ""}] ${name}`;
      }),
    );
  }
  expect(false, `not reached by Tab; focus went through:\n${seen.slice(0, 60).join("\n")}`).toBe(true);
}

test("? opens the shortcut help everywhere; the sidebar lists it too", async ({ browser }) => {
  const page = await as(browser, "sana");
  await page.goto("/my-work");
  await expect(page.getByRole("heading", { name: "My Work", level: 1 })).toBeVisible();
  await page.keyboard.press("?");
  const help = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(help).toBeVisible();
  for (const scope of ["Everywhere", "Lists", "Repository", "Case editor", "Runner"]) {
    await expect(help.getByRole("heading", { name: scope })).toBeVisible();
  }
  await expect(help).toContainText("Search and command palette");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(help).toBeHidden();

  // Not while typing: `?` in a text field is a character.
  await page.keyboard.press("/");
  const search = page.getByRole("dialog").getByLabel("Search");
  await expect(search).toBeFocused();
  await page.keyboard.type("why?");
  await expect(search).toHaveValue("why?");
  await page.keyboard.press("Escape");

  // Focus is back on the search button in the top bar; the sidebar is behind it.
  await tabTo(
    page,
    page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: "Keyboard shortcuts" }),
    "Shift+Tab",
  );
  await page.keyboard.press("Enter");
  await expect(help).toBeVisible();
});

test("TCMS-143: the repository with the keyboard only", async ({ browser }) => {
  test.setTimeout(90_000); // five axe scans and a few dozen Tab presses
  const page = await as(browser, "bilal");
  const pid = await spark(page);
  const parentName = uniq("Keys");
  const parent = (
    await call<{ id: string }>(page, "POST", `/api/v1/projects/${pid}/folders`, { name: parentName })
  ).id;
  await page.goto(`/p/SPARK/repository?folder=${parent}`);
  const tree = page.getByRole("tree", { name: "Repository folders" });
  await expect(tree.getByRole("treeitem", { name: new RegExp(parentName) })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // F: a subfolder of the selected folder; Enter submits.
  const childName = uniq("Child");
  await page.keyboard.press("f");
  const dialog = page.getByRole("dialog", { name: `New folder in ${parentName}` });
  await expect(dialog.getByLabel("Name")).toBeFocused();
  await page.keyboard.type(childName);
  await page.keyboard.press("Enter");
  const child = tree.getByRole("treeitem", { name: new RegExp(childName) });
  await expect(child).toHaveAttribute("aria-level", "2");
  await expect(dialog).toBeHidden();
  await expect(child).toHaveAttribute("aria-selected", "true"); // the new folder is selected

  // The tree is one tab stop (its selected folder); arrows move, Enter selects.
  await tabTo(page, child);
  // The folder's actions open from the row (its "…" button is not a separate tab stop).
  await page.keyboard.press("Shift+F10");
  await expect(page.getByRole("menuitem", { name: "New subfolder" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Rename" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(child).toBeFocused();
  const parentItem = tree.getByRole("treeitem", { name: new RegExp(parentName) });
  await page.keyboard.press("ArrowUp");
  await expect(parentItem).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(parentItem).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowDown");
  await expect(child).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(child).toHaveAttribute("aria-selected", "true");
  await expectAccessible(page);

  // C: a new case in that folder, saved with Ctrl+S.
  const title = uniq("Keyboard only");
  await page.keyboard.press("c");
  await expect(page.getByRole("heading", { name: "New test case" })).toBeVisible();
  await expect(page.getByLabel("Title")).toBeFocused();
  await page.keyboard.type(title);
  await tabTo(page, page.getByLabel("Step 1 action", { exact: true }));
  await page.keyboard.type("Open the sign-in page");
  await page.keyboard.press("Tab");
  await page.keyboard.type("The form is shown");
  await expectAccessible(page);
  await page.keyboard.press("Control+s");
  const panel = page.getByRole("complementary", { name: /SPARK-TC-\d+ details/ });
  await expect(panel.getByRole("heading", { name: title })).toBeVisible();

  // Esc closes the panel; the list row is reachable with Tab and Enter opens it again.
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  const row = page.getByRole("row").filter({ hasText: title });
  await tabTo(page, row);
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("heading", { name: title })).toBeVisible();
  await expectAccessible(page);
});

test("TCMS-143: the runner with the keyboard only", async ({ browser }) => {
  const bilal = await as(browser, "bilal");
  const pid = await spark(bilal);
  const folder = (
    await call<{ id: string }>(bilal, "POST", `/api/v1/projects/${pid}/folders`, {
      name: uniq("Runner keys"),
    })
  ).id;
  const cases: Ref[] = [];
  for (let i = 0; i < 2; i++) {
    const r = await call<{ case: Ref }>(bilal, "POST", `/api/v1/projects/${pid}/test-cases`, {
      folder_id: folder,
      content: {
        format: "steps",
        title: uniq("Keyboard run"),
        steps: [
          { action: "Open the cart", expected_result: "Cart is shown" },
          { action: "Pay", expected_result: "Receipt is shown" },
        ],
      },
    });
    cases.push(r.case);
  }
  const envs = await call<{ id: string; archived: boolean }[]>(
    bilal,
    "GET",
    `/api/v1/projects/${pid}/environments`,
  );
  const members = await call<{ user: { id: string; email: string } }[]>(
    bilal,
    "GET",
    `/api/v1/projects/${pid}/members`,
  );
  const sanaId = members.find((m) => m.user.email === "sana@acme.test")?.user.id;
  const { cycle } = await call<{ cycle: Ref & { name: string } }>(
    bilal,
    "POST",
    `/api/v1/projects/${pid}/cycles`,
    {
      name: uniq("Keyboard cycle"),
      environment_id: envs.find((e) => !e.archived)?.id,
      selection: { case_ids: cases.map((c) => c.id) },
      default_assignee_id: sanaId,
    },
  );
  const listed = await call<{ items: { id: string; test_case: { key: string } }[] }>(
    bilal,
    "GET",
    `/api/v1/cycles/${cycle.id}/runs?sort=position&page_size=50`,
  );
  const byKey = new Map(listed.items.map((r) => [r.test_case.key, r.id]));
  const runs = cases.map((c) => byKey.get(c.key) ?? "");

  const sana = await as(browser, "sana");
  await sana.goto(`/p/SPARK/cycles/${cycle.key}`);
  await tabTo(sana, sana.getByRole("button", { name: "Start testing" }));
  await sana.keyboard.press("Enter");
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[0]}$`));

  // Shift+N / Shift+P walk the queue.
  await expect(sana.getByRole("button", { name: /Next/ })).toBeEnabled();
  await sana.keyboard.press("Shift+N");
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[1]}$`));
  await expect(sana.getByRole("button", { name: /Prev/ })).toBeEnabled();
  await sana.keyboard.press("Shift+P");
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[0]}$`));

  // ? shows the runner's own list (one dialog, not the global one on top).
  await sana.keyboard.press("?");
  await expect(sana.getByRole("dialog")).toHaveCount(1);
  await expect(sana.getByRole("dialog", { name: "Keyboard shortcuts" })).toContainText(
    "Next or previous run",
  );
  await sana.keyboard.press("Escape");
  await expect(sana.getByRole("dialog")).toHaveCount(0);

  // Space starts; P passes step 1; F fails step 2 and focuses the actual result; Esc leaves it.
  await sana.keyboard.press("Space");
  await expect(sana.getByRole("button", { name: /Finish run/ })).toBeVisible();
  await expectAccessible(sana);
  await sana.keyboard.press("p");
  await sana.keyboard.press("f");
  const actual = sana.getByLabel("Actual result");
  await expect(actual).toBeFocused();
  await sana.keyboard.type("Receipt never arrives");
  await sana.keyboard.press("Escape");
  await expect(sana.locator("[data-preview=failed]")).toBeVisible();
  await expect(sana.getByRole("list", { name: "Steps" }).getByText("Saved")).toHaveCount(2);

  // ? also works with a draft open (the step grid owns the key then).
  await sana.keyboard.press("?");
  await expect(sana.getByRole("dialog")).toHaveCount(1);
  await sana.keyboard.press("Escape");

  // Ctrl+Enter finishes and moves to the next run.
  await sana.keyboard.press("Control+Enter");
  await expect(sana.getByText(/Failed · Next/)).toBeVisible();
  await expect(sana).toHaveURL(new RegExp(`/run/${runs[1]}$`));
  const finished = await call<{ status: string }>(bilal, "GET", `/api/v1/runs/${runs[0]}`);
  expect(finished.status).toBe("failed");
});
