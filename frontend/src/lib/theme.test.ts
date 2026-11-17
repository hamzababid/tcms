import { afterEach, describe, expect, it } from "vitest";

import { applyTheme, isChoice, resolveTheme, storedChoice, THEME_KEY } from "./theme";

describe("theme", () => {
  afterEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("resolves System from the device setting", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("defaults to System and ignores unknown stored values", () => {
    expect(storedChoice()).toBe("system");
    localStorage.setItem(THEME_KEY, "sepia");
    expect(storedChoice()).toBe("system");
    expect(isChoice("sepia")).toBe(false);
  });

  it("applies a choice to <html> and remembers it", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(storedChoice()).toBe("dark");
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
