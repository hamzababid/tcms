import type { ReactNode } from "react";

import { Logo } from "@/app/Logo";

/** Centered card used by every sign-in screen (docs/design/Login.dc.html): 380 px, 10 px radius. */
export function AuthCard({
  title,
  subtitle,
  icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="flex min-h-full flex-col items-center justify-center bg-ground px-4 py-12">
      <div className="w-full max-w-[380px] rounded-[var(--radius-auth)] border border-border bg-surface p-8 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
        {icon ? (
          <div className="mb-[18px] flex size-10 items-center justify-center rounded-full bg-accent-tint text-accent-ink">
            {icon}
          </div>
        ) : (
          <Logo variant="light" className="mb-[18px] h-8 w-auto" />
        )}
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {subtitle ? <p className="mt-1.5 text-[13.5px] leading-5 text-ink-secondary">{subtitle}</p> : null}
        <div className="mt-[18px]">{children}</div>
      </div>
      <p className="mt-6 text-xs text-ink-muted">Self-hosted test case management</p>
    </main>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="rounded-control border border-danger-border bg-danger-surface px-3 py-2.5 text-[13px] text-danger-ink"
    >
      {message}
    </p>
  );
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}
