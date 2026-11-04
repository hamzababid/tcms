import { render, screen } from "@testing-library/react";

import { formatPercent, formatRate } from "@/lib/format";

import { Metric } from "./Metric";
import { ProgressBar } from "./ProgressBar";

describe("Metric", () => {
  it("shows the percentage with numerator and denominator", () => {
    render(<Metric noun="passed" rate={{ numerator: 180, denominator: 205, value: 180 / 205 }} />);
    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.getByText("180 of 205 passed")).toBeInTheDocument();
  });

  it('shows "—" for an undefined rate, never 0% (BR-24)', () => {
    render(
      <Metric
        noun="passed"
        rate={{ numerator: 0, denominator: 0, value: null }}
        emptyText="0 executed yet"
      />,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("0 executed yet")).toBeInTheDocument();
    expect(screen.queryByText("0%")).toBeNull();
  });
});

describe("format", () => {
  it("formats rates as 'x of y (z%)'", () => {
    expect(formatRate({ numerator: 205, denominator: 245, value: 205 / 245 })).toBe("205 of 245 (84%)");
    expect(formatRate({ numerator: 0, denominator: 0, value: null })).toBe("—");
  });

  it("never rounds a partial result to 0% or 100%", () => {
    expect(formatPercent(0.001)).toBe("1%");
    expect(formatPercent(0.996)).toBe("99%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(0)).toBe("0%");
  });
});

describe("ProgressBar", () => {
  it("exposes counts in its accessible label and sizes segments by share", () => {
    const { container } = render(
      <ProgressBar counts={{ passed: 180, failed: 20, blocked: 5, skipped: 4, not_run: 36 }} />,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(
      "Passed 180, Failed 20, Blocked 5, Skipped 4, Not run 36",
    );
    const passed = container.querySelector('[data-segment="passed"]') as HTMLElement;
    expect(passed.style.width).toBe(`${(180 / 245) * 100}%`);
  });

  it("renders no segments for an empty cycle", () => {
    const { container } = render(
      <ProgressBar counts={{ passed: 0, failed: 0, blocked: 0, skipped: 0, not_run: 0 }} />,
    );
    expect(container.querySelectorAll("[data-segment]")).toHaveLength(0);
  });
});
