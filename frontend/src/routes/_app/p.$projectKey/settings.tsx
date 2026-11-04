import { createFileRoute } from "@tanstack/react-router";

import { useProject } from "@/api/queries";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { SettingsPage } from "@/features/projects/SettingsPage";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/settings")({
  validateSearch: (s: Record<string, unknown>): { tab?: string } =>
    typeof s.tab === "string" ? { tab: s.tab } : {},
  component: function Settings() {
    const summary = useRouteProject();
    const project = useProject(summary.id); // includes row_version for edits
    const { tab } = Route.useSearch();
    const navigate = Route.useNavigate();
    if (project.isPending)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    if (project.isError)
      return (
        <div className="p-6">
          <ErrorState error={project.error} />
        </div>
      );
    return (
      <SettingsPage
        project={project.data}
        tab={tab ?? "general"}
        onTab={(t) => void navigate({ search: { tab: t } })}
      />
    );
  },
});
