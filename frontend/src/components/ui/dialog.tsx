import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-[rgb(15_23_42/0.45)]" />
        <D.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-48px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-[var(--radius-auth)] border border-border bg-surface shadow-[var(--shadow-dialog)] focus:outline-none",
            wide ? "w-[min(720px,calc(100vw-32px))]" : "w-[min(480px,calc(100vw-32px))]",
          )}
        >
          <div className="flex items-start justify-between gap-4 px-6 pb-4 pt-5">
            <div className="flex flex-col gap-1">
              <D.Title className="text-base font-semibold text-ink">{title}</D.Title>
              {description ? (
                <D.Description className="text-[13px] leading-5 text-ink-secondary">
                  {description}
                </D.Description>
              ) : null}
            </div>
            <D.Close
              aria-label="Close"
              className="-mr-2 -mt-1 rounded-control p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink"
            >
              <X className="size-4" aria-hidden="true" />
            </D.Close>
          </div>
          <div className="min-h-0 overflow-y-auto px-6 pb-5">{children}</div>
          {footer ? (
            <div className="flex justify-end gap-2 rounded-b-[var(--radius-auth)] border-t border-border bg-ground px-6 py-3">
              {footer}
            </div>
          ) : null}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
