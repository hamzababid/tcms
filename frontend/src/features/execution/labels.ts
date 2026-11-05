import type { FilterOption } from "@/components/common/DataTable";

import type { CycleStatus } from "./api";

export const CYCLE_STATUS_LABEL: Record<CycleStatus, string> = {
  planned: "Planned",
  active: "Active",
  closed: "Closed",
};

export const CYCLE_STATUS_OPTIONS: FilterOption[] = [
  { value: "planned", label: "Planned" },
  { value: "active", label: "Active" },
  { value: "closed", label: "Closed" },
];

export const RUN_STATUS_OPTIONS: FilterOption[] = [
  { value: "not_run", label: "Not run" },
  { value: "in_progress", label: "In progress" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "blocked", label: "Blocked" },
  { value: "skipped", label: "Skipped" },
  { value: "not_applicable", label: "N/A" },
];
