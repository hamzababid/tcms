import { formatCount } from "@/lib/format";

import { EXECUTION_STATUS, toneVars } from "./status";

export interface ProgressCounts {
  passed: number;
  failed: number;
  blocked: number;
  skipped: number;
  /** Optional: cycle progress also shows runs with a draft attempt (docs/design/CycleDetail.dc.html). */
  in_progress?: number;
  not_run: number;
}

const SEGMENTS = ["passed", "failed", "blocked", "skipped", "in_progress", "not_run"] as const;

/** Segmented P/F/B/S/NR bar with counts in the accessible label and tooltip (docs/04 §11.4). */
export function ProgressBar({ counts, className = "" }: { counts: ProgressCounts; className?: string }) {
  const segments = SEGMENTS.filter((s) => s !== "in_progress" || counts.in_progress !== undefined);
  const n = (s: (typeof SEGMENTS)[number]) => counts[s] ?? 0;
  const total = segments.reduce((sum, s) => sum + n(s), 0);
  const label = segments.map((s) => `${EXECUTION_STATUS[s].label} ${formatCount(n(s))}`).join(", ");
  return (
    <div
      role="img"
      aria-label={label}
      title={label}
      className={`flex h-2 w-full overflow-hidden rounded-full ${className}`}
      style={{ background: toneVars("notrun").bar }}
    >
      {total > 0 &&
        segments.map((s) =>
          n(s) > 0 ? (
            <div
              key={s}
              data-segment={s}
              style={{
                width: `${(n(s) / total) * 100}%`,
                background: toneVars(EXECUTION_STATUS[s].tone).bar,
              }}
            />
          ) : null,
        )}
    </div>
  );
}
