import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  ArrowUpCircle,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Play,
  RotateCcw,
} from "lucide-react";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/api/client";
import type { Me, Project } from "@/api/queries";
import { ConfirmDialog } from "@/components/common/dialogs";
import { ErrorState, Skeleton, errorMessage, useToast } from "@/components/common/feedback";
import { MarkdownView } from "@/components/common/Markdown";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Kbd } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { cn } from "@/lib/utils";

import {
  discardAttempt,
  startAttempt,
  useRunAction,
  useRunnerRun,
  useRuns,
  type QueueFilter,
  type RunRead,
} from "../api";
import { NEWER_VERSION_REASON } from "../labels";
import { DraftEditor } from "./DraftEditor";

const SHORTCUTS: [string, string][] = [
  ["P / F / B / S", "Pass, fail, block or skip the focused step"],
  ["J / K or ↓ / ↑", "Next or previous step"],
  ["Space", "Start the attempt"],
  ["A", "Attach evidence to the focused step"],
  ["Ctrl + Enter", "Finish the run"],
  ["Shift + N", "Next run in the queue"],
  ["Esc", "Leave a text field"],
  ["?", "This help"],
];

function useElapsed(since: string | null): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!since) return;
    const t = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(t);
    };
  }, [since]);
  if (!since) return "";
  const s = Math.max(0, Math.floor((now - new Date(since).getTime()) / 1000));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  return `${mm}:${String(s % 60).padStart(2, "0")}`;
}

/** Runs list query for a queue filter (docs/02 §7.4, decision D5). */
const queueQuery = (f: QueueFilter) => ({
  ...(f === "mine_open" || f === "mine" ? { assignee_id: "me" } : {}),
  ...(f === "mine_open" || f === "open" ? { status: "not_run,in_progress" } : {}),
  sort: "position",
  page: 1,
  page_size: 200,
});

