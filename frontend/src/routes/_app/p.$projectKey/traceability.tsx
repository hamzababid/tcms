import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { TraceabilityPage } from "@/features/requirements/TraceabilityPage";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/traceability")({
  component: function Traceability() {
    const project = useRouteProject();
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    const perms = projectPermissions(me.data, project.id);
    return (
      <TraceabilityPage
        project={project}
        canManage={can(perms, "requirement.manage")}
        canLink={can(perms, "requirement.link")}
      />
    );
  },
});
