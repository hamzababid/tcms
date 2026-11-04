import { formatCount, formatPercent, type Rate } from "@/lib/format";

export interface MetricProps {
  /** Short label for the counts, e.g. "passed" → "180 of 205 passed". */
  noun: string;
  rate: Rate;
  /** Shown instead of counts when the rate is undefined, e.g. "0 executed yet". */
  emptyText?: string;
}

/** Every percentage is shown with its counts; undefined rates show "—" (BR-24, docs/07 §1.5). */
export function Metric({ noun, rate, emptyText }: MetricProps) {
  const undefinedRate = rate.value === null;
  const counts = undefinedRate
    ? (emptyText ?? `${formatCount(rate.denominator)} in denominator`)
    : `${formatCount(rate.numerator)} of ${formatCount(rate.denominator)} ${noun}`;
  return (
    <span className="inline-flex items-baseline gap-2">
      <span className="text-2xl font-semibold tabular-nums text-ink">{formatPercent(rate.value)}</span>
      <span className="text-sm text-ink-secondary tabular-nums">{counts}</span>
    </span>
  );
}
