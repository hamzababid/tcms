import * as T from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Underlined tabs (docs/design/Repository.dc.html): 38 px, 13 px, active 600 + indigo underline. */
export function Tabs({
  value,
  onValueChange,
  items,
  label,
  className,
  listClassName,
  contentClassName = "pt-6",
}: {
  value: string;
  onValueChange: (v: string) => void;
  items: { value: string; label: string; count?: number; content: ReactNode }[];
  label: string;
  className?: string;
  listClassName?: string;
  contentClassName?: string;
}) {
  return (
    <T.Root value={value} onValueChange={onValueChange} className={className}>
      <T.List
        aria-label={label}
        className={cn("flex gap-1 overflow-x-auto border-b border-border", listClassName)}
      >
        {items.map((i) => (
          <T.Trigger
            key={i.value}
            value={i.value}
            className="-mb-px inline-flex h-[38px] items-center gap-1.5 whitespace-nowrap rounded-t-[4px] border-b-2 border-transparent px-2.5 focus-visible:bg-accent-tint focus-visible:outline-none text-[13px] font-medium text-ink-secondary transition-colors hover:text-ink data-[state=active]:border-accent data-[state=active]:font-semibold data-[state=active]:text-ink"
          >
            {i.label}
            {i.count !== undefined ? (
              <span className="tabular rounded-full bg-surface-muted px-1.5 text-[11.5px] font-medium leading-[18px] text-ink-secondary">
                {i.count}
              </span>
            ) : null}
          </T.Trigger>
        ))}
      </T.List>
      {items.map((i) => (
        <T.Content key={i.value} value={i.value} className={cn("focus:outline-none", contentClassName)}>
          {i.content}
        </T.Content>
      ))}
    </T.Root>
  );
}
