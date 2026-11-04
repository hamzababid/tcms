import { type StatusKind, statusSpec, toneVars } from "./status";

export interface StatusBadgeProps {
  kind: StatusKind;
  status: string;
  /** Compact form shows only the icon; the label stays available to assistive technology. */
  compact?: boolean;
}

/** Status is never colour alone: icon + label + colour (docs/07 §1.6). */
export function StatusBadge({ kind, status, compact = false }: StatusBadgeProps) {
  const spec = statusSpec(kind, status);
  const Icon = spec.icon;
  const c = toneVars(spec.tone);
  return (
    <span
      className="inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-full border px-2 text-xs font-medium"
      style={{
        color: c.fg,
        background: c.bg,
        borderColor: c.border,
        borderStyle: spec.dashed ? "dashed" : "solid",
      }}
      data-status={status}
      title={compact ? spec.label : undefined}
    >
      <Icon aria-hidden="true" className="size-3.5 shrink-0" strokeWidth={2.25} />
      {compact ? <span className="sr-only">{spec.label}</span> : spec.label}
    </span>
  );
}
