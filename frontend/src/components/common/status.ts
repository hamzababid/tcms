/**
 * The single mapping from statuses to tone, icon and label (docs/07 §6.2). Only StatusBadge and
 * ProgressBar read it; no other component may map statuses to colours or icons.
 */
import {
  Archive,
  ArchiveX,
  Ban,
  CalendarClock,
  Check,
  CheckCircle2,
  Circle,
  CircleAlert,
  CircleDashed,
  CirclePause,
  CircleSlash,
  Contrast,
  Hourglass,
  ListChecks,
  Lock,
  Octagon,
  Pencil,
  PlayCircle,
  RotateCw,
  SkipForward,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";

export type Tone = "pass" | "fail" | "blocked" | "skip" | "progress" | "notrun" | "na" | "retest";

export interface StatusSpec {
  label: string;
  tone: Tone;
  icon: LucideIcon;
  /** Dashed outline (e.g. requirement "not covered"). */
  dashed?: boolean;
}

/** Run, attempt and step statuses plus the needs-retest flag. */
export const EXECUTION_STATUS = {
  passed: { label: "Passed", tone: "pass", icon: CheckCircle2 },
  failed: { label: "Failed", tone: "fail", icon: XCircle },
  blocked: { label: "Blocked", tone: "blocked", icon: Octagon },
  skipped: { label: "Skipped", tone: "skip", icon: SkipForward },
  not_applicable: { label: "N/A", tone: "na", icon: CircleSlash },
  in_progress: { label: "In progress", tone: "progress", icon: Contrast },
  not_run: { label: "Not run", tone: "notrun", icon: Circle },
  needs_retest: { label: "Needs retest", tone: "retest", icon: RotateCw },
} as const satisfies Record<string, StatusSpec>;

export const CASE_STATUS = {
  draft: { label: "Draft", tone: "skip", icon: Pencil },
  in_review: { label: "In review", tone: "progress", icon: Hourglass },
  approved: { label: "Approved", tone: "pass", icon: Check },
  deprecated: { label: "Deprecated", tone: "blocked", icon: ArchiveX },
  archived: { label: "Archived", tone: "na", icon: Archive },
} as const satisfies Record<string, StatusSpec>;

/** Defect statuses grouped by category colour (docs/07 §6.2). */
export const DEFECT_STATUS = {
  open: { label: "Open", tone: "fail", icon: CircleAlert },
  reopened: { label: "Reopened", tone: "fail", icon: CircleAlert },
  triaged: { label: "Triaged", tone: "blocked", icon: ListChecks },
  assigned: { label: "Assigned", tone: "blocked", icon: ListChecks },
  in_progress: { label: "In progress", tone: "progress", icon: Wrench },
  fixed: { label: "Fixed", tone: "progress", icon: Wrench },
  ready_for_retest: { label: "Ready for retest", tone: "retest", icon: RotateCw },
  verified: { label: "Verified", tone: "pass", icon: CheckCircle2 },
  closed: { label: "Closed", tone: "pass", icon: CheckCircle2 },
  deferred: { label: "Deferred", tone: "skip", icon: CirclePause },
  rejected: { label: "Rejected", tone: "skip", icon: Ban },
  duplicate: { label: "Duplicate", tone: "skip", icon: Ban },
  cannot_reproduce: { label: "Cannot reproduce", tone: "skip", icon: Ban },
} as const satisfies Record<string, StatusSpec>;

/** Requirement status in a release (docs/02 §10.5). */
export const REQUIREMENT_RELEASE_STATUS = {
  passed: EXECUTION_STATUS.passed,
  failed: EXECUTION_STATUS.failed,
  blocked: EXECUTION_STATUS.blocked,
  not_run: EXECUTION_STATUS.not_run,
  not_covered: { label: "Not covered", tone: "skip", icon: CircleDashed, dashed: true },
} as const satisfies Record<string, StatusSpec>;

/** Test cycle lifecycle (docs/02 §7.1). */
export const CYCLE_STATUS = {
  planned: { label: "Planned", tone: "notrun", icon: CalendarClock },
  active: { label: "Active", tone: "progress", icon: PlayCircle },
  closed: { label: "Closed", tone: "na", icon: Lock },
} as const satisfies Record<string, StatusSpec>;

/** Test plan lifecycle (docs/02 §6.1). */
export const PLAN_STATUS = {
  draft: { label: "Draft", tone: "skip", icon: Pencil },
  active: { label: "Active", tone: "progress", icon: PlayCircle },
  completed: { label: "Completed", tone: "pass", icon: CheckCircle2 },
  archived: { label: "Archived", tone: "na", icon: Archive },
} as const satisfies Record<string, StatusSpec>;

export const STATUS_KINDS = {
  execution: EXECUTION_STATUS,
  case: CASE_STATUS,
  defect: DEFECT_STATUS,
  requirement: REQUIREMENT_RELEASE_STATUS,
  cycle: CYCLE_STATUS,
  plan: PLAN_STATUS,
} as const;

export type StatusKind = keyof typeof STATUS_KINDS;
export type StatusOf<K extends StatusKind> = keyof (typeof STATUS_KINDS)[K];

/** Unknown enum values (docs/06 §2.11: tolerate and display raw). */
export function statusSpec(kind: StatusKind, status: string): StatusSpec {
  const table: Record<string, StatusSpec> = STATUS_KINDS[kind];
  return table[status] ?? { label: status, tone: "na", icon: Circle };
}

export const toneVars = (tone: Tone) => ({
  fg: `var(--status-${tone}-fg)`,
  bg: `var(--status-${tone}-bg)`,
  border: `var(--status-${tone}-border)`,
  bar: `var(--status-${tone}-bar)`,
});
