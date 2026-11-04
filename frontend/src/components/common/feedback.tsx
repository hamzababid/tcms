import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Toast {
  id: number;
  text: string;
  tone: "ok" | "error";
}

const ToastContext = createContext<(text: string, tone?: Toast["tone"]) => void>(() => undefined);

/** Toasts auto-dismiss after 4 s and are announced politely (docs/07 §4.5, §8). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    window.setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="flex max-w-sm items-center gap-2.5 rounded-card border border-border bg-surface px-4 py-3 text-[13px] text-ink shadow-[var(--shadow-popover)]"
          >
            {t.tone === "ok" ? (
              <CheckCircle2 aria-hidden="true" className="size-4 text-[var(--status-pass-bar)]" />
            ) : (
              <AlertTriangle aria-hidden="true" className="size-4 text-[var(--status-fail-bar)]" />
            )}
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail ?? error.code;
  return "Something went wrong";
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className="rounded-card border border-danger-border bg-danger-surface p-5 text-[13px]">
      <p className="font-medium text-danger-ink">{errorMessage(error)}</p>
      {requestId ? <p className="mt-1 font-mono text-xs text-ink-muted">Request {requestId}</p> : null}
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ text, action, icon }: { text: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-border-control bg-surface px-6 py-10 text-center text-[13px] text-ink-secondary">
      {icon ? (
        <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-accent-tint text-accent-ink">
          {icon}
        </div>
      ) : null}
      <p className="max-w-sm">{text}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  const items = useMemo(() => Array.from({ length: rows }, (_, i) => i), [rows]);
  return (
    <div role="status" aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
      {items.map((i) => (
        <div key={i} className="h-9 animate-pulse rounded-control bg-surface-muted" />
      ))}
    </div>
  );
}

/** Page header bar (docs/design/Repository.dc.html): white, bordered, 20/600 title, dense actions. */
export function PageHeader({
  title,
  actions,
  subtitle,
  eyebrow,
}: {
  title: string;
  subtitle?: string | undefined;
  eyebrow?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border bg-surface px-6 py-4">
      <div className="min-w-0">
        {eyebrow ? <div className="mb-0.5 text-xs text-ink-secondary">{eyebrow}</div> : null}
        <h1 className="truncate text-xl font-semibold leading-7 text-ink">{title}</h1>
        {subtitle ? <p className="mt-0.5 text-[13px] text-ink-secondary">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

const WIDTHS = {
  "3xl": "max-w-3xl",
  "4xl": "max-w-4xl",
  "5xl": "max-w-5xl",
  "6xl": "max-w-6xl",
  full: "",
} as const;

/** A standard page: header bar, then padded content left-aligned with the title. */
export function Page({
  title,
  subtitle,
  eyebrow,
  actions,
  width = "5xl",
  children,
}: {
  title: string;
  subtitle?: string | undefined;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  width?: keyof typeof WIDTHS;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-full flex-col">
      <PageHeader title={title} subtitle={subtitle} eyebrow={eyebrow} actions={actions} />
      <div className="flex-1 px-6 py-6">
        <div className={WIDTHS[width]}>{children}</div>
      </div>
    </div>
  );
}

/** White card with an optional titled header row (docs/design/Dashboard.dc.html sections). */
export function Card({
  title,
  actions,
  children,
  className,
  flush = false,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={cn("rounded-card border border-border bg-surface", className)}>
      {title ? (
        <div className="flex items-center justify-between gap-3 border-b border-border px-[18px] py-3.5">
          <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={flush ? "" : "p-[18px]"}>{children}</div>
    </section>
  );
}
