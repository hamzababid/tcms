import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { RequirementsPage } from "@/features/requirements/RequirementsPage";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/requirements")({
  component: function Requirements() {
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
      <RequirementsPage
        project={project}
        canManage={can(perms, "requirement.manage")}
        canLink={can(perms, "requirement.link")}
      />
    );
  },
});
