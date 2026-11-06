import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { RunnerPage } from "@/features/execution/runner/RunnerPage";
import { projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

/** Runner (docs/04 §11.1 `/p/:projectKey/cycles/:cycleKey/run/:runId`, docs/07 §5.9). */
export const Route = createFileRoute("/_app/p/$projectKey/cycles/$cycleKey_/run/$runId")({
  component: function Runner() {
    const project = useRouteProject();
    const { cycleKey, runId } = Route.useParams();
    const navigate = Route.useNavigate();
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton rows={8} />
        </div>
      );
    return (
      <RunnerPage
        project={project}
        cycleKey={cycleKey}
        runId={runId}
        me={me.data}
        perms={projectPermissions(me.data, project.id)}
        onRun={(id) =>
          void navigate({
            to: "/p/$projectKey/cycles/$cycleKey/run/$runId",
            params: { projectKey: project.key, cycleKey, runId: id },
          })
        }
      />
    );
  },
});
