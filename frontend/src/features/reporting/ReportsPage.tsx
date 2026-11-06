/** Reports: quality dashboard and the six standard reports with CSV/XLSX export (docs/07 §5.12; FR-RPT-003…005). */
import { Download, RefreshCw } from "lucide-react";
import { useState } from "react";

import { useReleases, type Project } from "@/api/queries";
import { Card, errorMessage, ErrorState, Page, Skeleton, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { formatCount, formatDate, formatDateTime, formatRate } from "@/lib/format";

import {
  exportReport,
  refreshMetrics,
  useInvalidateReporting,
  useQualityDashboard,
  useReport,
  useTransfer,
  type ReportPage,
} from "./api";
import { ChartCard, CountBars, DailyStatus, ExecutionTrend } from "./charts";

export const REPORTS = [
  { value: "cycle-execution", label: "Cycle execution" },
  { value: "results-history", label: "Results history" },
  { value: "bug-links", label: "Bug links" },
  { value: "traceability", label: "Traceability" },
  { value: "tester-activity", label: "Tester activity" },
  { value: "case-inventory", label: "Case inventory" },
] as const;

export function ReportsPage({
  project,
  tab,
  onTab,
  canExport,
}: {
  project: Project;
  tab: string;
  onTab: (t: string) => void;
  canExport: boolean;
}) {
  return (
    <Page
      title="Reports"
      subtitle="Quality trends and the standard reports. Every number has the same definition everywhere."
      width="full"
    >
      <Tabs
        label="Reports"
        value={tab}
        onValueChange={onTab}
        items={[
          { value: "quality", label: "Quality", content: <QualityTab project={project} /> },
          ...REPORTS.map((r) => ({
            value: r.value,
            label: r.label,
            content: <ReportTab key={r.value} project={project} name={r.value} canExport={canExport} />,
          })),
        ]}
      />
    </Page>
  );
}

function ReleasePicker({
  project,
  value,
  onChange,
}: {
  project: Project;
  value: string;
  onChange: (v: string) => void;
}) {
  const releases = useReleases(project.id);
  return (
    <label className="flex items-center gap-2 text-[13px]">
      <span className="text-ink-secondary">Release</span>
      <Select
        aria-label="Release"
        className="w-48"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
        }}
      >
        <option value="">All releases</option>
        {(releases.data ?? []).map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </Select>
    </label>
  );
}

const shortDay = (d: string) => d.slice(5);

