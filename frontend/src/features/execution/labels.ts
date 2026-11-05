import type { FilterOption } from "@/components/common/DataTable";
import { CYCLE_STATUS, EXECUTION_STATUS } from "@/components/common/status";

import type { CycleStatus } from "./api";

/** Labels only; tone and icon stay in StatusBadge (docs/07 §6.2). */
export const CYCLE_STATUS_LABEL = Object.fromEntries(
  Object.entries(CYCLE_STATUS).map(([k, v]) => [k, v.label]),
) as Record<CycleStatus, string>;

export const CYCLE_STATUS_OPTIONS: FilterOption[] = Object.entries(CYCLE_STATUS_LABEL).map(
  ([value, label]) => ({ value, label }),
);

const RUN_STATUSES = [
  "not_run",
  "in_progress",
  "passed",
  "failed",
  "blocked",
  "skipped",
  "not_applicable",
] as const;

export const RUN_STATUS_OPTIONS: FilterOption[] = RUN_STATUSES.map((s) => ({
  value: s,
  label: EXECUTION_STATUS[s].label,
}));

/** Legend order of the progress card (docs/07 §5.8). */
export const LEGEND = ["passed", "failed", "blocked", "skipped", "in_progress", "not_run"] as const;

/** Why a newer version cannot replace the pinned one in place (docs/02 §7.2, BR-04/05). */
export const NEWER_VERSION_REASON: Record<string, string> = {
  run_has_results: "The run has results: replace it with a new run to test the newer version.",
  cycle_closed: "The cycle is closed.",
  run_superseded: "The run has been superseded.",
};

/** Default name for the next cycle from a plan (docs/07 §5.7 "Create cycle"). */
export const nextCycleName = (planName: string, existing: number) => `${planName} – Cycle ${existing + 1}`;
