import { createFileRoute } from "@tanstack/react-router";

import { ProfilePage } from "@/features/profile/ProfilePage";

const TABS = ["profile", "sessions", "tokens", "security", "notifications"];

export const Route = createFileRoute("/_app/profile")({
  validateSearch: (s: Record<string, unknown>): { tab?: string } =>
    typeof s.tab === "string" && TABS.includes(s.tab) ? { tab: s.tab } : {},
  component: function Profile() {
    const { tab } = Route.useSearch();
    const navigate = Route.useNavigate();
    return <ProfilePage tab={tab ?? "profile"} onTab={(t) => void navigate({ search: { tab: t } })} />;
  },
});
