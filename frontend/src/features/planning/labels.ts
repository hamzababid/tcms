import type { FilterOption } from "@/components/common/DataTable";

import type { PlanStatus, PlanType } from "./api";

export const PLAN_TYPES: FilterOption[] = [
  { value: "functional", label: "Functional" },
  { value: "integration", label: "Integration" },
  { value: "regression", label: "Regression" },
  { value: "release_validation", label: "Release validation" },
  { value: "uat", label: "UAT" },
  { value: "smoke", label: "Smoke" },
  { value: "performance", label: "Performance" },
  { value: "security", label: "Security" },
];

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  draft: "Draft",
  active: "Active",
  completed: "Completed",
  archived: "Archived",
};

export const PLAN_TYPE_LABEL: Record<PlanType, string> = Object.fromEntries(
  PLAN_TYPES.map((t) => [t.value, t.label]),
) as Record<PlanType, string>;
