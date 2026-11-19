import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { pick } from "./pick";

// Long lists in pickers and menus (docs/07 §4.5): the project switcher and the pickers for folders, people,
// plans and projects search and scroll inside the window instead of running off the page.

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious, JSON.stringify(serious.map((v) => [v.id, v.nodes.map((n) => n.target)]))).toEqual([]);
}

test.use({ storageState: "e2e/.auth/ayesha.json" });

test("the project switcher searches, scrolls inside the window and opens with G P", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 640 });
  await page.goto("/p/SPARK");
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: /Switch project/ }).click();
  const panel = page.getByRole("dialog", { name: "Switch project" });
  const search = panel.getByRole("combobox", { name: /^Search \d/ });
  await expect(search).toBeFocused();
  const box = await panel.boundingBox();
  expect((box?.y ?? 0) + (box?.height ?? 9999)).toBeLessThanOrEqual(640);
  const list = panel.getByRole("listbox", { name: "Projects" });
  await expect(list.getByRole("option").first()).toContainText("SPARK"); // the current project first
  await expect(list.getByRole("option", { selected: true })).toContainText("SPARK Platform");
  await expectAccessible(page);

  const projects = (await (await page.request.get("/api/v1/projects")).json()) as {
    key: string;
    status: string;
  }[];
  const other = projects.find((x) => x.key !== "SPARK" && x.status === "active");
  if (!other) throw new Error("needs a second project");
  await search.fill(other.key);
  await expect(list.getByRole("option").first()).toContainText(other.key);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/p/${other.key}$`));

  // G then P opens it again with the cursor in the search box; Esc closes.
  await page.locator("body").press("g");
  await page.keyboard.press("p");
  await expect(search).toBeFocused();
  await search.fill("spark platform");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/p\/SPARK$/);
  await page.getByRole("button", { name: /Switch project/ }).click();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await page.getByRole("button", { name: /Switch project/ }).click();
  await panel.getByRole("link", { name: /All projects/ }).click();
  await expect(page).toHaveURL(/\/projects$/);
});

test("the case editor's folder picker searches folders by name and path", async ({ page }) => {
  await page.goto("/p/SPARK/cases/new");
  await expect(page.getByRole("heading", { name: "New test case" })).toBeVisible();
  const folder = page.getByRole("button", { name: "Folder", exact: true });
  await pick(page, folder, "Password Reset");
  await expect(folder).toContainText("Password Reset");
  await folder.click();
  const search = page.getByRole("combobox", { name: "Search folders" });
  await search.fill("authentication");
  // Matches the folder itself and those under it (the path is part of the search).
  await expect(page.getByRole("option", { name: /Login/ }).first()).toBeVisible();
  await expect(page.getByRole("option", { name: /Password Reset/ }).first()).toBeVisible();
  await search.fill("no folder has this name");
  await expect(page.getByText("No matches")).toBeVisible();
  await page.keyboard.press("Escape");
  await expectAccessible(page);
});