function QualityTab({ project }: { project: Project }) {
  const [releaseId, setReleaseId] = useState("");
  const q = useQualityDashboard(project.id, releaseId ? { release_id: releaseId } : {});
  const toast = useToast();
  const invalidate = useInvalidateReporting();
  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <ReleasePicker project={project} value={releaseId} onChange={setReleaseId} />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void refreshMetrics(project.id).then(() => {
              toast("Today's snapshot is being refreshed");
              window.setTimeout(invalidate, 3000);
            });
          }}
        >
          <RefreshCw aria-hidden="true" className="size-3.5" /> Refresh
        </Button>
        {q.data ? (
          <span className="text-xs text-ink-secondary">
            {formatDate(q.data.date_from)} – {formatDate(q.data.date_to)} · last snapshot{" "}
            {formatDate(q.data.last_snapshot_day)} · today is live
          </span>
        ) : null}
      </div>
      {q.isPending ? (
        <Skeleton rows={6} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : (
        <>
          <div className="grid gap-5 lg:grid-cols-2">
            <ChartCard
              title="Execution and pass rate per day"
              summary={`${q.data.days.length} days; ${formatCount(q.data.days.reduce((n, d) => n + d.executed, 0))} executed in total`}
              rows={q.data.days}
              columns={[
                { key: "day", label: "Day", value: (d) => d.day },
                { key: "e", label: "Executed", value: (d) => d.executed, numeric: true },
                { key: "p", label: "Pass rate", value: (d) => formatRate(d.pass_rate), numeric: true },
              ]}
            >
              <ExecutionTrend
                data={q.data.days.map((d) => ({
                  day: shortDay(d.day),
                  executed: d.executed,
                  passed: d.passed,
                  rate: d.pass_rate.value,
                }))}
              />
            </ChartCard>
            <ChartCard
              title="Passed, failed and blocked per day"
              summary={`${formatCount(q.data.days.reduce((n, d) => n + d.failed, 0))} failed attempts in the period`}
              rows={q.data.days}
              columns={[
                { key: "day", label: "Day", value: (d) => d.day },
                { key: "p", label: "Passed", value: (d) => d.passed, numeric: true },
                { key: "f", label: "Failed", value: (d) => d.failed, numeric: true },
                { key: "b", label: "Blocked", value: (d) => d.blocked, numeric: true },
              ]}
            >
              <DailyStatus
                data={q.data.days.map((d) => ({
                  day: shortDay(d.day),
                  passed: d.passed,
                  failed: d.failed,
                  blocked: d.blocked,
                }))}
              />
            </ChartCard>
            <ChartCard
              title="Bug links per day"
              summary={`${formatCount(q.data.days.reduce((n, d) => n + d.bug_links_added, 0))} bug links added`}
              rows={q.data.days}
              columns={[
                { key: "day", label: "Day", value: (d) => d.day },
                { key: "n", label: "Links added", value: (d) => d.bug_links_added, numeric: true },
              ]}
            >
              <CountBars
                label="Links added"
                data={q.data.days.map((d) => ({ name: shortDay(d.day), value: d.bug_links_added }))}
              />
            </ChartCard>
            <ChartCard
              title="Bugs by module"
              summary={q.data.bugs_by_module.map((m) => `${m.name}: ${m.references}`).join("; ") || "No bugs"}
              rows={q.data.bugs_by_module}
              columns={[
                { key: "m", label: "Module", value: (m) => m.name },
                { key: "n", label: "Bug references", value: (m) => m.references, numeric: true },
              ]}
              empty="No bugs linked to runs in scope."
            >
              <CountBars
                label="Bug references"
                data={q.data.bugs_by_module.slice(0, 12).map((m) => ({ name: m.name, value: m.references }))}
              />
            </ChartCard>
          </div>
          <Card title="Release-wise quality" description="The last six releases" flush>
            <table aria-label="Release-wise quality" className="w-full text-left text-[13px]">
              <thead className="bg-ground text-xs text-ink-secondary">
                <tr>
                  <th className="px-5 py-2 font-medium">Release</th>
                  <th className="px-3 py-2 font-medium">Pass rate of applicable</th>
                  <th className="px-3 py-2 text-right font-medium">Failed at release</th>
                  <th className="px-3 py-2 text-right font-medium">Bug references</th>
                  <th className="px-3 py-2 font-medium">Coverage</th>
                  <th className="px-3 py-2 font-medium">Regression pass rate</th>
                </tr>
              </thead>
              <tbody>
                {q.data.releases.map((r) => (
                  <tr key={r.release.id} className="h-10 border-t border-border">
                    <td className="px-5">
                      {r.release.name}{" "}
                      <span className="text-xs text-ink-secondary">
                        {r.released_at ? formatDate(r.released_at) : r.status}
                      </span>
                    </td>
                    <td className="tabular px-3">{formatRate(r.pass_rate_applicable)}</td>
                    <td className="tabular px-3 text-right">{r.failed_at_release ?? "—"}</td>
                    <td className="tabular px-3 text-right">{formatCount(r.bug_references)}</td>
                    <td className="tabular px-3">{formatRate(r.coverage)}</td>
                    <td className="tabular px-3">{formatRate(r.regression.pass_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Automation coverage">
            <p className="text-[13px]">
              Automated {formatRate(q.data.automation.automation_coverage)} ·{" "}
              {Object.entries(q.data.automation.by_automation)
                .map(([k, n]) => `${k.replaceAll("_", " ")} ${formatCount(n)}`)
                .join(" · ")}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}

const STATUS_FILTER: Record<string, { label: string; values: string[] }> = {
  "cycle-execution": {
    label: "Status",
    values: ["passed", "failed", "blocked", "skipped", "not_applicable", "in_progress", "not_run"],
  },
  "results-history": {
    label: "Status",
    values: ["passed", "failed", "blocked", "skipped", "not_applicable"],
  },
  traceability: {
    label: "Status in release",
    values: ["passed", "failed", "blocked", "not_run", "not_covered"],
  },
};
const DATED = new Set(["results-history", "bug-links", "tester-activity"]);

function cellText(v: unknown, kind: string): string {
  if (v === null || v === undefined || v === "") return "—";
  if (kind === "datetime" && typeof v === "string") return formatDateTime(v);
  if (kind === "date" && typeof v === "string") return formatDate(v);
  if (typeof v === "number") return formatCount(v);
  if (typeof v === "string") return v.replaceAll("_", " ");
  return JSON.stringify(v);
}

function ReportTab({ project, name, canExport }: { project: Project; name: string; canExport: boolean }) {
  const [releaseId, setReleaseId] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [transferId, setTransferId] = useState<string | null>(null);
  const toast = useToast();
  const filters: Record<string, string> = {
    ...(releaseId ? { release_id: releaseId } : {}),
    ...(status ? { status } : {}),
    ...(DATED.has(name) && from ? { date_from: from } : {}),
    ...(DATED.has(name) && to ? { date_to: to } : {}),
  };
  const rep = useReport(project.id, name, { ...filters, page, page_size: 50 });
  const transfer = useTransfer(transferId);
  const doExport = async (format: "csv" | "xlsx") => {
    try {
      const out = await exportReport(project.id, name, format, filters);
      if ("transferId" in out) {
        setTransferId(out.transferId);
        toast(`${formatCount(out.rows)} rows: the file is being prepared; you will be notified`);
      }
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  };
  const statusFilter = STATUS_FILTER[name];
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-3 text-[13px]">
        <ReleasePicker
          project={project}
          value={releaseId}
          onChange={(v) => {
            setReleaseId(v);
            setPage(1);
          }}
        />
        {statusFilter ? (
          <label className="flex items-center gap-2">
            <span className="text-ink-secondary">{statusFilter.label}</span>
            <Select
              aria-label={statusFilter.label}
              className="w-40"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Any</option>
              {statusFilter.values.map((v) => (
                <option key={v} value={v}>
                  {v.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
          </label>
        ) : null}
        {DATED.has(name) ? (
          <>
            <Input
              type="date"
              aria-label="From date"
              title="From"
              className="w-40"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
              }}
            />
            <Input
              type="date"
              aria-label="To date"
              title="To"
              className="w-40"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
              }}
            />
          </>
        ) : null}
        {canExport ? (
          <span className="ml-auto flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => void doExport("csv")}>
              <Download aria-hidden="true" className="size-3.5" /> CSV
            </Button>
            <Button variant="secondary" size="sm" onClick={() => void doExport("xlsx")}>
              <Download aria-hidden="true" className="size-3.5" /> Excel
            </Button>
          </span>
        ) : null}
      </div>
      {transfer.data ? (
        <p role="status" className="text-[13px]">
          {transfer.data.status === "ready" && transfer.data.download_url ? (
            <a href={transfer.data.download_url} className="font-medium text-accent-ink hover:underline">
              Download{" "}
              {typeof transfer.data.summary.file_name === "string"
                ? transfer.data.summary.file_name
                : "the export"}{" "}
              ({formatCount(Number(transfer.data.summary.rows ?? 0))} rows)
            </a>
          ) : transfer.data.status === "failed" ? (
            "The export failed. Try again or narrow the filters."
          ) : (
            "Preparing the export…"
          )}
        </p>
      ) : null}
      {rep.isPending ? (
        <Skeleton rows={6} />
      ) : rep.isError ? (
        <ErrorState error={rep.error} onRetry={() => void rep.refetch()} />
      ) : (
        <ReportTable data={rep.data} page={page} setPage={setPage} />
      )}
    </div>
  );
}

function ReportTable({
  data,
  page,
  setPage,
}: {
  data: ReportPage;
  page: number;
  setPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  return (
    <div className="rounded-card border border-border bg-surface">
      <div className="overflow-x-auto">
        <table aria-label={`${data.title} report`} className="w-full text-left text-[12.5px]">
          <thead className="bg-ground text-xs text-ink-secondary">
            <tr>
              {data.columns.map((c) => (
                <th
                  key={c.key}
                  className={`whitespace-nowrap px-3 py-2 font-medium ${c.kind === "int" ? "text-right" : ""}`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.length === 0 ? (
              <tr>
                <td colSpan={data.columns.length} className="px-3 py-6 text-center text-ink-secondary">
                  No rows for these filters.
                </td>
              </tr>
            ) : (
              data.items.map((row, i) => (
                <tr key={i} className="h-9 border-t border-border">
                  {data.columns.map((c) => (
                    <td
                      key={c.key}
                      className={`max-w-xs truncate px-3 ${c.kind === "int" ? "tabular text-right" : ""}`}
                    >
                      {cellText(row[c.key], c.kind)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-ink-secondary">
        <span>
          {formatCount(data.total)} rows · page {page} of {pages}
        </span>
        <span className="flex gap-2">
          <Button
            variant="secondary"
            size="xs"
            disabled={page <= 1}
            onClick={() => {
              setPage(page - 1);
            }}
          >
            Previous
          </Button>
          <Button
            variant="secondary"
            size="xs"
            disabled={page >= pages}
            onClick={() => {
              setPage(page + 1);
            }}
          >
            Next
          </Button>
        </span>
      </div>
    </div>
  );
}
