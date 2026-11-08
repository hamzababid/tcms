import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { EmptyState, Skeleton } from "@/components/common/feedback";
import { ProjectAuditLogPage } from "@/features/admin/AuditLog";
import { can, projectPermissions } from "@/lib/permissions";
import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/audit")({
  component: function ProjectAudit() {
    const project = useRouteProject();
    const me = useMe();
    if (me.isPending) return <Skeleton />;
    if (!can(projectPermissions(me.data, project.id), "project.audit.view"))
      return (
        <div className="p-6">
          <EmptyState text="The audit log is for QA Managers and organization administrators." />
        </div>
      );
    return <ProjectAuditLogPage project={project} />;
  },
});
