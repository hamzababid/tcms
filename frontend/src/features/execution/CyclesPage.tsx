import { useNavigate } from "@tanstack/react-router";
import type { ColumnDef, ColumnFiltersState, PaginationState, SortingState } from "@tanstack/react-table";
import { PlayCircle, Plus } from "lucide-react";
import { useState } from "react";

import { useEnvironments, useReleases, type Project } from "@/api/queries";
import { DataTable, filterValue, sortParam } from "@/components/common/DataTable";
import { EmptyState, Page } from "@/components/common/feedback";
import { ProgressBar } from "@/components/common/ProgressBar";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/field";
import { formatDate, formatRate } from "@/lib/format";

import { useCycles, type CycleListItem, type CycleQuery } from "./api";
import { CreateCycleDialog } from "./CreateCycleDialog";
import { CYCLE_STATUS_OPTIONS } from "./labels";

/** Test cycles list (docs/07 §5.8; US-080, US-083). */
export function CyclesPage({ project, canManage }: { project: Project; canManage: boolean }) {
  const navigate = useNavigate();
  const environments = useEnvironments(project.id);
  const releases = useReleases(project.id);
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([{ id: "key", desc: true }]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const writable = canManage && project.status !== "archived";

  const q = filterValue(filters, "name");
  const status = filterValue(filters, "status");
  const env = filterValue(filters, "environment");
  const release = filterValue(filters, "release");
  const query: CycleQuery = {
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
    sort: sortParam(sorting) ?? "-key",
    ...(q ? { q } : {}),
    ...(status ? { status } : {}),
    ...(env ? { environment_id: env } : {}),
    ...(release ? { release_id: release } : {}),
    ...(showArchived ? { include_archived: true } : {}),
  };
  const cycles = useCycles(project.id, query);

  const columns: ColumnDef<CycleListItem>[] = [
    {
      id: "key",
      header: "Key",
      accessorKey: "key",
      cell: (c) => (
        <span className="whitespace-nowrap font-mono text-[12.5px] font-medium">{c.row.original.key}</span>
      ),
      meta: { width: "w-32", fixed: true },
    },
    {
      id: "name",
      header: "Name",
      accessorKey: "name",
      cell: (c) => {
        const r = c.row.original;
        return (
          <span className="block min-w-0">
            <span className="block truncate" title={r.name}>
              {r.name}
              {r.archived ? <span className="ml-2 text-xs text-ink-muted">(archived)</span> : null}
            </span>
            {r.plan ? (
              <span className="block truncate text-xs text-ink-muted">
                from plan <span className="font-mono">{r.plan.key}</span>
              </span>
            ) : null}
          </span>
        );
      },
      meta: {
        filter: { kind: "text", placeholder: "Key or name" },
        fixed: true,
        cellClassName: "max-w-0 min-w-[200px]",
      },
    },
    {
      id: "status",
      header: "Status",
      accessorFn: (r) => r.status,
      cell: (c) => <StatusBadge kind="cycle" status={c.row.original.status} />,
      meta: { width: "w-32", filter: { kind: "select", options: CYCLE_STATUS_OPTIONS } },
    },
    {
      id: "progress",
      header: "Progress",
      enableSorting: false,
      cell: (c) => {
        const s = c.row.original.summary;
        return (
          <span className="flex min-w-[180px] flex-col gap-1">
            <ProgressBar counts={s} />
            <span className="tabular whitespace-nowrap text-xs text-ink-secondary">
              {c.row.original.runs_pending
                ? "Creating runs…"
                : s.total === 0
                  ? "No runs"
                  : `Executed ${formatRate(s.execution_progress)}`}
            </span>
          </span>
        );
      },
      meta: { width: "w-60" },
    },
    {
      id: "environment",
      header: "Environment",
      enableSorting: false,
      accessorFn: (r) => r.environment.name,
      meta: {
        width: "w-36",
        filter: {
          kind: "select",
          options: (environments.data ?? []).map((e) => ({ value: e.id, label: e.name })),
        },
      },
    },
    {
      id: "release",
      header: "Release",
      enableSorting: false,
      accessorFn: (r) => r.release?.name ?? "—",
      meta: {
        width: "w-36",
        filter: {
          kind: "select",
          options: (releases.data ?? []).map((r) => ({ value: r.id, label: r.name })),
        },
      },
    },
    {
      id: "due_date",
      header: "Due",
      accessorKey: "due_date",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{formatDate(c.row.original.due_date)}</span>
      ),
      meta: { width: "w-32" },
    },
  ];

  const open = (r: CycleListItem) =>
    void navigate({
      to: "/p/$projectKey/cycles/$cycleKey",
      params: { projectKey: project.key, cycleKey: r.key },
    });

  return (
    <Page
      title="Test cycles"
      subtitle="Run a plan or a slice of the repository against a build, assign testers and track progress."
      width="full"
      actions={
        writable ? (
          <Button
            onClick={() => {
              setCreating(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            New cycle
          </Button>
        ) : undefined
      }
    >
      <DataTable
        label="Test cycles"
        columns={columns}
        data={cycles.data?.items ?? []}
        loading={cycles.isPending}
        error={cycles.error}
        onRetry={() => void cycles.refetch()}
        noun={["cycle", "cycles"]}
        getRowId={(r) => r.id}
        initialHidden={["release"]}
        emptyText="No cycles match these filters."
        toolbar={
          <Checkbox
            label="Show archived"
            checked={showArchived}
            onChange={(e) => {
              setShowArchived(e.target.checked);
              setPagination((p) => ({ ...p, pageIndex: 0 }));
            }}
          />
        }
        {...(filters.length || showArchived
          ? {}
          : {
              empty: (
                <EmptyState
                  icon={<PlayCircle className="size-5" />}
                  text="No cycles yet. Create one from a plan or straight from the repository."
                  {...(writable
                    ? {
                        action: (
                          <Button
                            size="sm"
                            onClick={() => {
                              setCreating(true);
                            }}
                          >
                            New cycle
                          </Button>
                        ),
                      }
                    : {})}
                />
              ),
            })}
        rowProps={(r) => ({
          tabIndex: 0,
          className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
          onClick: () => {
            open(r);
          },
          onKeyDown: (e) => {
            if (e.key === "Enter" && e.target === e.currentTarget) open(r);
          },
        })}
        server={{
          total: cycles.data?.total ?? 0,
          pagination,
          onPaginationChange: setPagination,
          sorting,
          onSortingChange: setSorting,
          filters,
          onFiltersChange: (f) => {
            setFilters(f);
            setPagination((p) => ({ ...p, pageIndex: 0 }));
          },
        }}
      />
      {creating ? (
        <CreateCycleDialog
          project={project}
          onClose={() => {
            setCreating(false);
          }}
          onOpen={(key) => {
            setCreating(false);
            void navigate({
              to: "/p/$projectKey/cycles/$cycleKey",
              params: { projectKey: project.key, cycleKey: key },
            });
          }}
        />
      ) : null}
    </Page>
  );
}
