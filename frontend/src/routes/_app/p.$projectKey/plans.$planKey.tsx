import { createFileRoute } from "@tanstack/react-router";

import { useMe, useResolvedKey } from "@/api/queries";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { PlanDetail } from "@/features/planning/PlanDetail";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/plans/$planKey")({
  component: function PlanDetailRoute() {
    const project = useRouteProject();
    const { planKey } = Route.useParams();
    const me = useMe();
    const resolved = useResolvedKey(project.id, planKey);
    if (!me.data || resolved.isPending)
      return (
        <div className="p-6">
          <Skeleton rows={6} />
        </div>
      );
    if (resolved.isError || resolved.data.entity_type !== "test_plan")
      return (
        <div className="p-6">
          <ErrorState error={resolved.error ?? new Error(`${planKey} is not a test plan.`)} />
        </div>
      );
    const perms = projectPermissions(me.data, project.id);
    return (
      <PlanDetail
        key={resolved.data.id}
        project={project}
        planId={resolved.data.id}
        canManage={can(perms, "plan.manage")}
        canManageCycles={can(perms, "cycle.manage")}
        canLinkRequirements={can(perms, "requirement.link")}
      />
    );
  },
});
