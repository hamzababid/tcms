/** Organization dashboard (docs/07 §5.2; FR-WS-008, US-146): one row per project. Org Admins see every
 * project; others see the projects they belong to. "Open crit/high" became failed runs (ADR-023). */
import { Link } from "@tanstack/react-router";
import type { ColumnDef } from "@tanstack/react-table";

import type { components } from "@/api/schema";
import { DataTable } from "@/components/common/DataTable";
import { EmptyState, ErrorState, Page } from "@/components/common/feedback";
import { ProgressBar } from "@/components/common/ProgressBar";
import { formatCount, formatDateTime, formatRate } from "@/lib/format";

import { useOrgDashboard } from "./api";

type Row = components["schemas"]["OrgProjectRow"];

const columns: ColumnDef<Row>[] = [
  {
    id: "project",
    header: "Project",
    accessorFn: (p) => `${p.project.key} ${p.project.title}`,
    cell: (c) => {
      const p = c.row.original;
      return (
        <span>
          <Link
            to="/p/$projectKey"
            params={{ projectKey: p.project.key }}
            className="font-medium text-accent-ink hover:underline"
          >
            {p.project.key}
          </Link>{" "}
          <span className="text-ink-secondary">{p.project.title}</span>
        </span>
      );
    },
    meta: { fixed: true, filter: { kind: "text", placeholder: "Key or name" } },
  },
  {
    id: "active_cycles",
    header: "Active cycles",
    accessorKey: "active_cycles",
    cell: (c) => <span className="tabular">{formatCount(c.row.original.active_cycles)}</span>,
    meta: { align: "right", width: "w-32" },
  },
  {
    id: "progress",
    header: "Execution progress",
    accessorFn: (p) => p.summary.execution_progress.value ?? -1,
    cell: (c) => (
      <div>
        <ProgressBar counts={c.row.original.summary} />
        <div className="tabular mt-1 text-xs text-ink-secondary">
          {formatRate(c.row.original.summary.execution_progress)}
        </div>
      </div>
    ),
    meta: { width: "w-64" },
  },
  {
    id: "pass_rate",
    header: "Pass rate",
    accessorFn: (p) => p.summary.pass_rate.value ?? -1,
    cell: (c) => <span className="tabular">{formatRate(c.row.original.summary.pass_rate)}</span>,
    meta: { width: "w-28" },
  },
  {
    id: "failed",
    header: "Failed runs",
    accessorKey: "failed",
    cell: (c) => <span className="tabular">{formatCount(c.row.original.failed)}</span>,
    meta: { align: "right", width: "w-28" },
  },
  {
    id: "bugs",
    header: "Bugs on failing runs",
    accessorKey: "bugs_on_failing_runs",
    cell: (c) => <span className="tabular">{formatCount(c.row.original.bugs_on_failing_runs)}</span>,
    meta: { align: "right", width: "w-40" },
  },
  {
    id: "last_activity",
    header: "Last activity",
    accessorFn: (p) => p.last_activity ?? "",
    cell: (c) => (
      <span className="whitespace-nowrap text-ink-secondary">
        {formatDateTime(c.row.original.last_activity)}
      </span>
    ),
    meta: { width: "w-44", filter: { kind: "daterange" } },
  },
];

export function OrgDashboardPage() {
  const d = useOrgDashboard();
  return (
    <Page
      title="Organization dashboard"
      subtitle="Planned and active cycles of every project you can see."
      width="full"
    >
      {d.isError ? (
        <ErrorState error={d.error} onRetry={() => void d.refetch()} />
      ) : (
        <DataTable
          label="Projects"
          columns={columns}
          data={d.data?.projects ?? []}
          getRowId={(p) => p.project.id}
          loading={d.isPending}
          noun={["project", "projects"]}
          emptyText="No projects match these filters."
          empty={<EmptyState text="You are not a member of any active project." />}
          initialSorting={[{ id: "last_activity", desc: true }]}
        />
      )}
    </Page>
  );
}
