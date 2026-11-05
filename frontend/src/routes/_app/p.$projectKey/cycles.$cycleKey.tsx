import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { useCycles } from "@/features/execution/api";
import { CycleDetail } from "@/features/execution/CycleDetail";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/cycles/$cycleKey")({
  component: function CycleDetailRoute() {
    const project = useRouteProject();
    const { cycleKey } = Route.useParams();
    const me = useMe();
    const cycles = useCycles(project.id, { q: cycleKey, page: 1, page_size: 50 });
    if (!me.data || cycles.isPending)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    if (cycles.isError)
      return (
        <div className="p-6">
          <ErrorState error={cycles.error} />
        </div>
      );
    const cycle = cycles.data.items.find((x) => x.key === cycleKey);
    if (!cycle)
      return (
        <div className="p-6">
          <ErrorState error={new Error(`Cycle ${cycleKey} was not found.`)} />
        </div>
      );
    const perms = projectPermissions(me.data, project.id);
    return (
      <CycleDetail
        project={project}
        cycleId={cycle.id}
        canManage={can(perms, "cycle.manage")}
        canReopen={can(perms, "cycle.reopen")}
        canExecute={can(perms, "run.execute")}
      />
    );
  },
});
