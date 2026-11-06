import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { ReleasePage } from "@/features/reporting/ReleasesPage";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/releases/$releaseId")({
  component: function Release() {
    const project = useRouteProject();
    const { releaseId } = Route.useParams();
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    return (
      <ReleasePage
        key={releaseId}
        project={project}
        releaseId={releaseId}
        canDecide={can(projectPermissions(me.data, project.id), "release.manage")}
      />
    );
  },
});
