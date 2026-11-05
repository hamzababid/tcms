import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

// docs/design/Main.dc.html: 36 px (32 in dense toolbars, 28 in filter/bulk bars), 6 px radius,
// 500 weight; destructive is an outline; disabled is a muted fill, not opacity.
const buttonVariants = cva(
  "inline-flex shrink-0 select-none items-center justify-center gap-2 whitespace-nowrap rounded-control border font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)] disabled:pointer-events-none disabled:border-border disabled:bg-surface-muted disabled:text-ink-muted [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "border-accent bg-accent text-white hover:border-accent-hover hover:bg-accent-hover active:bg-accent-active",
        secondary: "border-border-control bg-surface text-ink hover:bg-ground active:bg-surface-muted",
        ghost:
          "border-transparent bg-transparent text-ink-body hover:bg-surface-muted hover:text-ink disabled:border-transparent disabled:bg-transparent",
        destructive: "border-danger bg-surface text-danger hover:bg-danger-surface",
        tint: "border-accent-border-strong bg-surface text-accent-ink hover:bg-accent-tint",
        link: "h-auto border-transparent bg-transparent px-0 text-link hover:text-[var(--link-hover)] hover:underline disabled:bg-transparent",
      },
      size: {
        default: "h-9 px-3.5 text-sm",
        sm: "h-8 px-3 text-[13px]",
        xs: "h-7 px-2.5 text-[12.5px]",
        lg: "h-[42px] px-4 text-sm font-semibold",
        icon: "size-8 p-0",
      },
    },
    compoundVariants: [{ variant: "link", className: "h-auto px-0" }],
    defaultVariants: { variant: "primary", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        type={asChild ? undefined : (type ?? "button")}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
