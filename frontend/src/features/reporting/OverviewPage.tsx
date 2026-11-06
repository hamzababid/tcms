/**
 * Project Overview = QA Manager dashboard (docs/07 §5.3, §5.12; docs/02 §11.3; FR-RPT-001).
 * One request feeds every widget; numbers match the reports with the same filters (TCMS-115).
 */
import { Link } from "@tanstack/react-router";
import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

import { useEnvironments, useMembers, useReleases, type Project } from "@/api/queries";
import { Card, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { Metric } from "@/components/common/Metric";
import { ProgressBar } from "@/components/common/ProgressBar";
import { Select } from "@/components/ui/field";
import { formatCount, formatDate, formatRate } from "@/lib/format";

import { useManagerDashboard, type DashboardFilters, type ManagerDashboard } from "./api";
import { ChartCard, StatusBars } from "./charts";
import { ReadyBadge } from "./readiness";

const storageKey = (pid: string) => `assay.overview.${pid}`;

function loadFilters(pid: string): DashboardFilters | null {
  try {
    const raw = localStorage.getItem(storageKey(pid));
    return raw ? (JSON.parse(raw) as DashboardFilters) : null;
  } catch {
    return null;
  }
}

export function OverviewPage({ project }: { project: Project }) {
  const releases = useReleases(project.id);
  const envs = useEnvironments(project.id);
  const members = useMembers(project.id);
  const [chosen, setChosen] = useState<DashboardFilters | null>(() => loadFilters(project.id));
  // Until the user picks filters: the first active release (docs/02 §11.1 remembers the last filter).
  const active = releases.data?.find((r) => r.status === "active");
  const filters: DashboardFilters | null =
    chosen ?? (releases.data ? (active ? { release_id: active.id } : {}) : null);
  useEffect(() => {
    if (chosen) localStorage.setItem(storageKey(project.id), JSON.stringify(chosen));
  }, [chosen, project.id]);
  const f = filters ?? {};
  const dash = useManagerDashboard(project.id, f);
  const set = (k: keyof DashboardFilters, v: string) => {
    setChosen(Object.fromEntries(Object.entries({ ...f, [k]: v }).filter(([, x]) => Boolean(x))));
  };

  return (
    <Page
      title="Overview"
      subtitle="Release readiness, execution, bugs, coverage and team progress for the filters below."
      width="full"
    >
      <div className="mb-5 flex flex-wrap items-center gap-3 text-[13px]">
        <label className="flex items-center gap-2">
          <span className="text-ink-secondary">Release</span>
          <Select
            aria-label="Release"
            className="w-48"
            value={f.release_id ?? ""}
            onChange={(e) => {
              set("release_id", e.target.value);
            }}
          >
            <option value="">All releases</option>
            {(releases.data ?? [])
              .filter((r) => r.status !== "archived")
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
          </Select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-ink-secondary">Environment</span>
          <Select
            aria-label="Environment"
            className="w-40"
            value={f.environment_id ?? ""}
            onChange={(e) => {
              set("environment_id", e.target.value);
            }}
          >
            <option value="">All</option>
            {(envs.data ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-ink-secondary">Tester</span>
          <Select
            aria-label="Tester"
            className="w-44"
            value={f.tester_id ?? ""}
            onChange={(e) => {
              set("tester_id", e.target.value);
            }}
          >
            <option value="">Everyone</option>
            {(members.data ?? []).map((m) => (
              <option key={m.user.id} value={m.user.id}>
                {m.user.display_name}
              </option>
            ))}
          </Select>
        </label>
      </div>
      {dash.isPending || filters === null ? (
        <Skeleton rows={8} />
      ) : dash.isError ? (
        <ErrorState error={dash.error} onRetry={() => void dash.refetch()} />
      ) : (
        <Widgets project={project} d={dash.data} />
      )}
    </Page>
  );
}

function Widgets({ project, d }: { project: Project; d: ManagerDashboard }) {
  const key = project.key;
  const s = d.summary;
  const active = d.cycles.filter((c) => c.status !== "closed");
  return (
    <div className="grid gap-5">
      <div className="grid gap-5 lg:grid-cols-3">
        <Card
          title="Readiness"
          footer={
            d.readiness ? (
              <Link
                to="/p/$projectKey/releases/$releaseId"
                params={{ projectKey: key, releaseId: d.readiness.release.id }}
                className="text-[13px] font-medium text-accent-ink hover:underline"
              >
                View readiness →
              </Link>
            ) : null
          }
        >
          {d.readiness ? (
            <div className="flex flex-col gap-2">
              <ReadyBadge ready={d.readiness.ready} size="lg" />
              <p className="text-[13px] text-ink-secondary">
                {d.readiness.release.name}: {d.readiness.met} of {d.readiness.total} rules met
                {d.readiness.uses_defaults ? " (default rules)" : ""}
              </p>
            </div>
          ) : (
            <p className="text-[13px] text-ink-secondary">Choose a release to see its readiness.</p>
          )}
        </Card>
        <Card title="Execution">
          <div className="flex flex-col gap-3">
            <Metric noun="applicable executed" rate={s.execution_progress} emptyText="No runs in scope" />
            <p className="text-[13px] text-ink">Pass rate {formatRate(s.pass_rate)}</p>
            <ProgressBar counts={s} />
            <p className="text-xs text-ink-secondary">
              {formatCount(s.total)} runs · {formatCount(s.not_applicable)} N/A ·{" "}
              {formatCount(s.needs_retest)} to retest · {formatCount(d.retest_count)} retests
            </p>
          </div>
        </Card>
        <Card
          title="Bugs"
          footer={
            <Link
              to="/p/$projectKey/bugs"
              params={{ projectKey: key }}
              className="text-[13px] font-medium text-accent-ink hover:underline"
            >
              View bugs →
            </Link>
          }
        >
          <dl className="grid grid-cols-[1fr_auto] gap-y-1.5 text-[13px]">
            <dt className="text-ink-secondary">Linked</dt>
            <dd className="tabular text-right font-semibold">{formatCount(d.bugs.linked)}</dd>
            <dt className="text-ink-secondary">On failing runs</dt>
            <dd className="tabular text-right font-semibold">{formatCount(d.bugs.on_failing_runs)}</dd>
            <dt className="text-ink-secondary">Failures without a bug</dt>
            <dd className="tabular text-right font-semibold">{formatCount(d.bugs.failures_without_bug)}</dd>
          </dl>
          {d.top_bugs.length ? (
            <ul className="mt-3 flex flex-col gap-1 text-xs">
              {d.top_bugs.slice(0, 5).map((b) => (
                <li key={b.reference} className="flex justify-between gap-2">
                  <span className="truncate">
                    <span className="font-mono text-[var(--status-fail-fg)]">{b.reference}</span>{" "}
                    {b.title ?? ""}
                  </span>
                  <span className="tabular text-ink-secondary">{b.failing_runs} failing</span>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>
      </div>
      <Card title={`Active cycles (${active.length})`} flush>
        {active.length === 0 ? (
          <p className="p-5 text-[13px] text-ink-secondary">No planned or active cycles for these filters.</p>
        ) : (
          <ul className="divide-y divide-border">
            {active.map((c) => (
              <li
                key={c.id}
                className="grid items-center gap-3 px-5 py-3 text-[13px] md:grid-cols-[minmax(0,2fr)_minmax(0,2fr)_auto]"
              >
                <span className="min-w-0 truncate">
                  <Link
                    to="/p/$projectKey/cycles/$cycleKey"
                    params={{ projectKey: key, cycleKey: c.key }}
                    className="font-mono text-xs text-accent-ink hover:underline"
                  >
                    {c.key}
                  </Link>{" "}
                  {c.name} <span className="text-ink-secondary">· {c.environment.name}</span>
                </span>
                <ProgressBar counts={c.summary} />
                <span className="flex items-center gap-2 whitespace-nowrap text-xs text-ink-secondary">
                  <span className="tabular">
                    {formatCount(c.summary.executed)}/{formatCount(c.summary.applicable)}
                  </span>
                  {c.due_date ? <span>due {formatDate(c.due_date)}</span> : null}
                  {c.overdue ? (
                    <span className="inline-flex items-center gap-1 text-[var(--status-fail-fg)]">
                      <AlertTriangle aria-hidden="true" className="size-3.5" /> Overdue
                    </span>
                  ) : null}
                  {c.summary.needs_retest ? <span>⟳ {c.summary.needs_retest} retest</span> : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <ChartCard
          title="Status by cycle"
          summary={`${d.cycles.length} cycles; ${d.cycles.map((c) => `${c.key}: ${c.summary.passed} passed, ${c.summary.failed} failed`).join("; ")}`}
          rows={d.cycles}
          columns={[
            { key: "key", label: "Cycle", value: (c) => c.key },
            { key: "p", label: "Passed", value: (c) => c.summary.passed, numeric: true },
            { key: "f", label: "Failed", value: (c) => c.summary.failed, numeric: true },
            { key: "b", label: "Blocked", value: (c) => c.summary.blocked, numeric: true },
            { key: "s", label: "Skipped", value: (c) => c.summary.skipped, numeric: true },
            {
              key: "n",
              label: "Not run",
              value: (c) => c.summary.not_run + c.summary.in_progress,
              numeric: true,
            },
          ]}
        >
          <StatusBars
            data={d.cycles.slice(0, 12).map((c) => ({
              name: c.key,
              passed: c.summary.passed,
              failed: c.summary.failed,
              blocked: c.summary.blocked,
              skipped: c.summary.skipped,
              not_run: c.summary.not_run + c.summary.in_progress,
            }))}
          />
        </ChartCard>
        <Card
          title="Requirement coverage"
          footer={
            <Link
              to="/p/$projectKey/traceability"
              params={{ projectKey: key }}
              className="text-[13px] font-medium text-accent-ink hover:underline"
            >
              View traceability →
            </Link>
          }
        >
          <div className="flex flex-col gap-2 text-[13px]">
            <p>Covered {formatRate(d.coverage.coverage)}</p>
            <p>Verified {formatRate(d.coverage.verified)}</p>
            {d.top_uncovered.length ? (
              <>
                <p className="mt-2 text-xs font-medium text-ink-secondary">Not covered</p>
                <ul className="flex flex-wrap gap-1.5 text-xs">
                  {d.top_uncovered.map((r) => (
                    <li
                      key={r.id}
                      className="rounded-full border border-border px-2 py-0.5 font-mono"
                      title={r.title ?? undefined}
                    >
                      {r.reference}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        </Card>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Team progress" className="lg:col-span-2" flush>
          {d.team.length === 0 ? (
            <p className="p-5 text-[13px] text-ink-secondary">No runs in scope.</p>
          ) : (
            <table aria-label="Team progress" className="w-full text-left text-[13px]">
              <thead className="bg-ground text-xs text-ink-secondary">
                <tr>
                  <th className="px-5 py-2 font-medium">Tester</th>
                  <th className="px-3 py-2 text-right font-medium">Assigned</th>
                  <th className="px-3 py-2 text-right font-medium">Executed</th>
                  <th className="px-3 py-2 text-right font-medium">Remaining</th>
                  <th className="px-3 py-2 text-right font-medium">Failed</th>
                  <th className="px-3 py-2 text-right font-medium">Blocked</th>
                </tr>
              </thead>
              <tbody>
                {d.team.map((t) => (
                  <tr key={t.user?.id ?? "pool"} className="h-9 border-t border-border">
                    <td className="px-5">
                      {t.user ? (
                        t.user.display_name
                      ) : (
                        <span className="text-ink-secondary">Unassigned pool</span>
                      )}
                    </td>
                    <td className="tabular px-3 text-right">{formatCount(t.assigned)}</td>
                    <td className="tabular px-3 text-right">{formatCount(t.executed)}</td>
                    <td className="tabular px-3 text-right">{formatCount(t.remaining)}</td>
                    <td className="tabular px-3 text-right">{formatCount(t.failed)}</td>
                    <td className="tabular px-3 text-right">{formatCount(t.blocked)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <div className="grid gap-5">
          <Card title="Regression" description="Runs of cases tagged regression">
            <div className="flex flex-col gap-2 text-[13px]">
              <p>Progress {formatRate(d.regression.execution_progress)}</p>
              <p>Pass rate {formatRate(d.regression.pass_rate)}</p>
              <ProgressBar counts={d.regression} />
            </div>
          </Card>
          <Card
            title="Repository"
            footer={
              <Link
                to="/p/$projectKey/repository"
                params={{ projectKey: key }}
                className="text-[13px] font-medium text-accent-ink hover:underline"
              >
                Open repository →
              </Link>
            }
          >
            <div className="flex flex-col gap-1.5 text-[13px]">
              <p>
                <strong className="tabular">{formatCount(d.repository.total_cases)}</strong> cases in{" "}
                {formatCount(d.repository.folders)} folders
              </p>
              <p>Approved {formatRate(d.repository.approved)}</p>
              <p>Automated {formatRate(d.repository.automation_coverage)}</p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
