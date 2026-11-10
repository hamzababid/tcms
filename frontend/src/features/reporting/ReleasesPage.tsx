/** Releases list and release page with readiness and decisions (docs/07 §5.15; FR-RPT-006, UJ-8). */
import { Link } from "@tanstack/react-router";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";

import { useReleases, type Project } from "@/api/queries";
import { Card, EmptyState, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { ProgressBar } from "@/components/common/ProgressBar";
import { DataTable, Pager, usePaging } from "@/components/common/DataTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { useCycles } from "@/features/execution/api";
import { usePlans } from "@/features/planning/api";
import { formatCount, formatDate, formatRate } from "@/lib/format";

import {
  DECISION_LABEL,
  useDecisions,
  useManagerDashboard,
  useReleaseReadiness,
  useReleaseSummaries,
} from "./api";
import { DecisionDialog, DecisionTimeline, ReadinessRules, ReadyBadge } from "./readiness";

const RELEASE_STATUS: Record<string, string> = {
  planned: "Planned",
  active: "Active",
  released: "Released",
  archived: "Archived",
};

type ReleaseSummary = NonNullable<ReturnType<typeof useReleaseSummaries>["data"]>[number];

export function ReleasesPage({ project }: { project: Project }) {
  const list = useReleaseSummaries(project.id);
  const columns: ColumnDef<ReleaseSummary>[] = [
    {
      id: "name",
      header: "Release",
      accessorKey: "name",
      cell: (c) => {
        const r = c.row.original;
        return (
          <div>
            <Link
              to="/p/$projectKey/releases/$releaseId"
              params={{ projectKey: project.key, releaseId: r.id }}
              className="font-medium text-accent-ink hover:underline"
            >
              {r.name}
            </Link>
            <div className="text-xs text-ink-secondary">
              {r.plan_count} plans · {r.cycle_count} cycles
            </div>
          </div>
        );
      },
      meta: { fixed: true, filter: { kind: "text", placeholder: "Release name" } },
    },
    {
      id: "status",
      header: "Status",
      accessorKey: "status",
      cell: (c) => RELEASE_STATUS[c.row.original.status] ?? c.row.original.status,
      meta: {
        width: "w-32",
        filter: {
          kind: "select",
          options: Object.entries(RELEASE_STATUS).map(([value, label]) => ({ value, label })),
        },
      },
    },
    {
      id: "target_date",
      header: "Target",
      accessorFn: (r) => r.target_date ?? "",
      cell: (c) => formatDate(c.row.original.target_date),
      meta: { width: "w-36", filter: { kind: "daterange" } },
    },
    {
      id: "execution",
      header: "Execution",
      enableSorting: false,
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
      id: "ready",
      header: "Readiness",
      accessorFn: (r) => (r.ready ? "ready" : "not_ready"),
      cell: (c) => <ReadyBadge ready={c.row.original.ready} />,
      meta: {
        width: "w-32",
        filter: {
          kind: "select",
          options: [
            { value: "ready", label: "Ready" },
            { value: "not_ready", label: "Not ready" },
          ],
        },
      },
    },
    {
      id: "decision",
      header: "Latest decision",
      accessorFn: (r) => r.latest_decision?.decided_at ?? "",
      cell: (c) => {
        const d = c.row.original.latest_decision;
        return d ? (
          <span>
            <strong>{DECISION_LABEL[d.decision]}</strong>{" "}
            <span className="text-xs text-ink-secondary">{formatDate(d.decided_at)}</span>
          </span>
        ) : (
          <span className="text-ink-muted">—</span>
        );
      },
      meta: { width: "w-44" },
    },
  ];
  return (
    <Page
      title="Releases"
      subtitle="Execution and readiness per release, and the go/no-go decisions recorded for it. Create and edit releases in Settings."
      width="full"
    >
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : (
        <DataTable
          label="Releases"
          columns={columns}
          data={list.data ?? []}
          getRowId={(r) => r.id}
          loading={list.isPending}
          noun={["release", "releases"]}
          emptyText="No releases match these filters."
          empty={
            <EmptyState text="No releases yet. A QA Manager creates them in Project settings › Releases." />
          }
        />
      )}
    </Page>
  );
}

