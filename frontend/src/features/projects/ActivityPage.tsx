import { useActivity, useMembers, type Project } from "@/api/queries";
import { Page } from "@/components/common/feedback";

import { AuditTable, useAuditState } from "./AuditTable";

/** US-028 / FR-WS-007: audit events rendered as sentences, filterable per column. */
export function ActivityPage({ project }: { project: Project }) {
  const state = useAuditState();
  const activity = useActivity(project.id, state.query);
  const members = useMembers(project.id);
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
