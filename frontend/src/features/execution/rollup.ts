/**
 * Live result preview in the runner (docs/07 §5.9, docs/design/Runner.dc.html). It mirrors BR-09 so the
 * tester sees what Finish will record; the server computes the real status (CLAUDE.md rule 4).
 */
import type { StepStatus } from "./api";

export interface Preview {
  /** The status Finish records, or null when the steps alone are not enough. */
  status: "passed" | "failed" | "blocked" | null;
  label: string;
  hint: string;
  /** Finish needs a run-level outcome (Block / Skip / N/A) with a reason. */
  incomplete: boolean;
  /** Finish will ask for a reason (BR-10, review K2). */
  needsReason: boolean;
  notRecorded: number;
  skipped: number;
}

export function previewOf(steps: StepStatus[]): Preview {
  const notRecorded = steps.filter((s) => s === "not_run").length;
  const skipped = steps.filter((s) => s === "skipped").length;
  const base = { notRecorded, skipped };
  if (steps.includes("failed"))
    return {
      ...base,
      status: "failed",
      label: "Failed",
      hint: "A failed step makes the run Failed, whatever the other steps say. Failed steps need an actual result.",
      incomplete: false,
      needsReason: false,
    };
  if (steps.includes("blocked"))
    return {
      ...base,
      status: "blocked",
      label: "Blocked",
      hint: "No failures and at least one blocked step: the run is Blocked. You will be asked for a reason.",
      incomplete: false,
      needsReason: true,
    };
  if (notRecorded === 0 && steps.includes("passed"))
    return {
      ...base,
      status: "passed",
      label: skipped ? `Passed · ${skipped} skipped` : "Passed",
      hint: skipped
        ? "Skipped steps are allowed in a pass and are flagged on the result."
        : "All steps passed.",
      incomplete: false,
      needsReason: false,
    };
  return {
    ...base,
    status: null,
    label: "Incomplete",
    hint: notRecorded
      ? `${notRecorded} ${notRecorded === 1 ? "step" : "steps"} not recorded. Record them, or Block / Skip / mark N/A the run with a reason.`
      : "All steps skipped: choose Skip or N/A for the run with a reason.",
    incomplete: true,
    needsReason: false,
  };
}
