import { createFileRoute } from "@tanstack/react-router";

import { MfaPage } from "@/features/auth/MfaPage";

export const Route = createFileRoute("/login_/mfa")({
  validateSearch: (s: Record<string, unknown>): { returnTo?: string } =>
    typeof s.returnTo === "string" && s.returnTo.startsWith("/") ? { returnTo: s.returnTo } : {},
  component: function Mfa() {
    const { returnTo } = Route.useSearch();
    return <MfaPage returnTo={returnTo} />;
  },
});
