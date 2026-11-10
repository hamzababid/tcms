import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef, ColumnFiltersState } from "@tanstack/react-table";
import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { useState } from "react";

import { Card, ErrorState, errorMessage, Page, Skeleton, useToast } from "@/components/common/feedback";
import { DataTable, filterValue, usePaging } from "@/components/common/DataTable";
import { Tag } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { formatBytes, formatCount, formatDateTime } from "@/lib/format";

import { adminKeys, retryJob, useJobs, useSystemStatus, type Job, type JobStatus } from "./api";

const CHECK_LABEL: Record<string, string> = {
  database: "Database",
  migrations: "Database schema",
  storage: "File storage",
};
const PROBLEM: JobStatus[] = ["failed", "dead"];
const QUEUE_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  dead: "Gave up",
};

function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

/** US-165 / TCMS-139 (docs/07 §5.13): version, health, the job queue and failed jobs with retry. */
export function SystemPage() {
  const status = useSystemStatus();
  const qc = useQueryClient();
  const toast = useToast();
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const statusFilter = filterValue(filters, "status") as JobStatus | undefined;
  const typeFilter = filterValue(filters, "type");
  const [pagination, setPagination] = usePaging(JSON.stringify(filters));
  const jobs = useJobs(
    statusFilter ? [statusFilter] : PROBLEM,
    pagination.pageIndex + 1,
    pagination.pageSize,
    typeFilter,
  );
  const [retrying, setRetrying] = useState<string | null>(null);

  async function retry(job: Job) {
    setRetrying(job.id);
    try {
      await retryJob(job.id);
      toast(`${job.type} queued again`);
      await qc.invalidateQueries({ queryKey: adminKeys.all });
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setRetrying(null);
    }
  }

  const columns: ColumnDef<Job>[] = [
    {
      id: "type",
      accessorKey: "type",
      header: "Job",
      cell: (c) => (
        <span className="flex items-center gap-2 font-mono text-[12.5px]">
          {c.getValue() as string}
          {c.row.original.system ? <Tag tone="neutral">installation</Tag> : null}
        </span>
      ),
      meta: { width: "w-56", fixed: true, filter: { kind: "text", placeholder: "Job type" } },
    },
    {
      id: "status",
      accessorKey: "status",
      header: "Status",
      cell: (c) => <span className="text-danger">{c.getValue() === "dead" ? "Gave up" : "Failed"}</span>,
      meta: {
        width: "w-32",
        filter: {
          kind: "select",
          options: [
            { value: "failed", label: "Failed" },
            { value: "dead", label: "Gave up" },
          ],
        },
      },
    },
    {
      id: "attempts",
      accessorFn: (j) => `${j.attempts} of ${j.max_attempts}`,
      header: "Attempts",
      meta: { width: "w-24" },
    },
    {
      id: "last_error",
      accessorKey: "last_error",
      header: "Last error",
      cell: (c) => (
        <span
          className="line-clamp-2 break-all font-mono text-[12px] text-ink-secondary"
          title={(c.getValue() as string | null) ?? ""}
        >
          {(c.getValue() as string | null) ?? "—"}
        </span>
      ),
    },
    {
      id: "finished_at",
      accessorKey: "finished_at",
      header: "Stopped",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {formatDateTime(c.getValue() as string | null)}
        </span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      cell: (c) => (
        <Button
          variant="secondary"
          size="xs"
          disabled={retrying === c.row.original.id}
          aria-label={`Retry ${c.row.original.type}`}
          onClick={() => void retry(c.row.original)}
        >
          <RotateCcw aria-hidden="true" className="size-3.5" />
          Retry
        </Button>
      ),
      meta: { align: "right", width: "w-24", fixed: true, label: "Actions" },
    },
  ];

  if (status.isError) return <ErrorState error={status.error} />;
  if (status.isPending) return <Skeleton />;
  const s = status.data;
  const counts = s.jobs.counts;
  return (
    <Page
      title="System"
      subtitle={`Checked ${formatDateTime(s.checked_at)}; refreshes every 30 seconds.`}
      width="full"
    >
      <div className="flex flex-col gap-5">
        <div className="grid gap-5 lg:grid-cols-3">
          <Card title="Version">
            <dl className="grid grid-cols-[120px_1fr] gap-y-1.5 text-[13px]">
              <dt className="text-ink-secondary">Application</dt>
              <dd className="font-mono text-[12.5px]">{s.version}</dd>
              <dt className="text-ink-secondary">Environment</dt>
              <dd>{s.environment}</dd>
              <dt className="text-ink-secondary">Schema</dt>
              <dd className="font-mono text-[12.5px]">{s.migration_current ?? "unknown"}</dd>
              <dt className="text-ink-secondary">Audit kept</dt>
              <dd>{s.audit_retention_years} years</dd>
            </dl>
          </Card>
          <Card title="Health">
            <ul aria-label="Health checks" className="flex flex-col gap-2 text-[13px]">
              {Object.entries(s.checks).map(([name, c]) => (
                <li key={name} className="flex items-start gap-2">
                  {c.ok ? (
                    <CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 text-success" />
                  ) : (
                    <XCircle aria-hidden="true" className="mt-0.5 size-4 text-danger" />
                  )}
                  <span>
                    {CHECK_LABEL[name] ?? name}: {c.ok ? "OK" : "Problem"}
                    {c.detail ? (
                      <span className="block text-[12px] text-ink-secondary">{c.detail}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Files">
            <p className="text-[13px] text-ink-secondary">
              <span className="text-[20px] font-semibold text-ink">{formatBytes(s.attachments.bytes)}</span>{" "}
              in {formatCount(s.attachments.files)} attachments
            </p>
          </Card>
        </div>
        <Card
          title="Background jobs"
          description="Emails, imports, exports, snapshots and clean-up run in the background."
        >
          <dl aria-label="Job queue" className="grid grid-cols-2 gap-4 text-[13px] md:grid-cols-5">
            {(["queued", "running", "succeeded", "failed", "dead"] as const).map((k) => (
              <div key={k}>
                <dt className="text-ink-secondary">{QUEUE_LABEL[k]}</dt>
                <dd
                  className={`text-[20px] font-semibold tabular ${(k === "failed" || k === "dead") && (counts[k] ?? 0) > 0 ? "text-danger" : "text-ink"}`}
                >
                  {formatCount(counts[k] ?? 0)}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[13px] text-ink-secondary">
            Oldest waiting job: {s.jobs.oldest_due_at ? `due ${ago(s.jobs.oldest_due_at)}` : "none"} · Last
            job finished {ago(s.jobs.last_succeeded_at)}. Succeeded jobs are kept 14 days, failed ones 90
            days.
          </p>
        </Card>
        <DataTable
          label="Failed jobs"
          columns={columns}
          data={jobs.data?.items ?? []}
          getRowId={(j) => j.id}
          loading={jobs.isPending}
          error={jobs.error}
          onRetry={() => void jobs.refetch()}
          noun={["job", "jobs"]}
          emptyText={filters.length ? "No jobs match these filters." : "No failed jobs."}
          toolbar={<h2 className="text-[15px] font-semibold text-ink">Failed jobs</h2>}
          server={{
            total: jobs.data?.total ?? 0,
            pagination,
            onPaginationChange: setPagination,
            filters,
            onFiltersChange: setFilters,
          }}
        />
      </div>
    </Page>
  );
}
