import { createFileRoute, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { REPORTS, ReportsPage } from "@/features/reporting/ReportsPage";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

const TABS = new Set<string>(["quality", ...REPORTS.map((r) => r.value)]);

export const Route = createFileRoute("/_app/p/$projectKey/reports")({
  validateSearch: (s: Record<string, unknown>): { tab?: string } =>
    typeof s.tab === "string" && TABS.has(s.tab) ? { tab: s.tab } : {},
  component: function Reports() {
    const project = useRouteProject();
    const { tab } = Route.useSearch();
    const navigate = useNavigate({ from: Route.fullPath });
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    return (
      <ReportsPage
        project={project}
        tab={tab ?? "quality"}
        onTab={(t) => void navigate({ search: { tab: t }, replace: true })}
        canExport={can(projectPermissions(me.data, project.id), "data.export")}
      />
    );
  },
});