/** Test runner (docs/07 §5.9, docs/design/Runner.dc.html; US-090…098). */
export function RunnerPage({
  project,
  cycleKey,
  runId,
  me,
  perms,
  onRun,
}: {
  project: Project;
  cycleKey: string;
  runId: string;
  me: Me;
  perms: Set<string>;
  onRun: (id: string) => void;
}) {
  const [filter, setFilter] = useState<QueueFilter>("mine_open");
  const [help, setHelp] = useState(false);
  const run = useRunnerRun(runId, filter);
  const used = run.data?.queue?.filter ?? filter;
  const queue = useRuns(run.data?.cycle.id, queueQuery(used));

  const next = run.data?.queue?.next_run_id ?? null;
  useEffect(() => {
    // Shift+N next run, ? help (docs/02 §7.4) — page level, not while typing.
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
      if (document.querySelector("[role=dialog]")) return;
      if (e.shiftKey && e.key.toLowerCase() === "n" && next) {
        e.preventDefault();
        onRun(next);
      } else if (e.key === "?" && !run.data?.draft) {
        e.preventDefault();
        setHelp(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [next, onRun, run.data?.draft]);

  if (run.isPending)
    return (
      <div className="p-6">
        <Skeleton rows={8} />
      </div>
    );
  if (run.isError)
    return (
      <div className="p-6">
        <ErrorState error={run.error} onRetry={() => void run.refetch()} />
      </div>
    );
  const r = run.data;
  const q = r.queue;
  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-surface px-5 py-3">
        <Link
          to="/p/$projectKey/cycles/$cycleKey"
          params={{ projectKey: project.key, cycleKey }}
          className="inline-flex min-w-0 items-center gap-2 text-[13.5px] font-medium text-ink hover:text-link"
        >
          <ArrowLeft aria-hidden="true" className="size-4 shrink-0" />
          <span className="font-mono text-[12.5px] text-ink-secondary">{r.cycle.key}</span>
          <span className="truncate">{r.cycle.name}</span>
        </Link>
        <span className="text-[13px] text-ink-secondary" aria-live="polite">
          {q?.position ? `Run ${q.position} of ${q.total}` : `${q?.total ?? 0} left`} ·{" "}
          {used.startsWith("mine") ? "my queue" : "all testers"}
        </span>
        <span className="flex-1" />
        <Button
          variant="secondary"
          size="sm"
          disabled={!q?.previous_run_id}
          onClick={() => {
            if (q?.previous_run_id) onRun(q.previous_run_id);
          }}
        >
          <ChevronLeft aria-hidden="true" className="size-4" /> Prev
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!next}
          onClick={() => {
            if (next) onRun(next);
          }}
        >
          Next <ChevronRight aria-hidden="true" className="size-4" /> <Kbd>Shift N</Kbd>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setHelp(true);
          }}
          aria-label="Keyboard shortcuts"
        >
          ?
        </Button>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          aria-label="Queue"
          className="hidden w-72 shrink-0 flex-col border-r border-border bg-surface md:flex"
        >
          <div className="flex gap-2 border-b border-border p-3">
            <select
              aria-label="Whose runs"
              className="h-8 flex-1 rounded-control border border-border-control bg-surface px-2 text-[12.5px]"
              value={used.startsWith("mine") ? "mine" : "all"}
              onChange={(e) => {
                const open = used.endsWith("open");
                setFilter(e.target.value === "mine" ? (open ? "mine_open" : "mine") : open ? "open" : "all");
              }}
            >
              <option value="mine">Mine</option>
              <option value="all">Everyone</option>
            </select>
            <select
              aria-label="Which runs"
              className="h-8 flex-1 rounded-control border border-border-control bg-surface px-2 text-[12.5px]"
              value={used.endsWith("open") ? "open" : "all"}
              onChange={(e) => {
                const mine = used.startsWith("mine");
                setFilter(e.target.value === "open" ? (mine ? "mine_open" : "open") : mine ? "mine" : "all");
              }}
            >
              <option value="open">Not done</option>
              <option value="all">All</option>
            </select>
          </div>
          <ol className="min-h-0 flex-1 overflow-y-auto p-2 text-[13px]">
            {(queue.data?.items ?? []).map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  aria-current={item.id === r.id ? "true" : undefined}
                  onClick={() => {
                    onRun(item.id);
                  }}
                  className={cn(
                    "flex h-9 w-full items-center gap-2 rounded-control px-2 text-left hover:bg-surface-muted",
                    item.id === r.id && "bg-accent-tint font-semibold text-accent-ink",
                  )}
                >
                  <StatusBadge kind="execution" status={item.status} compact />
                  <span className="w-24 shrink-0 font-mono text-[12px]">{item.test_case.key}</span>
                  <span className="min-w-0 flex-1 truncate">{item.test_case.title}</span>
                </button>
              </li>
            ))}
            {queue.data?.items.length === 0 ? (
              <li className="p-2 text-ink-muted">Nothing left in this queue.</li>
            ) : null}
          </ol>
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto bg-ground px-5 py-5">
          <RunBody
            key={`${r.id}-${r.draft?.id ?? "none"}`}
            project={project}
            run={r}
            me={me}
            perms={perms}
            queueFilter={used}
            onHelp={() => {
              setHelp(true);
            }}
            onRun={onRun}
          />
        </main>
      </div>

      <Dialog
        open={help}
        onOpenChange={setHelp}
        title="Keyboard shortcuts"
        footer={
          <Button
            onClick={() => {
              setHelp(false);
            }}
          >
            Close
          </Button>
        }
      >
        <dl className="grid grid-cols-[140px_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px]">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <Kbd>{k}</Kbd>
              </dt>
              <dd className="text-ink-secondary">{v}</dd>
            </div>
          ))}
        </dl>
      </Dialog>
    </div>
  );
}

const STATUS_WORD: Record<string, string> = {
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
  skipped: "Skipped",
  not_applicable: "N/A",
};

