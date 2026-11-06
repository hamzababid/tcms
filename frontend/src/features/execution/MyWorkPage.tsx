import { Link, useNavigate } from "@tanstack/react-router";
import { AlertTriangle, ListTodo, Play } from "lucide-react";

import { Card, EmptyState, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { ProgressBar } from "@/components/common/ProgressBar";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatCount, formatDate, formatDateTime, formatRate } from "@/lib/format";

import { useMyWork, type MyWorkCycle } from "./api";
import { LEGEND } from "./labels";

/** My Work (docs/07 §5.14, docs/02 §7.5; US-099): my runs across projects, reviews, my week. */
export function MyWorkPage() {
  const work = useMyWork();
  return (
    <Page
      title="My Work"
      subtitle="Runs assigned to you in planned and active cycles, across your projects."
      width="6xl"
    >
      {work.isPending ? (
        <Skeleton rows={6} />
      ) : work.isError ? (
        <ErrorState error={work.error} onRetry={() => void work.refetch()} />
      ) : (
        <div className="grid gap-5">
          <Card
            title={`To execute (${formatCount(work.data.cycles.reduce((n, c) => n + c.summary.not_run + c.summary.in_progress, 0))})`}
            flush
          >
            {work.data.cycles.length === 0 ? (
              <div className="p-5">
                <EmptyState
                  icon={<ListTodo className="size-5" />}
                  text="Nothing assigned to you. Claim runs from a cycle's pool, or ask your lead to assign some."
                />
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {work.data.cycles.map((c) => (
                  <CycleRow key={c.id} c={c} />
                ))}
              </ul>
            )}
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <ReviewsCard reviews={work.data.reviews} />
            <Card title="My week" description="Attempts you finished in the last 7 days">
              <WeekSummary week={work.data.week} />
            </Card>
          </div>
        </div>
      )}
    </Page>
  );
}

function CycleRow({ c }: { c: MyWorkCycle }) {
  const navigate = useNavigate();
  const s = c.summary;
  return (
    <li className="grid gap-2 px-5 py-3.5 md:grid-cols-[minmax(0,1fr)_220px_auto] md:items-center md:gap-5">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-[13.5px]">
          <Link
            to="/p/$projectKey/cycles/$cycleKey"
            params={{ projectKey: c.project.key, cycleKey: c.key }}
            className="font-mono text-[12.5px] font-medium text-link hover:underline"
          >
            {c.key}
          </Link>
          <span className="truncate font-medium text-ink">{c.name}</span>
          <StatusBadge kind="cycle" status={c.status} />
        </p>
        <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-ink-secondary">
          <span>{c.project.name}</span>
          {c.due_date ? <span>due {formatDate(c.due_date)}</span> : null}
          <span>
            {formatCount(s.not_run)} not run · {formatCount(s.in_progress)} in progress
          </span>
          {s.needs_retest ? (
            <span className="inline-flex items-center gap-1 text-[var(--status-retest-fg)]">
              <AlertTriangle aria-hidden="true" className="size-3" /> {s.needs_retest} need retest
            </span>
          ) : null}
        </p>
      </div>
      <div className="grid gap-1">
        <ProgressBar counts={s} />
        <span className="tabular text-xs text-ink-secondary">
          Executed {formatRate(s.execution_progress)}
        </span>
      </div>
      <div>
        {c.next_run_id ? (
          <Button
            size="sm"
            onClick={() =>
              void navigate({
                to: "/p/$projectKey/cycles/$cycleKey/run/$runId",
                params: { projectKey: c.project.key, cycleKey: c.key, runId: c.next_run_id ?? "" },
              })
            }
          >
            <Play aria-hidden="true" className="size-4" />
            {s.in_progress > 0 || s.executed > 0 ? "Continue" : "Start"}
            <span className="sr-only"> {c.key}</span>
          </Button>
        ) : (
          <span className="text-xs text-ink-secondary">All done ({formatCount(s.total)})</span>
        )}
      </div>
    </li>
  );
}

function ReviewsCard({
  reviews,
}: {
  reviews: { project: { key: string }; id: string; key: string; title: string; updated_at: string }[];
}) {
  return (
    <Card title={`Awaiting my review (${reviews.length})`} flush>
      {reviews.length === 0 ? (
        <p className="p-5 text-[13px] text-ink-secondary">No cases are waiting for your review.</p>
      ) : (
        <ul className="divide-y divide-border text-[13px]">
          {reviews.map((r) => (
            <li key={r.id} className="flex items-center gap-3 px-5 py-2.5">
              <Link
                to="/p/$projectKey/cases/$caseKey"
                params={{ projectKey: r.project.key, caseKey: r.key }}
                className="w-28 shrink-0 font-mono text-[12.5px] font-medium text-link hover:underline"
              >
                {r.key}
              </Link>
              <span className="min-w-0 flex-1 truncate">{r.title}</span>
              <span className="whitespace-nowrap text-xs text-ink-secondary">
                {formatDateTime(r.updated_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function WeekSummary({ week }: { week: MyWorkCycle["summary"] }) {
  const finished = week.passed + week.failed + week.blocked + week.skipped + week.not_applicable;
  if (finished === 0)
    return <p className="text-[13px] text-ink-secondary">Nothing finished in the last 7 days.</p>;
  return (
    <div className="grid gap-2 text-[13px]">
      <p className="tabular text-ink">
        <span className="font-semibold">Executed {formatCount(week.executed)}</span> · Passed{" "}
        {formatRate(week.pass_rate)}
      </p>
      <ul aria-label="My results by status" className="flex flex-wrap gap-x-4 gap-y-1.5">
        {LEGEND.filter((k) => k !== "not_run" && k !== "in_progress").map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <StatusBadge kind="execution" status={k} compact />
            <span className="tabular">{formatCount(week[k])}</span>
          </li>
        ))}
        <li className="tabular text-ink-secondary">(N/A {formatCount(week.not_applicable)})</li>
      </ul>
    </div>
  );
}
