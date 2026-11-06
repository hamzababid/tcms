import { describe, expect, it } from "vitest";

import { previewOf } from "./rollup";

describe("runner result preview (mirrors BR-09)", () => {
  it.each([
    [["passed", "failed", "not_run"], "failed"], // AC-EXE-01
    [["passed", "skipped", "passed"], "passed"], // AC-EXE-02
    [["passed", "blocked"], "blocked"],
    [["passed", "not_run"], null], // AC-EXE-03
    [["skipped", "skipped"], null],
  ] as const)("%j → %s", (steps, status) => {
    expect(previewOf([...steps]).status).toBe(status);
  });

  it("flags skipped steps on a pass and asks for a reason on a blocked run", () => {
    expect(previewOf(["passed", "skipped"]).label).toBe("Passed · 1 skipped");
    expect(previewOf(["blocked"]).needsReason).toBe(true);
    expect(previewOf(["passed", "not_run", "not_run"]).hint).toMatch(/^2 steps not recorded/);
    expect(previewOf(["skipped"]).hint).toMatch(/All steps skipped/);
  });
});
