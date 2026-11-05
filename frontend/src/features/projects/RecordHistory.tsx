import type { ColumnDef, PaginationState } from "@tanstack/react-table";
import { useState } from "react";

import { useRecordHistory, type Activity } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { formatDateTime } from "@/lib/format";

const columns: ColumnDef<Activity>[] = [
  {
    id: "occurred_at",
    accessorKey: "occurred_at",
    header: "When",
    enableSorting: false,
    cell: (c) => (
      <span className="whitespace-nowrap text-ink-secondary">
        {formatDateTime(c.row.original.occurred_at)}
      </span>
    ),
    meta: { width: "w-44", fixed: true },
  },
  {
    id: "actor",
    accessorFn: (r) => r.actor_display ?? "System",
    header: "By",
    enableSorting: false,
    meta: { width: "w-44" },
  },
  {
    id: "summary",
    accessorFn: (r) => r.summary ?? r.action,
    header: "Event",
    enableSorting: false,
    meta: { fixed: true },
  },
];

/** History tab of a plan or cycle (US-161): the record's audit events, newest first. */
export function RecordHistory({ entityType, entityId }: { entityType: string; entityId: string }) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const history = useRecordHistory(entityType, entityId, {
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  });
  return (
    <DataTable
      label="History"
      columns={columns}
      data={history.data?.items ?? []}
      getRowId={(r) => r.id}
      loading={history.isPending}
      error={history.error}
      onRetry={() => void history.refetch()}
      noun={["event", "events"]}
      emptyText="No history yet."
      hideFilters
      server={{
        total: history.data?.total ?? 0,
        pagination,
        onPaginationChange: setPagination,
        sorting: [],
        onSortingChange: () => undefined,
        filters: [],
        onFiltersChange: () => undefined,
      }}
    />
  );
}
