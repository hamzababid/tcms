import { ChevronDown, ChevronsUp, ChevronUp, Equal } from "lucide-react";

const PRIORITY = {
  critical: { label: "Critical", icon: ChevronsUp },
  high: { label: "High", icon: ChevronUp },
  medium: { label: "Medium", icon: Equal },
  low: { label: "Low", icon: ChevronDown },
} as const;

/** Priority is icon + label + colour, never colour alone (docs/07 §6.2). */
export function PriorityIcon({ priority, compact = false }: { priority: string; compact?: boolean }) {
  const spec = (PRIORITY as Record<string, (typeof PRIORITY)[keyof typeof PRIORITY]>)[priority];
  const Icon = spec?.icon ?? Equal;
  const label = spec?.label ?? priority;
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium"
      style={{ color: `var(--priority-${priority}, var(--ink-secondary))` }}
      title={compact ? label : undefined}
    >
      <Icon aria-hidden="true" className="size-3.5" strokeWidth={2.5} />
      {compact ? <span className="sr-only">{label}</span> : label}
    </span>
  );
}