function RunBody({
  project,
  run: r,
  me,
  perms,
  queueFilter,
  onHelp,
  onRun,
}: {
  project: Project;
  run: RunRead;
  me: Me;
  perms: Set<string>;
  queueFilter: QueueFilter;
  onHelp: () => void;
  onRun: (id: string) => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const update = useRunAction(project.id, r.cycle.id, "update-version");
  const [busy, setBusy] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const writable = project.status !== "archived" && r.cycle.status !== "closed" && !r.superseded_by_run_id;
  const canExecute = writable && can(perms, "run.execute");
  const canManage = writable && can(perms, "cycle.manage");
  const draft = r.draft ?? null;
  const mine = draft?.executed_by?.id === me.user.id;
  const editable = Boolean(draft) && (mine ? canExecute : canManage);
  const history = r.history ?? [];
  const latest = history.at(-1);
  const elapsed = useElapsed(draft?.started_at ?? null);
  const v = r.version;

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["run"] });
    void qc.invalidateQueries({ queryKey: ["cycle", r.cycle.id] });
  };
  const start = async (body: { take_over?: boolean; corrects_result_id?: string | null } = {}) => {
    setBusy(true);
    try {
      await startAttempt(r.id, body);
      refresh();
    } catch (e) {
      toast(errorMessage(e), "error");
      if (e instanceof ApiError && e.code === "draft_exists") refresh();
    } finally {
      setBusy(false);
    }
  };

  const onFinished = async (status: string) => {
    let nextId: string | null = null;
    let nextKey = "";
    try {
      const { data: fresh } = await api.GET("/api/v1/runs/{run_id}", {
        params: { path: { run_id: r.id }, query: { include: "queue", queue_filter: queueFilter } },
      });
      nextId = fresh?.queue?.next_run_id ?? null;
      if (nextId) {
        const items = qc.getQueriesData<{ items: { id: string; test_case: { key: string } }[] }>({
          queryKey: ["cycle", r.cycle.id, "runs"],
        });
        nextKey = items.flatMap(([, d]) => d?.items ?? []).find((x) => x.id === nextId)?.test_case.key ?? "";
      }
    } catch {
      /* the queue is a convenience; the result is saved */
    }
    toast(
      `${r.test_case.key} ${STATUS_WORD[status] ?? status}${nextId ? ` · Next: ${nextKey || "next run"}` : " · Queue done"}`,
    );
    if (nextId) {
      const target = nextId;
      window.setTimeout(() => {
        onRun(target);
      }, 1000); // docs/07 §5.9 auto-advance
    }
  };

  useEffect(() => {
    // Space starts the attempt (docs/02 §7.4) when there is none.
    if (draft || !canExecute) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|TEXTAREA|SELECT|BUTTON|A)$/.test(t.tagName)) return;
      if (e.key === " " && !document.querySelector("[role=dialog]")) {
        e.preventDefault();
        void start();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  });

  return (
    <div className="mx-auto grid max-w-5xl gap-4">
      <section aria-label="Case" className="grid gap-2">
        <p className="flex flex-wrap items-center gap-2 text-[12.5px] text-ink-secondary">
          <Link
            to="/p/$projectKey/cases/$caseKey"
            params={{ projectKey: project.key, caseKey: r.test_case.key }}
            className="font-mono font-medium text-link hover:underline"
          >
            {r.test_case.key}
          </Link>
          <span>·</span>
          <span>{r.test_case.folder_path.join(" / ")}</span>
          <span>·</span>
          <PriorityIcon priority={r.test_case.priority} />
          <span className="flex-1" />
          <StatusBadge kind="execution" status={r.status} />
          {elapsed ? (
            <span
              className="tabular rounded-full bg-surface px-2 py-0.5 font-mono"
              aria-label={`Elapsed ${elapsed}`}
            >
              ⏱ {elapsed}
            </span>
          ) : null}
        </p>
        <h1 className="text-xl font-semibold leading-7 text-ink">{v?.title ?? r.test_case.title}</h1>
        <p className="text-[13px] text-ink-secondary">
          Pinned to v{r.pinned_version_no}
          {r.newer_version ? ` · v${r.newer_version.version_no} available` : ""}
        </p>
      </section>

      {r.newer_version && !r.superseded_by_run_id ? (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-card border border-accent-border bg-accent-tint px-4 py-2.5 text-[13px] text-accent-ink"
        >
          <ArrowUpCircle aria-hidden="true" className="size-4" />
          <span className="flex-1">
            v{r.newer_version.version_no} available (you are on v{r.pinned_version_no}).{" "}
            {!r.newer_version.can_update ? (NEWER_VERSION_REASON[r.newer_version.reason ?? ""] ?? "") : ""}
          </span>
          {r.newer_version.can_update && (canManage || (canExecute && r.assignee?.id === me.user.id)) ? (
            <Button
              size="xs"
              disabled={update.isPending}
              onClick={() => {
                update.mutate(r.id, {
                  onSuccess: () => {
                    toast(`Updated to v${r.newer_version?.version_no ?? ""}`);
                  },
                  onError: (e) => {
                    toast(errorMessage(e), "error");
                  },
                });
              }}
            >
              Update to v{r.newer_version.version_no}
            </Button>
          ) : null}
        </div>
      ) : null}

      {v?.preconditions || v?.test_data || v?.description ? (
        <section
          aria-label="Before you start"
          className="grid gap-3 rounded-card border border-border bg-surface p-4 md:grid-cols-2"
        >
          {v.preconditions ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">
                Preconditions
              </p>
              <MarkdownView text={v.preconditions} />
            </div>
          ) : null}
          {v.test_data ? (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">
                Test data
              </p>
              <MarkdownView text={v.test_data} />
            </div>
          ) : null}
          {v.description ? (
            <div className="md:col-span-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">
                Description
              </p>
              <MarkdownView text={v.description} />
            </div>
          ) : null}
        </section>
      ) : null}

      {r.cycle.status === "closed" ? (
        <p
          role="status"
          className="rounded-card border border-border bg-surface-muted px-4 py-2.5 text-[13px]"
        >
          The cycle is closed: runs can no longer be executed.
        </p>
      ) : r.superseded_by_run_id ? (
        <p
          role="status"
          className="rounded-card border border-border bg-surface-muted px-4 py-2.5 text-[13px]"
        >
          This run was replaced by a newer run.{" "}
          <Button
            variant="link"
            size="xs"
            onClick={() => {
              if (r.superseded_by_run_id) onRun(r.superseded_by_run_id);
            }}
          >
            Open the new run
          </Button>
        </p>
      ) : null}

      {draft ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-secondary">
            <span>
              Attempt {draft.attempt_no}
              {draft.corrects_result_id ? " (correction)" : ""} ·{" "}
              {mine ? "you" : (draft.executed_by?.display_name ?? "someone")} started{" "}
              {formatDateTime(draft.started_at)}
            </span>
            <span className="flex-1" />
            {!mine && canManage ? (
              <Button
                variant="secondary"
                size="xs"
                disabled={busy}
                onClick={() => void start({ take_over: true })}
              >
                Take over
              </Button>
            ) : null}
            {editable ? (
              <Menu>
                <MenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="More attempt actions">
                    <MoreHorizontal aria-hidden="true" className="size-4" />
                  </Button>
                </MenuTrigger>
                <MenuContent align="end">
                  <MenuItem
                    danger
                    onSelect={() => {
                      setConfirmDiscard(true);
                    }}
                  >
                    Discard draft…
                  </MenuItem>
                </MenuContent>
              </Menu>
            ) : null}
          </div>
          {!mine && !canManage ? (
            <p role="status" className="rounded-card border border-border bg-surface px-4 py-2.5 text-[13px]">
              {draft.executed_by?.display_name ?? "Someone else"} is running this attempt.
            </p>
          ) : null}
          <DraftEditor
            run={r}
            draft={draft}
            editable={editable}
            onHelp={onHelp}
            onFinished={(s) => void onFinished(s)}
          />
        </>
      ) : (
        <section aria-label="Attempt" className="grid gap-3 rounded-card border border-border bg-surface p-5">
          {latest ? (
            <p className="flex flex-wrap items-center gap-2 text-[13.5px]">
              Latest result <StatusBadge kind="execution" status={latest.status ?? "not_run"} /> by{" "}
              {latest.executed_by?.display_name ?? "—"} · {formatDateTime(latest.finished_at)}
              {latest.reason ? <span className="text-ink-secondary">· {latest.reason}</span> : null}
            </p>
          ) : (
            <p className="text-[13.5px] text-ink-secondary">This run has not been executed yet.</p>
          )}
          {canExecute ? (
            <div className="flex flex-wrap gap-2">
              {latest ? (
                <>
                  <Button disabled={busy} onClick={() => void start()}>
                    <RotateCcw aria-hidden="true" className="size-4" /> Retest
                  </Button>
                  {latest.executed_by?.id === me.user.id || canManage ? (
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => void start({ corrects_result_id: latest.id })}
                    >
                      Correct result…
                    </Button>
                  ) : null}
                </>
              ) : (
                <Button disabled={busy} onClick={() => void start()}>
                  <Play aria-hidden="true" className="size-4" /> Start <Kbd onAccent>Space</Kbd>
                </Button>
              )}
            </div>
          ) : null}
          {v && v.format === "steps" ? (
            <ol aria-label="Steps" className="grid gap-2 border-t border-border pt-3 text-[13px]">
              {v.steps.map((s) => (
                <li key={s.id} className="grid grid-cols-[28px_minmax(0,1fr)_minmax(0,1fr)] gap-3">
                  <span className="tabular text-ink-secondary">{s.position}</span>
                  <MarkdownView text={s.action} />
                  <MarkdownView text={s.expected_result ?? "—"} />
                </li>
              ))}
            </ol>
          ) : v ? (
            <MarkdownView text={v.text_body} />
          ) : null}
        </section>
      )}

      {history.length ? (
        <section
          aria-label="History"
          className="rounded-card border border-border bg-surface p-4 text-[13px]"
        >
          <h2 className="mb-2 font-semibold text-ink">History</h2>
          <ol className="grid gap-1.5">
            {history.map((a) => (
              <li
                key={a.id}
                className={cn(
                  "flex flex-wrap items-center gap-2",
                  a.corrected_by_result_id && "line-through opacity-70",
                )}
              >
                <span className="tabular w-20 text-ink-secondary">Attempt {a.attempt_no}</span>
                <StatusBadge kind="execution" status={a.status ?? "not_run"} />
                <span className="text-ink-secondary">
                  {a.executed_by?.display_name ?? "—"} · {formatDateTime(a.finished_at)}
                  {a.skipped_steps ? ` · ${a.skipped_steps} skipped` : ""}
                  {a.reason ? ` · ${a.reason}` : ""}
                </span>
                {a.corrected_by_result_id ? <span className="text-xs no-underline">(corrected)</span> : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <ConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title="Discard this draft?"
        description="The recorded steps and their evidence are deleted. The run goes back to its last result."
        confirmLabel="Discard"
        destructive
        pending={busy}
        onConfirm={() => {
          if (!draft) return;
          setBusy(true);
          discardAttempt(draft.id)
            .then(() => {
              setConfirmDiscard(false);
              toast("Draft discarded");
              refresh();
            })
            .catch((e: unknown) => {
              toast(errorMessage(e), "error");
            })
            .finally(() => {
              setBusy(false);
            });
        }}
      />
    </div>
  );
}
