/** Notifications and email preferences (docs/06 §4.1, docs/02 §2.7; M7 D11, D13). */
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type NotificationItem = components["schemas"]["NotificationRead"];
export type EmailPreferences = components["schemas"]["EmailPreferences"];

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const notifKeys = {
  all: ["notifications"] as const,
  count: ["notifications", "count"] as const,
  list: ["notifications", "list"] as const,
  prefs: ["notifications", "prefs"] as const,
};

/** Polled every 60 s and when the window regains focus (no push channel in the MVP). */
export const useUnreadCount = () =>
  useQuery({
    queryKey: notifKeys.count,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    queryFn: async () => must((await api.GET("/api/v1/me/notifications/unread-count")).data).count,
  });

export const useNotifications = (enabled: boolean) =>
  useQuery({
    queryKey: notifKeys.list,
    enabled,
    queryFn: async () =>
      must((await api.GET("/api/v1/me/notifications", { params: { query: { page_size: 20 } } })).data),
  });

export async function markRead(body: { ids: string[] } | { all: true }) {
  const payload = "ids" in body ? { ids: body.ids, all: false } : { all: true };
  return must((await api.POST("/api/v1/me/notifications/read", { body: payload })).data);
}

export const useEmailPreferences = () =>
  useQuery({
    queryKey: notifKeys.prefs,
    queryFn: async () => must((await api.GET("/api/v1/me/notification-preferences")).data),
  });

export async function saveEmailPreferences(body: { mentions?: boolean; digest?: boolean }) {
  return must((await api.PATCH("/api/v1/me/notification-preferences", { body })).data);
}

export function useInvalidateNotifications() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: notifKeys.all });
  };
}
