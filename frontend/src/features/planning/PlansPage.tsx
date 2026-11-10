import { useNavigate } from "@tanstack/react-router";
import type { ColumnDef, ColumnFiltersState, SortingState } from "@tanstack/react-table";
import { ClipboardList, Plus } from "lucide-react";
import { useState } from "react";

import { useMembers, useReleases, type Project } from "@/api/queries";
import { DataTable, filterValue, sortParam, usePaging } from "@/components/common/DataTable";
import { EmptyState, Page } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/field";
import { SavedViewsMenu, useSavedViews } from "@/features/views/SavedViews";
import { formatDate } from "@/lib/format";

import { usePlans, type PlanListItem, type PlanQuery } from "./api";
import { PlanForm } from "./PlanForm";
import { PLAN_STATUS_OPTIONS, PLAN_TYPE_LABEL, PLAN_TYPES } from "./labels";

/** Test plans list (docs/07 §5.7; US-070). */
export function PlansPage({ project, canManage }: { project: Project; canManage: boolean }) {
  const navigate = useNavigate();
  const members = useMembers(project.id);
  const releases = useReleases(project.id);
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([{ id: "key", desc: true }]);
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const writable = canManage && project.status !== "archived";
  const views = useSavedViews(project.id, "test_plan", { filters, setFilters, sorting, setSorting });

  const q = filterValue(filters, "name");
  const status = filterValue(filters, "status");
  const type = filterValue(filters, "type");
  const owner = filterValue(filters, "owner");
  const release = filterValue(filters, "release");
  const where = {
    sort: sortParam(sorting) ?? "-key",
    ...(q ? { q } : {}),
    ...(status ? { status } : {}),
    ...(type ? { type } : {}),
    ...(owner ? { owner_id: owner } : {}),
    ...(release ? { release_id: release } : {}),
    ...(showArchived ? { include_archived: true } : {}),
  };
  const [pagination, setPagination] = usePaging(JSON.stringify(where));
  const query: PlanQuery = { ...where, page: pagination.pageIndex + 1, page_size: pagination.pageSize };
  const plans = usePlans(project.id, query);
  const releaseName = (id: string | null) =>
    id ? (releases.data?.find((r) => r.id === id)?.name ?? "—") : "—";

  const columns: ColumnDef<PlanListItem>[] = [
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
      cell: (c) => (
        <span className="block truncate" title={c.row.original.name}>
          {c.row.original.name}
          {c.row.original.archived ? <span className="ml-2 text-xs text-ink-muted">(archived)</span> : null}
        </span>
      ),
      meta: {
        filter: { kind: "text", placeholder: "Key or name" },
        fixed: true,
        cellClassName: "max-w-0 min-w-[200px]",
      },
    },
    {
      id: "type",
      header: "Type",
      enableSorting: false,
      accessorFn: (r) => r.type,
      cell: (c) => <span className="whitespace-nowrap">{PLAN_TYPE_LABEL[c.row.original.type]}</span>,
      meta: { width: "w-40", filter: { kind: "select", options: PLAN_TYPES } },
    },
    {
      id: "status",
      header: "Status",
      accessorFn: (r) => r.status,
      cell: (c) => <StatusBadge kind="plan" status={c.row.original.status} />,
      meta: { width: "w-36", filter: { kind: "select", options: PLAN_STATUS_OPTIONS } },
    },
    {
      id: "release",
      header: "Release",
      enableSorting: false,
      accessorFn: (r) => releaseName(r.release_id),
      meta: {
        width: "w-36",
        filter: {
          kind: "select",
          options: (releases.data ?? []).map((r) => ({ value: r.id, label: r.name })),
        },
      },
    },
    {
      id: "owner",
      header: "Owner",
      enableSorting: false,
      accessorFn: (r) => r.owner?.display_name ?? "—",
      cell: (c) => <span className="whitespace-nowrap">{c.row.original.owner?.display_name ?? "—"}</span>,
      meta: {
        width: "w-40",
        filter: {
          kind: "select",
          options: (members.data ?? []).map((m) => ({ value: m.user.id, label: m.user.display_name })),
        },
      },
    },
    {
      id: "dates",
      header: "Dates",
      enableSorting: false,
      cell: (c) => {
        const r = c.row.original;
        return (
          <span className="whitespace-nowrap text-ink-secondary">
            {r.start_date || r.end_date ? `${formatDate(r.start_date)} → ${formatDate(r.end_date)}` : "—"}
          </span>
        );
      },
      meta: { width: "w-56" },
    },
    {
      id: "case_count",
      header: "Cases",
      enableSorting: false,
      accessorFn: (r) => r.case_count,
      cell: (c) => <span className="tabular">{c.row.original.case_count.toLocaleString()}</span>,
      meta: { width: "w-20", align: "right" },
    },
  ];

  const open = (r: PlanListItem) =>
    void navigate({
      to: "/p/$projectKey/plans/$planKey",
      params: { projectKey: project.key, planKey: r.key },
    });

  return (
    <Page
      title="Test plans"
      subtitle="Group cases into a plan for a release or test effort, then run cycles from it."
      width="full"
      actions={
        writable ? (
          <Button
            onClick={() => {
              setCreating(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            New plan
          </Button>
        ) : undefined
      }
    >
      <DataTable
        label="Test plans"
        columns={columns}
        data={plans.data?.items ?? []}
        loading={plans.isPending}
        error={plans.error}
        onRetry={() => void plans.refetch()}
        noun={["plan", "plans"]}
        getRowId={(r) => r.id}
        initialHidden={["release", "dates"]}
        emptyText="No plans match these filters."
        toolbar={
          <span className="flex items-center gap-3">
            <SavedViewsMenu views={views} canShare={canManage} />
            <Checkbox
              label="Show archived"
              checked={showArchived}
              onChange={(e) => {
                setShowArchived(e.target.checked);
              }}
            />
          </span>
        }
        {...(filters.length || showArchived
          ? {}
          : {
              empty: (
                <EmptyState
                  icon={<ClipboardList className="size-5" />}
                  text="No test plans yet. A plan groups the cases, scope and exit criteria of a test effort."
                  {...(writable
                    ? {
                        action: (
                          <Button
                            size="sm"
                            onClick={() => {
                              setCreating(true);
                            }}
                          >
                            New plan
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
          total: plans.data?.total ?? 0,
          pagination,
          onPaginationChange: setPagination,
          sorting,
          onSortingChange: setSorting,
          filters,
          onFiltersChange: setFilters,
        }}
      />
      {creating ? (
        <PlanForm
          project={project}
          plan={null}
          onClose={() => {
            setCreating(false);
          }}
          onSaved={(plan) => {
            setCreating(false);
            void navigate({
              to: "/p/$projectKey/plans/$planKey",
              params: { projectKey: project.key, planKey: plan.key },
            });
          }}
        />
      ) : null}
    </Page>
  );
}
