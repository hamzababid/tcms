import * as M from "@radix-ui/react-dropdown-menu";
import { forwardRef, type ComponentPropsWithoutRef, type ElementRef } from "react";

import { cn } from "@/lib/utils";

/** Dropdown menus (Radix) in the design system's popover style. */
export const Menu = M.Root;
export const MenuTrigger = M.Trigger;

export const MenuContent = forwardRef<
  ElementRef<typeof M.Content>,
  ComponentPropsWithoutRef<typeof M.Content>
>(({ className, sideOffset = 4, collisionPadding = 8, style, ...props }, ref) => (
  <M.Portal>
    <M.Content
      ref={ref}
      sideOffset={sideOffset}
      collisionPadding={collisionPadding}
      className={cn(
        "z-50 min-w-48 overflow-y-auto rounded-card border border-border bg-surface p-1 text-[13px] text-ink shadow-[var(--shadow-popover)]",
        className,
      )}
      // Never taller than the space on screen: long menus scroll instead of running off the page.
      style={{ maxHeight: "min(480px, var(--radix-dropdown-menu-content-available-height))", ...style }}
      {...props}
    />
  </M.Portal>
));
MenuContent.displayName = "MenuContent";

export const MenuItem = forwardRef<
  ElementRef<typeof M.Item>,
  ComponentPropsWithoutRef<typeof M.Item> & { danger?: boolean }
>(({ className, danger, ...props }, ref) => (
  <M.Item
    ref={ref}
    className={cn(
      "flex h-8 cursor-pointer select-none items-center gap-2 rounded-[5px] px-2.5 outline-none data-[disabled]:pointer-events-none data-[highlighted]:bg-surface-muted data-[disabled]:opacity-50",
      danger && "text-danger data-[highlighted]:bg-danger-surface",
      className,
    )}
    {...props}
  />
));
MenuItem.displayName = "MenuItem";

export function MenuSeparator() {
  return <M.Separator className="-mx-1 my-1 h-px bg-border" />;
}

export function MenuShortcut({ children }: { children: string }) {
  return <span className="ml-auto pl-4 font-mono text-[11px] text-ink-muted">{children}</span>;
}