export function ReleasePage({
  project,
  releaseId,
  canDecide,
}: {
  project: Project;
  releaseId: string;
  canDecide: boolean;
}) {
  const releases = useReleases(project.id);
  const rel = releases.data?.find((r) => r.id === releaseId);
  const ready = useReleaseReadiness(releaseId);
  const decisions = useDecisions(releaseId);
  const [tab, setTab] = useState("readiness");
  const [deciding, setDeciding] = useState(false);
  const writable = project.status !== "archived" && rel?.status !== "archived";
  if (releases.isPending || ready.isPending)
    return (
      <div className="p-6">
        <Skeleton rows={6} />
      </div>
    );
  if (ready.isError)
    return (
      <div className="p-6">
        <ErrorState error={ready.error} />
      </div>
    );
  if (!rel)
    return (
      <div className="p-6">
        <EmptyState text="This release does not exist in the project." />
      </div>
    );
  const r = ready.data;
  return (
    <Page
      title={rel.name}
      eyebrow={
        <Link to="/p/$projectKey/releases" params={{ projectKey: project.key }} className="hover:underline">
          Releases
        </Link>
      }
      subtitle={`${RELEASE_STATUS[rel.status] ?? rel.status} · ${formatDate(rel.start_date)} – ${formatDate(rel.target_date)}`}
      actions={
        <>
          <ReadyBadge ready={r.ready} size="lg" />
          {canDecide && writable ? (
            <Button
              onClick={() => {
                setDeciding(true);
              }}
            >
              Record decision…
            </Button>
          ) : null}
        </>
      }
      width="6xl"
    >
      <Tabs
        label="Release"
        value={tab}
        onValueChange={setTab}
        items={[
          { value: "readiness", label: "Readiness", content: <ReadinessTab r={r} /> },
          { value: "plans", label: "Plans", content: <PlansTab project={project} releaseId={releaseId} /> },
          {
            value: "cycles",
            label: "Cycles",
            content: <CyclesTab project={project} releaseId={releaseId} />,
          },
          { value: "bugs", label: "Bugs", content: <BugsTab project={project} releaseId={releaseId} /> },
          {
            value: "decisions",
            label: "Decisions",
            count: decisions.data?.length ?? 0,
            content: decisions.data ? <DecisionTimeline decisions={decisions.data} /> : <Skeleton />,
          },
        ]}
      />
      <DecisionDialog
        releaseId={releaseId}
        releaseName={rel.name}
        ready={r.ready}
        open={deciding}
        onClose={() => {
          setDeciding(false);
        }}
      />
    </Page>
  );
}

function ReadinessTab({ r }: { r: NonNullable<ReturnType<typeof useReleaseReadiness>["data"]> }) {
  return (
    <div className="grid gap-5">
      <p className="text-[13px] text-ink-secondary">
        {r.uses_defaults
          ? "No plan of this release has exit rules, so the default rules apply to every cycle of the release."
          : "Each plan's exit rules are checked against that plan's cycles. The release is ready when every plan is ready."}
      </p>
      {r.plans.length ? (
        <ul className="flex flex-wrap gap-3 text-[13px]">
          {r.plans.map((p) => (
            <li
              key={p.plan.id}
              className="flex items-center gap-2 rounded-card border border-border bg-surface px-3 py-2"
            >
              <span className="font-mono text-xs">{p.plan.key}</span> {p.plan.name}{" "}
              <ReadyBadge ready={p.ready} />
            </li>
          ))}
        </ul>
      ) : null}
      <ReadinessRules rules={r.rules} />
      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Execution in the release">
          <div className="flex flex-col gap-2 text-[13px]">
            <ProgressBar counts={r.summary} />
            <p>Progress {formatRate(r.summary.execution_progress)}</p>
            <p>Pass rate {formatRate(r.summary.pass_rate)}</p>
            <p>Pass rate of applicable {formatRate(r.summary.pass_rate_applicable)}</p>
            <p className="text-xs text-ink-secondary">
              {formatCount(r.summary.failed)} failed · {formatCount(r.summary.blocked)} blocked ·{" "}
              {formatCount(r.summary.not_run)} not run
            </p>
          </div>
        </Card>
        <Card title="Requirement coverage">
          <div className="flex flex-col gap-2 text-[13px]">
            <p>Covered {formatRate(r.coverage.coverage)}</p>
            <p>Verified {formatRate(r.coverage.verified)}</p>
          </div>
        </Card>
      </div>
    </div>
  );
}

