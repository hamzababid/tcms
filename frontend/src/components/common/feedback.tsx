import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";

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
            className="flex items-center gap-2 rounded-card border border-border bg-surface px-4 py-3 text-sm text-ink shadow-md"
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
    <div role="alert" className="rounded-card border border-border bg-surface p-6 text-sm">
      <p className="font-medium text-ink">{errorMessage(error)}</p>
      {requestId ? <p className="mt-1 font-mono text-xs text-ink-muted">Request {requestId}</p> : null}
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="rounded-card border border-dashed border-border bg-surface p-8 text-center text-sm text-ink-secondary">
      <p>{text}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  const items = useMemo(() => Array.from({ length: rows }, (_, i) => i), [rows]);
  return (
    <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
      {items.map((i) => (
        <div key={i} className="h-10 animate-pulse rounded-control bg-[var(--border)]" />
      ))}
    </div>
  );
}

export function PageHeader({
  title,
  actions,
  subtitle,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-ink-secondary">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex gap-2">{actions}</div> : null}
    </div>
  );
}
