import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { BugsPage } from "@/features/bugs/BugsPage";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/bugs")({
  component: function Bugs() {
    const project = useRouteProject();
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    return (
      <BugsPage project={project} canRetest={can(projectPermissions(me.data, project.id), "cycle.manage")} />
    );
  },
});
