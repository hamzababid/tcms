import { Link, useNavigate } from "@tanstack/react-router";
import { AlertTriangle, ListTodo, Play } from "lucide-react";

import { Card, EmptyState, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { ProgressBar } from "@/components/common/ProgressBar";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatCount, formatDate, formatDateTime, formatRate } from "@/lib/format";

import { useMyWork, type MyWork, type MyWorkCycle } from "./api";
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
          <AttentionCard items={work.data.attention} />
          <div className="grid gap-5 lg:grid-cols-3">
            <ReviewsCard reviews={work.data.reviews} />
            <Card title="Today" description="Attempts you finished today">
              <WeekSummary week={work.data.today} empty="Nothing finished today yet." />
            </Card>
            <Card title="My week" description="Attempts you finished in the last 7 days">
              <WeekSummary week={work.data.week} />
              <p className="mt-3 text-xs text-ink-secondary">
                Bugs you linked this week: {formatCount(work.data.bugs_linked_week)}
              </p>
            </Card>
          </div>
          <UpcomingCard cycles={work.data.cycles} />
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

function WeekSummary({ week, empty }: { week: MyWorkCycle["summary"]; empty?: string }) {
  const finished = week.passed + week.failed + week.blocked + week.skipped + week.not_applicable;
  if (finished === 0)
    return (
      <p className="text-[13px] text-ink-secondary">{empty ?? "Nothing finished in the last 7 days."}</p>
    );
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

/** docs/02 §11.3 QA Engineer dashboard: my failed and blocked runs, and runs flagged for retest. */
function AttentionCard({ items }: { items: MyWork["attention"] }) {
  return (
    <Card title={`Failed, blocked or to retest (${items.length})`} flush>
      {items.length === 0 ? (
        <p className="p-5 text-[13px] text-ink-secondary">
          None of your runs is failed, blocked or flagged for retest.
        </p>
      ) : (
        <ul className="divide-y divide-border text-[13px]">
          {items.map((a) => (
            <li key={a.run_id} className="flex items-center gap-3 px-5 py-2.5">
              <Link
                to="/p/$projectKey/cycles/$cycleKey/run/$runId"
                params={{ projectKey: a.project.key, cycleKey: a.cycle_key, runId: a.run_id }}
                className="w-28 shrink-0 font-mono text-[12.5px] font-medium text-link hover:underline"
              >
                {a.case_key}
              </Link>
              <span className="min-w-0 flex-1 truncate">{a.title}</span>
              <span className="font-mono text-xs text-ink-secondary">{a.cycle_key}</span>
              {a.needs_retest ? <StatusBadge kind="execution" status="needs_retest" /> : null}
              <StatusBadge kind="execution" status={a.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** Cycles starting in the next 14 days where I have runs. */
function UpcomingCard({ cycles }: { cycles: MyWorkCycle[] }) {
  const today = new Date();
  const limit = new Date(today.getTime() + 14 * 86_400_000).toISOString().slice(0, 10);
  const now = today.toISOString().slice(0, 10);
  const upcoming = cycles.filter((c) => c.start_date && c.start_date >= now && c.start_date <= limit);
  if (upcoming.length === 0) return null;
  return (
    <Card title={`Upcoming (${upcoming.length})`} description="Cycles starting in the next 14 days" flush>
      <ul className="divide-y divide-border text-[13px]">
        {upcoming.map((c) => (
          <li key={c.id} className="flex items-center gap-3 px-5 py-2.5">
            <span className="w-28 shrink-0 font-mono text-[12.5px]">{c.key}</span>
            <span className="min-w-0 flex-1 truncate">{c.name}</span>
            <span className="text-xs text-ink-secondary">starts {formatDate(c.start_date)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
