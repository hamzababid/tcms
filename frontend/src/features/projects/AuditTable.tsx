import type { ColumnDef, ColumnFiltersState, PaginationState, SortingState } from "@tanstack/react-table";
import { useState } from "react";

import type { Activity, AuditQuery, ProjectMember } from "@/api/queries";
import { DataTable, filterValue, rangeValue, type FilterOption } from "@/components/common/DataTable";
import { formatDateTime } from "@/lib/format";

/** Record types that appear in the project feed (labels for the Type filter). */
export const ENTITY_TYPES: FilterOption[] = [
  { value: "project", label: "Project" },
  { value: "membership", label: "Member" },
  { value: "environment", label: "Environment" },
  { value: "release", label: "Release" },
  { value: "folder", label: "Folder" },
  { value: "test_case", label: "Test case" },
  { value: "tag", label: "Tag" },
  { value: "comment", label: "Comment" },
  { value: "attachment", label: "Attachment" },
];

const typeLabel = (v: string) => ENTITY_TYPES.find((t) => t.value === v)?.label ?? v;

/** Server-side audit list state → API query (docs/06 §4.12 filters plus q). */
export function useAuditState(defaultPageSize = 25) {
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: defaultPageSize });
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [from, to] = rangeValue(filters, "occurred_at");
  const actor = filterValue(filters, "actor");
  const type = filterValue(filters, "entity_type");
  const q = filterValue(filters, "summary");
  const query: AuditQuery = {
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
    ...(actor ? { actor_id: actor } : {}),
    ...(type ? { entity_type: type } : {}),
    ...(q ? { q } : {}),
    ...(from ? { occurred_at__gte: from } : {}),
    ...(to ? { occurred_at__lte: to } : {}),
  };
  return { query, pagination, setPagination, filters, setFilters, sorting, setSorting };
}

export function AuditTable({
  label,
  rows,
  total,
  loading,
  error,
  onRetry,
  members,
  state,
  showType = true,
  bare = false,
  dense = false,
}: {
  label: string;
  rows: Activity[];
  total: number;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  members: ProjectMember[];
  state: ReturnType<typeof useAuditState>;
  showType?: boolean;
  bare?: boolean;
  dense?: boolean;
}) {
  const columns: ColumnDef<Activity>[] = [
    {
      id: "occurred_at",
      accessorKey: "occurred_at",
      header: "When",
      enableSorting: false,
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{formatDateTime(c.getValue() as string)}</span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44", fixed: true },
    },
    {
      id: "actor",
      accessorFn: (r) => r.actor_display ?? "System",
      header: "By",
      enableSorting: false,
      cell: (c) => <span className="whitespace-nowrap">{c.getValue() as string}</span>,
      meta: {
        filter: {
          kind: "select",
          options: members.map((m) => ({ value: m.user.id, label: m.user.display_name })),
        },
        width: "w-44",
      },
    },
    {
      id: "summary",
      accessorFn: (r) => r.summary ?? r.action,
      header: "Event",
      enableSorting: false,
      meta: { filter: { kind: "text", placeholder: "Search events" }, fixed: true },
    },
    ...(showType
      ? [
          {
            id: "entity_type",
            accessorKey: "entity_type",
            header: "Type",
            enableSorting: false,
            cell: (c) => (
              <span className="whitespace-nowrap text-ink-secondary">
                {typeLabel(c.getValue() as string)}
              </span>
            ),
            meta: { filter: { kind: "select", options: ENTITY_TYPES }, width: "w-40" },
          } satisfies ColumnDef<Activity>,
        ]
      : []),
    {
      id: "entity_key",
      accessorKey: "entity_key",
      header: "Record",
      enableSorting: false,
      cell: (c) => (
        <span className="whitespace-nowrap font-mono text-[12.5px] font-medium">
          {(c.getValue() as string | null) ?? "—"}
        </span>
      ),
      meta: { width: "w-40" },
    },
  ];
  return (
    <DataTable
      label={label}
      columns={columns}
      data={rows}
      getRowId={(r) => r.id}
      loading={loading}
      error={error}
      onRetry={onRetry}
      noun={["event", "events"]}
      emptyText="No activity matches these filters."
      bare={bare}
      dense={dense}
      {...(dense ? { initialHidden: ["entity_key", "actor"] } : {})}
      server={{
        total,
        pagination: state.pagination,
        onPaginationChange: state.setPagination,
        sorting: state.sorting,
        onSortingChange: state.setSorting,
        filters: state.filters,
        onFiltersChange: state.setFilters,
      }}
    />
  );
}
