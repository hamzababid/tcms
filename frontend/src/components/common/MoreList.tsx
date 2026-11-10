import * as P from "@radix-ui/react-popover";
import type { ReactNode } from "react";

/**
 * The first few items of a list in a table cell and "+N more", which opens the whole list. Keeps rows at
 * one or two lines however many items a record has (a user in 60 projects, a requirement with 40 cases).
 */
export function MoreList({
  items,
  max = 3,
  label,
}: {
  items: { key: string; node: ReactNode }[];
  max?: number;
  /** What the list is, for the button and the popover ("Projects of Sana Malik"). */
  label: string;
}) {
  const shown = items.length > max + 1 ? items.slice(0, max) : items;
  const rest = items.length - shown.length;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {shown.map((i) => (
        <span key={i.key} className="contents">
          {i.node}
        </span>
      ))}
      {rest > 0 ? (
        <P.Root>
          <P.Trigger
            aria-label={`+${rest} more: ${label}`}
            className="rounded-full px-1.5 text-xs font-medium text-link hover:underline"
          >
            +{rest} more
          </P.Trigger>
          <P.Portal>
            <P.Content
              align="start"
              sideOffset={4}
              aria-label={label}
              className="z-50 max-h-80 w-80 overflow-y-auto rounded-card border border-border bg-surface p-3 text-[13px] shadow-[var(--shadow-popover)]"
            >
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.06em] text-ink-muted">
                {label} ({items.length})
              </p>
              <span className="flex flex-wrap gap-1">
                {items.map((i) => (
                  <span key={i.key} className="contents">
                    {i.node}
                  </span>
                ))}
              </span>
            </P.Content>
          </P.Portal>
        </P.Root>
      ) : null}
    </span>
  );
}
