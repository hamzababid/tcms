import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { CyclesPage } from "@/features/execution/CyclesPage";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/cycles")({
  component: function Cycles() {
    const project = useRouteProject();
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    return (
      <CyclesPage
        project={project}
        canManage={can(projectPermissions(me.data, project.id), "cycle.manage")}
      />
    );
  },
});