function PlansTab({ project, releaseId }: { project: Project; releaseId: string }) {
  const [pagination, setPagination] = usePaging(releaseId);
  const plans = usePlans(project.id, {
    release_id: releaseId,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  });
  if (plans.isPending) return <Skeleton />;
  if (plans.isError) return <ErrorState error={plans.error} />;
  if (plans.data.total === 0) return <EmptyState text="No plans in this release." />;
  return (
    <div className="rounded-card border border-border bg-surface">
      <ul aria-label="Plans in the release" className="divide-y divide-border">
        {plans.data.items.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-3 text-[13px]">
            <Link
              to="/p/$projectKey/plans/$planKey"
              params={{ projectKey: project.key, planKey: p.key }}
              className="hover:underline"
            >
              <span className="font-mono text-xs text-accent-ink">{p.key}</span> {p.name}
            </Link>
            <span className="text-xs text-ink-secondary">{p.case_count} cases</span>
          </li>
        ))}
      </ul>
      <Pager
        label="Plans in the release"
        total={plans.data.total}
        pagination={pagination}
        onChange={setPagination}
        noun={["plan", "plans"]}
      />
    </div>
  );
}

function CyclesTab({ project, releaseId }: { project: Project; releaseId: string }) {
  const [pagination, setPagination] = usePaging(releaseId);
  const cycles = useCycles(project.id, {
    release_id: releaseId,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  });
  if (cycles.isPending) return <Skeleton />;
  if (cycles.isError) return <ErrorState error={cycles.error} />;
  if (cycles.data.total === 0) return <EmptyState text="No cycles in this release." />;
  return (
    <div className="rounded-card border border-border bg-surface">
      <ul aria-label="Cycles in the release" className="divide-y divide-border">
        {cycles.data.items.map((c) => (
          <li
            key={c.id}
            className="grid items-center gap-3 px-4 py-3 text-[13px] md:grid-cols-[minmax(0,2fr)_auto_minmax(0,2fr)]"
          >
            <Link
              to="/p/$projectKey/cycles/$cycleKey"
              params={{ projectKey: project.key, cycleKey: c.key }}
              className="truncate hover:underline"
            >
              <span className="font-mono text-xs text-accent-ink">{c.key}</span> {c.name}
            </Link>
            <StatusBadge kind="cycle" status={c.status} />
            <ProgressBar counts={c.summary} />
          </li>
        ))}
      </ul>
      <Pager
        label="Cycles in the release"
        total={cycles.data.total}
        pagination={pagination}
        onChange={setPagination}
        noun={["cycle", "cycles"]}
      />
    </div>
  );
}

function BugsTab({ project, releaseId }: { project: Project; releaseId: string }) {
  const d = useManagerDashboard(project.id, { release_id: releaseId });
  if (d.isPending) return <Skeleton />;
  if (d.isError) return <ErrorState error={d.error} />;
  const b = d.data.bugs;
  return (
    <div className="grid gap-4 text-[13px]">
      <p>
        {formatCount(b.linked)} bug references linked to runs of this release ·{" "}
        {formatCount(b.on_failing_runs)} on failing runs · {formatCount(b.failures_without_bug)} failures
        without a bug
      </p>
      {d.data.top_bugs.length ? (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {d.data.top_bugs.map((x) => (
            <li key={x.reference} className="flex justify-between gap-3 px-4 py-2">
              <span>
                <span className="font-mono text-[var(--status-fail-fg)]">{x.reference}</span> {x.title ?? ""}
              </span>
              <span className="text-xs text-ink-secondary">
                {x.failing_runs} failing of {x.runs} runs
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <Link
        to="/p/$projectKey/bugs"
        params={{ projectKey: project.key }}
        className="font-medium text-accent-ink hover:underline"
      >
        All bugs →
      </Link>
    </div>
  );
}
