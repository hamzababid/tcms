import type { ReactNode } from "react";

import { Logo } from "@/app/Logo";

/** Centered card used by every sign-in screen (docs/design/Login.dc.html). */
export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <main className="flex min-h-full items-center justify-center bg-ground px-4 py-12">
      <div className="w-full max-w-sm">
        <Logo variant="light" className="mx-auto mb-6 h-10 w-auto" />
        <div className="rounded-card border border-border bg-surface p-6 shadow-sm">
          <h1 className="text-lg font-semibold text-ink">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-ink-secondary">{subtitle}</p> : null}
          <div className="mt-5">{children}</div>
        </div>
      </div>
    </main>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className="rounded-control border px-3 py-2 text-sm"
      style={{
        color: "var(--status-fail-fg)",
        background: "var(--status-fail-bg)",
        borderColor: "var(--status-fail-border)",
      }}
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
