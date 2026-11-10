import { Link } from "@tanstack/react-router";
import type { ColumnDef, ColumnFiltersState, SortingState } from "@tanstack/react-table";
import { Bug, Download, ExternalLink, RotateCcw } from "lucide-react";
import { useState } from "react";

import type { Project } from "@/api/queries";
import { DataTable, filterValue, usePaging } from "@/components/common/DataTable";
import { EmptyState, errorMessage, Page, useToast } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/field";
import { exportReport } from "@/features/reporting/api";
import { SavedViewsMenu, useSavedViews } from "@/features/views/SavedViews";
import { formatDateTime } from "@/lib/format";

import { safeUrl, useBugs, useReferenceLinks, type BugQuery, type BugSummary } from "./api";
import { BugChip, RetestDialog, trackerOf, whereText } from "./components";

/** Bugs list (docs/02 §8.4; ADR-023): one row per bug reference linked in the project. */
export function BugsPage({ project, canRetest }: { project: Project; canRetest: boolean }) {
  const toast = useToast();
  const tracker = trackerOf(project);
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const views = useSavedViews(project.id, "bug", { filters, setFilters, sorting, setSorting });
  const [failing, setFailing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [retest, setRetest] = useState<string | null>(null);
  const q = filterValue(filters, "reference");
  const where = { ...(q ? { q } : {}), ...(failing ? { failing: true } : {}) };
  const [pagination, setPagination] = usePaging(JSON.stringify(where));
  const query: BugQuery = { ...where, page: pagination.pageIndex + 1, page_size: pagination.pageSize };
  const bugs = useBugs(project.id, query);
  const writable = canRetest && project.status !== "archived";

  const columns: ColumnDef<BugSummary>[] = [
    {
      id: "reference",
      header: "Bug",
      enableSorting: false,
      cell: (c) => {
        const b = c.row.original;
        const href = safeUrl(b.url);
        return (
          <span className="flex min-w-0 items-center gap-2">
            <Bug aria-hidden="true" className="size-3.5 shrink-0 text-[var(--status-fail-fg)]" />
            <span className="font-mono text-[12.5px] font-medium">{b.reference}</span>
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-link"
                aria-label={`Open ${b.reference} in ${tracker.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                }}
              >
                <ExternalLink aria-hidden="true" className="size-3.5" />
              </a>
            ) : null}
            {b.title ? (
              <span className="truncate text-ink-secondary" title={b.title}>
                {b.title}
              </span>
            ) : null}
          </span>
        );
      },
      meta: {
        filter: { kind: "text", placeholder: "Reference or title" },
        fixed: true,
        cellClassName: "max-w-0 min-w-[240px]",
      },
    },
    {
      id: "cases",
      header: "Cases",
      enableSorting: false,
      cell: (c) => <span className="tabular">{c.row.original.cases}</span>,
      meta: { width: "w-20", align: "right" },
    },
    {
      id: "runs",
      header: "Runs",
      enableSorting: false,
      cell: (c) => <span className="tabular">{c.row.original.runs}</span>,
      meta: { width: "w-20", align: "right" },
    },
    {
      id: "failing",
      header: "Failing now",
      enableSorting: false,
      cell: (c) => {
        const b = c.row.original;
        return (
          <span className="flex items-center gap-1.5">
            {b.failing_runs ? <StatusBadge kind="execution" status="failed" /> : null}
            <span className="tabular">{b.failing_runs}</span>
            {b.needs_retest_runs ? <StatusBadge kind="execution" status="needs_retest" compact /> : null}
          </span>
        );
      },
      meta: { width: "w-40" },
    },
    {
      id: "cycles",
      header: "Cycles",
      enableSorting: false,
      cell: (c) => <span className="text-ink-secondary">{c.row.original.cycle_keys.join(", ") || "—"}</span>,
      meta: { width: "w-48" },
    },
    {
      id: "last",
      header: "Last linked",
      enableSorting: false,
      cell: (c) => <span className="whitespace-nowrap">{formatDateTime(c.row.original.last_linked_at)}</span>,
      meta: { width: "w-44" },
    },
    ...(writable
      ? ([
          {
            id: "actions",
            header: "",
            enableSorting: false,
            cell: (c) =>
              c.row.original.runs ? (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    setRetest(c.row.original.reference);
                  }}
                >
                  <RotateCcw aria-hidden="true" className="size-3.5" /> Ready for retest
                </Button>
              ) : null,
            meta: { width: "w-40", label: "Actions" },
          },
        ] satisfies ColumnDef<BugSummary>[])
      : []),
  ];

  return (
    <Page
      title="Bugs"
      subtitle={`Bugs linked from test runs and cases. They are reported and fixed in ${tracker.name}.`}
      width="full"
      actions={
        <Button
          variant="secondary"
          onClick={() => {
            exportReport(project.id, "bug-links", "xlsx", {})
              .then((out) => {
                if ("transferId" in out)
                  toast(`${out.rows.toLocaleString()} rows: the file is being prepared`);
              })
              .catch((err: unknown) => {
                toast(errorMessage(err), "error");
              });
          }}
        >
          <Download aria-hidden="true" className="size-4" /> Export
        </Button>
      }
    >
      <DataTable
        label="Bugs"
        columns={columns}
        data={bugs.data?.items ?? []}
        loading={bugs.isPending}
        error={bugs.error}
        onRetry={() => void bugs.refetch()}
        noun={["bug", "bugs"]}
        getRowId={(b) => b.reference}
        toolbar={
          <span className="flex items-center gap-3">
            <SavedViewsMenu views={views} canShare={canRetest} />
            <Checkbox
              label="Linked to failing runs"
              checked={failing}
              onChange={(e) => {
                setFailing(e.target.checked);
              }}
            />
          </span>
        }
        {...(filters.length || failing
          ? {}
          : {
              empty: (
                <EmptyState
                  icon={<Bug className="size-5" />}
                  text="No bugs are linked yet. In the runner, press D on a failed step to link the bug you logged."
                />
              ),
            })}
        rowProps={(b) => ({
          tabIndex: 0,
          className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
          onClick: () => {
            setOpen(b.reference);
          },
          onKeyDown: (e) => {
            if (e.key === "Enter" && e.target === e.currentTarget) setOpen(b.reference);
          },
        })}
        server={{
          total: bugs.data?.total ?? 0,
          pagination,
          onPaginationChange: setPagination,
          filters,
          onFiltersChange: setFilters,
        }}
      />
      <ReferenceDialog
        project={project}
        reference={open}
        canRetest={writable}
        onClose={() => {
          setOpen(null);
        }}
      />
      <RetestDialog
        project={project}
        reference={retest}
        onClose={() => {
          setRetest(null);
        }}
      />
    </Page>
  );
}

/** Every link of one reference: cycle, case, attempt and step (docs/02 §8.4). */
function ReferenceDialog({
  project,
  reference,
  canRetest,
  onClose,
}: {
  project: Project;
  reference: string | null;
  canRetest: boolean;
  onClose: () => void;
}) {
  const tracker = trackerOf(project);
  const links = useReferenceLinks(project.id, reference);
  return (
    <Dialog
      open={reference !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={reference ?? ""}
      description={`Where this bug is linked. It is worked in ${tracker.name}.`}
      wide
    >
      <ul className="grid gap-2 text-[13px]">
        {(links.data ?? []).map((l) => (
          <li
            key={l.id}
            className="flex flex-wrap items-center gap-2 border-t border-border pt-2 first:border-t-0"
          >
            <BugChip link={l} project={project} tracker={tracker} canRetest={canRetest} compact />
            <Link
              to="/p/$projectKey/cases/$caseKey"
              params={{ projectKey: project.key, caseKey: l.test_case.key }}
              className="font-mono text-link hover:underline"
            >
              {l.test_case.key}
            </Link>
            <span className="min-w-0 flex-1 truncate">{l.test_case.title}</span>
            <span className="text-ink-secondary">{whereText(l)}</span>
            {l.run_status ? <StatusBadge kind="execution" status={l.run_status} /> : null}
            {l.cycle && l.run_id ? (
              <Link
                to="/p/$projectKey/cycles/$cycleKey/run/$runId"
                params={{ projectKey: project.key, cycleKey: l.cycle.key, runId: l.run_id }}
                className="text-link hover:underline"
              >
                Open run
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </Dialog>
  );
}
