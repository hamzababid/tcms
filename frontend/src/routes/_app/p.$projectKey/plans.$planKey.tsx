import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { usePlans } from "@/features/planning/api";
import { PlanDetail } from "@/features/planning/PlanDetail";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/plans/$planKey")({
  component: function PlanDetailRoute() {
    const project = useRouteProject();
    const { planKey } = Route.useParams();
    const me = useMe();
    // Resolve the human key to the plan id via the list (plans are not in /resolve yet).
    const plans = usePlans(project.id, { q: planKey, page: 1, page_size: 50 });
    if (!me.data || plans.isPending)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    if (plans.isError)
      return (
        <div className="p-6">
          <ErrorState error={plans.error} />
        </div>
      );
    const plan = plans.data.items.find((p) => p.key === planKey);
    if (!plan)
      return (
        <div className="p-6">
          <ErrorState error={new Error(`Plan ${planKey} was not found.`)} />
        </div>
      );
    return (
      <PlanDetail
        project={project}
        planId={plan.id}
        canManage={can(projectPermissions(me.data, project.id), "plan.manage")}
      />
    );
  },
});
