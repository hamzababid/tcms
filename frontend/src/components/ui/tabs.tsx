import * as T from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

export function Tabs({
  value,
  onValueChange,
  items,
  label,
}: {
  value: string;
  onValueChange: (v: string) => void;
  items: { value: string; label: string; content: ReactNode }[];
  label: string;
}) {
  return (
    <T.Root value={value} onValueChange={onValueChange}>
      <T.List aria-label={label} className="mb-6 flex gap-1 overflow-x-auto border-b border-border">
        {items.map((i) => (
          <T.Trigger
            key={i.value}
            value={i.value}
            className="-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-medium text-ink-secondary hover:text-ink data-[state=active]:border-accent data-[state=active]:text-ink"
          >
            {i.label}
          </T.Trigger>
        ))}
      </T.List>
      {items.map((i) => (
        <T.Content key={i.value} value={i.value} className="focus:outline-none">
          {i.content}
        </T.Content>
      ))}
    </T.Root>
  );
}
