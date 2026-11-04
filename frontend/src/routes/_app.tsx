import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";

import { api, ApiError } from "@/api/client";
import { keys } from "@/api/queries";
import { AppShell } from "@/app/AppShell";

/** Every signed-in page: session required, second factor done, MFA enrolled when required. */
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    try {
      const me = await context.queryClient.query({
        staleTime: 30_000,
        queryKey: keys.me,
        queryFn: async () => (await api.GET("/api/v1/auth/me")).data,
      });
      if (me && me.mfa.required && !me.mfa.enrolled) {
        throw redirect({ to: "/setup-mfa" });
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === "mfa_required") throw redirect({ to: "/login/mfa" });
      if (e instanceof ApiError && e.status === 401)
        throw redirect({ to: "/login", search: { returnTo: location.href } });
      throw e;
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});
