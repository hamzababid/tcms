import type { FilterOption } from "@/components/common/DataTable";
import { PLAN_STATUS } from "@/components/common/status";

import type { ExitRule, PlanStatus, PlanType } from "./api";

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

/** Labels only; tone and icon stay in StatusBadge (docs/07 §6.2). */
export const PLAN_STATUS_LABEL = Object.fromEntries(
  Object.entries(PLAN_STATUS).map(([k, v]) => [k, v.label]),
) as Record<PlanStatus, string>;

export const PLAN_STATUS_OPTIONS: FilterOption[] = Object.entries(PLAN_STATUS_LABEL).map(
  ([value, label]) => ({
    value,
    label,
  }),
);

export const PLAN_TYPE_LABEL: Record<PlanType, string> = Object.fromEntries(
  PLAN_TYPES.map((t) => [t.value, t.label]),
) as Record<PlanType, string>;

/** Button label for moving a plan into each target status (docs/02 §6.1); `archived` has its own action. */
export const STATUS_ACTION_LABEL: Record<PlanStatus, string> = {
  draft: "Back to draft",
  active: "Activate",
  completed: "Mark completed",
  archived: "Archive",
};

export type RuleType = ExitRule["type"];

/**
 * Readiness rules (docs/02 §11.4, docs/06 §5.9): percentage rules store a fraction 0–1, count rules
 * a whole number; `tag_fully_executed` needs a tag. `max_failed` replaced `max_open_defects` (ADR-023).
 */
export const RULE_TYPES: Record<RuleType, { label: string; kind: "percent" | "count" | "tag" }> = {
  min_execution_progress: { label: "Execution progress ≥", kind: "percent" },
  min_pass_rate: { label: "Pass rate ≥", kind: "percent" },
  min_pass_rate_applicable: { label: "Pass rate (applicable) ≥", kind: "percent" },
  max_failed: { label: "Failed runs ≤", kind: "count" },
  max_blocked: { label: "Blocked runs ≤", kind: "count" },
  min_requirement_coverage: { label: "Requirement coverage ≥", kind: "percent" },
  min_requirements_verified: { label: "Requirements verified ≥", kind: "percent" },
  tag_fully_executed: { label: "Every case tagged … executed", kind: "tag" },
};

export const RISK_IMPACTS = { low: "Low", medium: "Medium", high: "High" } as const;

/** "Execution progress ≥ 100%", "No failed runs", "Every case tagged smoke executed". */
export function ruleText(rule: ExitRule): string {
  // Unknown rule types are shown raw (docs/06 §2.11).
  const spec = (RULE_TYPES as Partial<Record<string, (typeof RULE_TYPES)[RuleType]>>)[rule.type];
  if (!spec) return `${rule.type} ${rule.threshold}`;
  if (spec.kind === "tag") return `Every case tagged ${rule.params?.tag ?? "?"} executed`;
  if (spec.kind === "percent") return `${spec.label} ${Math.round(rule.threshold * 100)}%`;
  if (rule.type === "max_failed")
    return rule.threshold === 0 ? "No failed runs" : `Failed runs ≤ ${rule.threshold}`;
  return `${spec.label} ${rule.threshold}`;
}
