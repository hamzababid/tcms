import { CASE_STATUS } from "@/components/common/status";

/** Display labels for test design enums (values come from the API, docs/06 §2.11). */
export const PRIORITIES = ["critical", "high", "medium", "low"] as const;

export const CASE_TYPES = {
  functional: "Functional",
  integration: "Integration",
  end_to_end: "End to end",
  api: "API",
  ui: "UI",
  data_validation: "Data validation",
  performance: "Performance",
  security: "Security",
  compatibility: "Compatibility",
  usability: "Usability",
} as const;

export const TECHNIQUES = {
  positive: "Positive",
  negative: "Negative",
  boundary_value: "Boundary value",
  equivalence_partitioning: "Equivalence partitioning",
  error_guessing: "Error guessing",
} as const;

export const AUTOMATION = {
  manual: "Manual",
  automated: "Automated",
  to_be_automated: "To be automated",
  not_automatable: "Not automatable",
} as const;

export function label(table: Record<string, string>, value: string | null | undefined): string {
  if (!value) return "—";
  return table[value] ?? value;
}

export const PRIORITY_LABELS: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

/** Labels only; tone and icon stay in StatusBadge (docs/07 §6.2). */
export const CASE_STATUS_LABELS: Record<string, string> = Object.fromEntries(
  Object.entries(CASE_STATUS).map(([k, v]) => [k, v.label]),
);
