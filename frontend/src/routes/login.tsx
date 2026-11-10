import { createFileRoute } from "@tanstack/react-router";

import { LoginPage } from "@/features/auth/LoginPage";

export const Route = createFileRoute("/login")({
  validateSearch: (s: Record<string, unknown>): { returnTo?: string } =>
    typeof s.returnTo === "string" && /^\/(?![/\\])/.test(s.returnTo) ? { returnTo: s.returnTo } : {}, // same-origin path only, never "//host"
  component: function Login() {
    const { returnTo } = Route.useSearch();
    return <LoginPage returnTo={returnTo} />;
  },
});
