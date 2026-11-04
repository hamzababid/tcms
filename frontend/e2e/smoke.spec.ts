import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("signed-out visitors get the sign-in page with the product name, accessibly", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("img", { name: "Assay" })).toBeVisible(); // logo from docs/brand
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
  const body = (await r.json()) as { code: string };
  expect(body.code).toBe("not_found");
});

test("brand assets from docs/brand are served (favicon, touch icon, manifest, logos)", async ({
  request,
  page,
}) => {
  for (const path of [
    "/favicon.ico",
    "/favicon.svg",
    "/apple-touch-icon.png",
    "/site.webmanifest",
    "/brand/assay-logo.svg",
    "/brand/assay-logo-on-dark.svg",
    "/brand/assay-mark-on-dark.svg",
    "/brand/assay-logo-64h.png",
    "/brand/assay-app-icon-192.png",
    "/brand/assay-app-icon-512.png",
  ]) {
    const r = await request.get(path);
    expect(r.status(), path).toBe(200);
  }
  await page.goto("/login");
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute(
    "href",
    "/favicon.svg",
  );
  const logo = page.getByRole("img", { name: "Assay" });
  await expect.poll(() => logo.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
});
