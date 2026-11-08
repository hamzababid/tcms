import { Link } from "@tanstack/react-router";

import { useActivity, useMe, useMembers, type Project } from "@/api/queries";
import { Page } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { can, projectPermissions } from "@/lib/permissions";

import { AuditTable, useAuditState } from "./AuditTable";

/** US-028 / FR-WS-007: audit events rendered as sentences, filterable per column. */
export function ActivityPage({ project }: { project: Project }) {
  const state = useAuditState();
  const activity = useActivity(project.id, state.query);
  const members = useMembers(project.id);
  const me = useMe();
  const canAudit = can(projectPermissions(me.data, project.id), "project.audit.view");
  return (
    <Page
      title="Activity"
      eyebrow={project.name}
      subtitle={
        project.status === "archived"
          ? "This project is archived and read-only."
          : "Everything that changed in this project, newest first."
      }
      width="full"
      actions={
        canAudit ? (
          <Button variant="secondary" size="sm" asChild>
            <Link to="/p/$projectKey/audit" params={{ projectKey: project.key }}>
              Audit log
            </Link>
          </Button>
        ) : undefined
      }
    >
      <AuditTable
        label="Project activity"
        rows={activity.data?.items ?? []}
        total={activity.data?.total ?? 0}
        loading={activity.isPending}
        error={activity.error}
        onRetry={() => void activity.refetch()}
        members={members.data ?? []}
        state={state}
      />
    </Page>
  );
}
