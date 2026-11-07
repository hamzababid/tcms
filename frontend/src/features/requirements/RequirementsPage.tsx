import type { ColumnDef, ColumnFiltersState, PaginationState, SortingState } from "@tanstack/react-table";
import { Link } from "@tanstack/react-router";
import { Download, FileText, Plus, Upload } from "lucide-react";
import { useState } from "react";

import type { Project } from "@/api/queries";
import { DataTable, filterValue } from "@/components/common/DataTable";
import { EmptyState, errorMessage, Page, useToast } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/field";
import { exportEntity } from "@/features/imports/api";
import { SavedViewsMenu, useSavedViews } from "@/features/views/SavedViews";
import { formatDateTime } from "@/lib/format";

import { useRequirements, type RequirementQuery, type RequirementRef } from "./api";
import { AddRequirementsDialog, RefLink, RequirementDialog } from "./components";

const LINKED_OPTIONS = [
  { value: "true", label: "Linked to cases" },
  { value: "false", label: "Not linked" },
];

/** Requirements page (R-120; ADR-024): references to the team's requirements, with linked cases. */
export function RequirementsPage({
  project,
  canManage,
  canLink,
}: {
  project: Project;
  canManage: boolean;
  canLink: boolean;
}) {
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [archived, setArchived] = useState(false);
  const [adding, setAdding] = useState(false);
  const toast = useToast();
  const [open, setOpen] = useState<string | null>(null);
  const writable = project.status !== "archived";
  const views = useSavedViews(project.id, "requirement", { filters, setFilters, sorting, setSorting });
  const q = filterValue(filters, "reference");
  const linked = filterValue(filters, "cases");
  const query: RequirementQuery = {
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
    ...(q ? { q } : {}),
    ...(linked ? { linked: linked === "true" } : {}),
    ...(archived ? { include_archived: true } : {}),
  };
  const refs = useRequirements(project.id, query);

  const columns: ColumnDef<RequirementRef>[] = [
    {
      id: "reference",
      header: "Requirement",
      enableSorting: false,
      cell: (c) => (
        <span className="flex min-w-0 items-center gap-2">
          <RefLink r={c.row.original} />
          {c.row.original.archived ? <span className="text-xs text-ink-muted">(archived)</span> : null}
        </span>
      ),
      meta: {
        filter: { kind: "text", placeholder: "Reference or title" },
        fixed: true,
        cellClassName: "max-w-0 min-w-[260px]",
      },
    },
    {
      id: "cases",
      header: "Cases",
      enableSorting: false,
      cell: (c) => <span className="tabular">{c.row.original.case_count}</span>,
      meta: { width: "w-36", align: "right", filter: { kind: "select", options: LINKED_OPTIONS } },
    },
    {
      id: "status",
      header: "Status (all cycles)",
      enableSorting: false,
      cell: (c) =>
        c.row.original.status ? <StatusBadge kind="requirement" status={c.row.original.status} /> : null,
      meta: { width: "w-40" },
    },
    {
      id: "updated",
      header: "Updated",
      enableSorting: false,
      cell: (c) => <span className="whitespace-nowrap">{formatDateTime(c.row.original.updated_at)}</span>,
      meta: { width: "w-44" },
    },
  ];

  return (
    <Page
      title="Requirements"
      subtitle="References to the requirements and stories in your team's tool, and the cases that verify them."
      width="full"
      actions={
        <>
          {canManage && writable ? (
            <Link
              to="/p/$projectKey/import"
              params={{ projectKey: project.key }}
              search={{ entity: "requirement" }}
              className="inline-flex h-8 items-center gap-1.5 rounded-control border border-border-control bg-surface px-3 text-[13px] font-medium text-ink hover:bg-surface-muted"
            >
              <Upload aria-hidden="true" className="size-4" /> Import
            </Link>
          ) : null}
          <Button
            variant="secondary"
            onClick={() => {
              exportEntity(project.id, { entity: "requirement", format: "xlsx" }).catch((err: unknown) => {
                toast(errorMessage(err), "error");
              });
            }}
          >
            <Download aria-hidden="true" className="size-4" /> Export
          </Button>
          {canManage && writable ? (
            <Button
              onClick={() => {
                setAdding(true);
              }}
            >
              <Plus aria-hidden="true" className="size-4" /> Add requirements
            </Button>
          ) : null}
        </>
      }
    >
      <DataTable
        label="Requirements"
        columns={columns}
        data={refs.data?.items ?? []}
        loading={refs.isPending}
        error={refs.error}
        onRetry={() => void refs.refetch()}
        noun={["requirement", "requirements"]}
        getRowId={(r) => r.id}
        toolbar={
          <span className="flex items-center gap-3">
            <SavedViewsMenu views={views} canShare={canManage} />
            <Checkbox
              label="Show archived"
              checked={archived}
              onChange={(e) => {
                setArchived(e.target.checked);
              }}
            />
          </span>
        }
        {...(filters.length || archived
          ? {}
          : {
              empty: (
                <EmptyState
                  icon={<FileText className="size-5" />}
                  text="No requirements yet. Add the references of the stories you test (e.g. SPK-120) and link them to cases."
                />
              ),
            })}
        rowProps={(r) => ({
          tabIndex: 0,
          className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
          onClick: () => {
            setOpen(r.id);
          },
          onKeyDown: (e) => {
            if (e.key === "Enter" && e.target === e.currentTarget) setOpen(r.id);
          },
        })}
        server={{
          total: refs.data?.total ?? 0,
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
      {adding ? (
        <AddRequirementsDialog
          project={project}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}
      <RequirementDialog
        project={project}
        refId={open}
        releaseId={null}
        canManage={canManage && writable}
        canLink={canLink && writable}
        onClose={() => {
          setOpen(null);
        }}
      />
    </Page>
  );
}
