import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("app shell loads with the product name and no serious accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Primary" })).toContainText("Assay");
  await expect(page).toHaveTitle("Assay");
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
});

test("the API is reachable through the web origin", async ({ request }) => {
  const live = await request.get("/api/v1/health/live");
  expect(live.ok()).toBe(true);
  expect(await live.json()).toEqual({ status: "ok" });
  const ready = await request.get("/api/v1/health/ready");
  expect(ready.status(), JSON.stringify(await ready.json())).toBe(200);
});

test("unknown API routes return problem+json", async ({ request }) => {
  const r = await request.get("/api/v1/no-such-route");
  expect(r.status()).toBe(404);
  expect(r.headers()["content-type"]).toBe("application/problem+json");
  expect((await r.json()).code).toBe("not_found");
});
