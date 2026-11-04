import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge";
import {
  CASE_STATUS,
  DEFECT_STATUS,
  EXECUTION_STATUS,
  REQUIREMENT_RELEASE_STATUS,
  STATUS_KINDS,
} from "./status";

describe("StatusBadge", () => {
  it("always renders a text label (status is never colour alone)", () => {
    render(<StatusBadge kind="execution" status="failed" />);
    expect(screen.getByText("Failed")).toBeVisible();
  });

  it("keeps the label for assistive technology in compact mode", () => {
    render(<StatusBadge kind="execution" status="blocked" compact />);
    expect(screen.getByText("Blocked")).toHaveClass("sr-only");
  });

  it("renders unknown enum values raw instead of failing (docs/06 §2.11)", () => {
    render(<StatusBadge kind="defect" status="new_future_state" />);
    expect(screen.getByText("new_future_state")).toBeInTheDocument();
  });

  it("covers every enum value of the API", () => {
    expect(Object.keys(EXECUTION_STATUS).sort()).toEqual([
      "blocked",
      "failed",
      "in_progress",
      "needs_retest",
      "not_applicable",
      "not_run",
      "passed",
      "skipped",
    ]);
    expect(Object.keys(CASE_STATUS).sort()).toEqual([
      "approved",
      "archived",
      "deprecated",
      "draft",
      "in_review",
    ]);
    expect(Object.keys(DEFECT_STATUS)).toHaveLength(13);
    expect(Object.keys(REQUIREMENT_RELEASE_STATUS).sort()).toEqual([
      "blocked",
      "failed",
      "not_covered",
      "not_run",
      "passed",
    ]);
  });

  it("never gives two execution statuses the same icon", () => {
    const icons = Object.values(EXECUTION_STATUS).map((s) => s.icon);
    expect(new Set(icons).size).toBe(icons.length);
  });

  it("uses only design-token colours", () => {
    for (const table of Object.values(STATUS_KINDS)) {
      for (const status of Object.keys(table)) {
        const { container } = render(<StatusBadge kind="execution" status={status} />);
        const style = (container.firstChild as HTMLElement).getAttribute("style") ?? "";
        expect(style).toMatch(/var\(--status-/);
        expect(style).not.toMatch(/#[0-9a-f]{3,8}/i);
      }
    }
  });
});
