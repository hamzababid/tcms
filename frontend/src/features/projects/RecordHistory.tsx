import { useMembers, useRecordHistory } from "@/api/queries";

import { AuditTable, useAuditState } from "./AuditTable";

/** History tab of a plan or cycle (US-161): the record's audit events, newest first, with the same
 * filters as the case history and the activity feed. */
export function RecordHistory({
  projectId,
  entityType,
  entityId,
}: {
  projectId: string;
  entityType: string;
  entityId: string;
}) {
  const state = useAuditState();
  // The record fixes the type; the rest of the audit filters apply.
  const { page, page_size, actor_id, action, occurred_at__gte, occurred_at__lte, q } = state.query;
  const history = useRecordHistory(entityType, entityId, {
    page,
    page_size,
    ...(actor_id ? { actor_id } : {}),
    ...(action ? { action } : {}),
    ...(occurred_at__gte ? { occurred_at__gte } : {}),
    ...(occurred_at__lte ? { occurred_at__lte } : {}),
    ...(q ? { q } : {}),
  });
  const members = useMembers(projectId);
  return (
    <AuditTable
      label="History"
      rows={history.data?.items ?? []}
      total={history.data?.total ?? 0}
      loading={history.isPending}
      error={history.error}
      onRetry={() => void history.refetch()}
      members={members.data ?? []}
      state={state}
      showType={false}
    />
  );
}
