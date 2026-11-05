import { createFileRoute } from "@tanstack/react-router";

import { useMe, useResolvedKey } from "@/api/queries";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { CycleDetail } from "@/features/execution/CycleDetail";
import { projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

interface CycleSearch {
  /** Run open in the side panel (deep link, docs/07 §4.2). */
  run?: string;
}

export const Route = createFileRoute("/_app/p/$projectKey/cycles/$cycleKey")({
  validateSearch: (s: Record<string, unknown>): CycleSearch => ({
    ...(typeof s.run === "string" ? { run: s.run } : {}),
  }),
  component: function CycleDetailRoute() {
    const project = useRouteProject();
    const { cycleKey } = Route.useParams();
    const search = Route.useSearch();
    const navigate = Route.useNavigate();
    const me = useMe();
    const resolved = useResolvedKey(project.id, cycleKey);
    if (!me.data || resolved.isPending)
      return (
        <div className="p-6">
          <Skeleton rows={6} />
        </div>
      );
    if (resolved.isError || resolved.data.entity_type !== "test_cycle")
      return (
        <div className="p-6">
          <ErrorState error={resolved.error ?? new Error(`${cycleKey} is not a test cycle.`)} />
        </div>
      );
    return (
      <CycleDetail
        key={resolved.data.id}
        project={project}
        cycleId={resolved.data.id}
        me={me.data}
        perms={projectPermissions(me.data, project.id)}
        runId={search.run ?? null}
        onRun={(id) => void navigate({ search: (s) => ({ ...s, run: id ?? undefined }) })}
      />
    );
  },
});
