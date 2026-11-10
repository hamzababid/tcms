/** Notification bell (docs/07 §3; US-170, AC-NTF-01): unread count, latest 20, open = mark read. */
import * as P from "@radix-ui/react-popover";
import { useNavigate } from "@tanstack/react-router";
import { Bell as BellIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  markRead,
  useInvalidateNotifications,
  useNotifications,
  useUnreadCount,
  type NotificationItem,
} from "./api";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const count = useUnreadCount();
  const list = useNotifications(open);
  const invalidate = useInvalidateNotifications();
  const navigate = useNavigate();
  const unread = count.data ?? 0;
  const openItem = async (n: NotificationItem) => {
    if (!n.read_at) await markRead({ ids: [n.id] });
    invalidate();
    setOpen(false);
    if (!n.url) return;
    if (n.url.startsWith("/api/")) window.location.assign(n.url);
    else void navigate({ to: n.url });
  };
  return (
    <P.Root open={open} onOpenChange={setOpen}>
      <P.Trigger asChild>
        <button
          type="button"
          // The name contains the badge text, so "99+" must be in it too (axe label-content-name-mismatch).
          aria-label={unread ? `Notifications, ${unread > 99 ? "99+" : unread} unread` : "Notifications"}
          className="relative flex size-8 items-center justify-center rounded-control text-ink-secondary hover:bg-surface-muted hover:text-ink"
        >
          <BellIcon aria-hidden="true" className="size-[18px]" />
          {unread ? (
            <span
              aria-hidden="true"
              className="tabular absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-[var(--status-fail-bar)] px-1 text-center text-[11px] font-semibold leading-[18px] text-white"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          ) : null}
        </button>
      </P.Trigger>
      <P.Portal>
        <P.Content
          align="end"
          sideOffset={6}
          aria-label="Notifications"
          className="z-50 w-[380px] rounded-card border border-border bg-surface text-[13px] shadow-[var(--shadow-popover)]"
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <h2 className="text-[14px] font-semibold text-ink">Notifications</h2>
            <Button
              variant="link"
              size="xs"
              disabled={!unread}
              onClick={() => {
                void markRead({ all: true }).then(invalidate);
              }}
            >
              Mark all read
            </Button>
          </div>
          {list.isPending ? (
            <p className="px-4 py-6 text-center text-ink-secondary">Loading…</p>
          ) : !list.data || list.data.items.length === 0 ? (
            <p className="px-4 py-6 text-center text-ink-secondary">No notifications yet.</p>
          ) : (
            <ul
              aria-label="Latest notifications"
              className="max-h-[420px] divide-y divide-border overflow-y-auto"
            >
              {list.data.items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    className={cn(
                      "flex w-full flex-col gap-0.5 px-4 py-2.5 text-left hover:bg-surface-muted",
                      !n.read_at && "bg-accent-tint/40",
                    )}
                    onClick={() => void openItem(n)}
                  >
                    <span className={cn("text-ink", !n.read_at && "font-medium")}>
                      {!n.read_at ? <span className="sr-only">Unread: </span> : null}
                      {n.title}
                    </span>
                    <span className="text-xs text-ink-secondary">
                      {n.project_key ? `${n.project_key} · ` : ""}
                      {formatDateTime(n.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="border-t border-border px-4 py-2 text-xs text-ink-secondary">
            Email settings: Your account › Notifications
          </div>
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}
