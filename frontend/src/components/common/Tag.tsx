import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Tag / version pill (docs/design/Main.dc.html "Keys, tags, shortcuts"). */
export function Tag({
  children,
  tone = "accent",
  className,
}: {
  children: ReactNode;
  tone?: "accent" | "neutral";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-full px-2 text-xs",
        tone === "accent" ? "bg-accent-tint text-accent-ink" : "bg-surface-muted text-ink-body",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Keycap. `onAccent` for use inside a primary button. */
export function Kbd({ children, onAccent = false }: { children: ReactNode; onAccent?: boolean }) {
  return onAccent ? (
    <kbd className="rounded-[3px] bg-accent-soft px-[5px] font-mono text-[11px] leading-4 text-white">
      {children}
    </kbd>
  ) : (
    <kbd className="rounded border border-b-2 border-border-control bg-surface px-1.5 font-mono text-[11.5px] leading-4 text-ink">
      {children}
    </kbd>
  );
}
