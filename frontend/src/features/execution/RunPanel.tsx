import { Link } from "@tanstack/react-router";
import { ArrowUpCircle, Play, X } from "lucide-react";
import type { ReactNode } from "react";

import type { Project } from "@/api/queries";
import { ErrorState, Facts, Skeleton, errorMessage, useToast } from "@/components/common/feedback";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";

import { useRun, useRunAction, type RunRead } from "./api";
import { NEWER_VERSION_REASON } from "./labels";

/**
 * Run side panel (docs/07 §4.2, §5.8): the run's case, pinned version, assignee and attempts, with
 * claim (US-082), update to the newer version (BR-04) or replace with a new run (BR-05).
 */
export function RunPanel({
  project,
  cycleId,
  runId,
  meId,
  canManage,
  canExecute,
  onClose,
  onOpenRun,
}: {
  project: Project;
  cycleId: string;
  runId: string;
  meId: string;
  canManage: boolean;
  canExecute: boolean;
  onClose: () => void;
  onOpenRun: (id: string) => void;
}) {
  const run = useRun(runId);
  return (
    <aside
      aria-label={run.data ? `${run.data.test_case.key} details` : "Run details"}
      className="flex w-[clamp(360px,30vw,520px)] shrink-0 flex-col overflow-hidden border-l border-border bg-surface"
    >
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <span className="min-w-0 truncate text-[13px] font-semibold text-ink">
          {run.data ? (
            <>
              <span className="font-mono">{run.data.test_case.key}</span> · run #{run.data.position}
            </>
          ) : (
            "Run"
          )}
        </span>
        <Button variant="ghost" size="icon" aria-label="Close run details" onClick={onClose}>
          <X aria-hidden="true" className="size-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {run.isPending ? (
          <Skeleton rows={6} />
        ) : run.isError ? (
          <ErrorState error={run.error} onRetry={() => void run.refetch()} />
        ) : (
          <RunBody
            project={project}
            cycleId={cycleId}
            run={run.data}
            meId={meId}
            canManage={canManage}
            canExecute={canExecute}
            onOpenRun={onOpenRun}
          />
        )}
      </div>
    </aside>
  );
}

function RunBody({
  project,
  cycleId,
  run: r,
  meId,
  canManage,
  canExecute,
  onOpenRun,
}: {
  project: Project;
  cycleId: string;
  run: RunRead;
  meId: string;
  canManage: boolean;
  canExecute: boolean;
  onOpenRun: (id: string) => void;
}) {
  const toast = useToast();
  const claim = useRunAction(project.id, cycleId, "claim");
  const update = useRunAction(project.id, cycleId, "update-version");
  const replace = useRunAction(project.id, cycleId, "replace");
  const open = r.cycle.status !== "closed" && project.status !== "archived";
  const newer = r.newer_version;
  const isAssignee = r.assignee?.id === meId;
  const onError = (e: unknown) => {
    toast(errorMessage(e), "error");
  };

  return (
    <div className="grid gap-5">
      <div>
        <h2 className="text-[15px] font-semibold leading-6 text-ink">{r.test_case.title}</h2>
        <p className="mt-0.5 text-xs text-ink-secondary">{r.test_case.folder_path.join(" / ")}</p>
        <Link
          to="/p/$projectKey/cycles/$cycleKey/run/$runId"
          params={{ projectKey: project.key, cycleKey: r.cycle.key, runId: r.id }}
          className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-control bg-accent px-3 text-[13px] font-medium text-white hover:bg-accent-hover"
        >
          <Play aria-hidden="true" className="size-4" />
          {r.history?.length ? "Open in runner" : "Execute"}
        </Link>
      </div>

      {r.superseded_by_run_id ? (
        <div
          role="status"
          className="rounded-card border border-border bg-surface-muted px-3 py-2 text-[13px]"
        >
          This run was replaced by a newer run; its results are kept for history.{" "}
          <Button
            variant="link"
            size="xs"
            onClick={() => {
              if (r.superseded_by_run_id) onOpenRun(r.superseded_by_run_id);
            }}
          >
            Open the new run
          </Button>
        </div>
      ) : null}

      {newer && !r.superseded_by_run_id ? (
        <div
          role="status"
          className="grid gap-2 rounded-card border border-accent-border bg-accent-tint px-3 py-2.5 text-[13px] text-accent-ink"
        >
          <p className="flex items-center gap-1.5 font-medium">
            <ArrowUpCircle aria-hidden="true" className="size-4" />v{newer.version_no} available (you are on v
            {r.pinned_version_no})
          </p>
          {newer.can_update ? (
            open && (canManage || (isAssignee && canExecute)) ? (
              <div>
                <Button
                  size="xs"
                  disabled={update.isPending}
                  onClick={() => {
                    update.mutate(r.id, {
                      onSuccess: () => {
                        toast(`Updated to v${newer.version_no}`);
                      },
                      onError,
                    });
                  }}
                >
                  Update to v{newer.version_no}
                </Button>
              </div>
            ) : null
          ) : (
            <>
              <p className="text-ink-secondary">{NEWER_VERSION_REASON[newer.reason ?? ""] ?? newer.reason}</p>
              {open && canManage && newer.reason === "run_has_results" ? (
                <div>
                  <Button
                    size="xs"
                    variant="secondary"
                    disabled={replace.isPending}
                    onClick={() => {
                      replace.mutate(r.id, {
                        onSuccess: (created) => {
                          toast(`New run at v${created.pinned_version_no}`);
                          onOpenRun(created.id);
                        },
                        onError,
                      });
                    }}
                  >
                    Replace with a new run on v{newer.version_no}
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}

      <Facts
        items={[
          ["Status", <StatusBadge key="s" kind="execution" status={r.status} />],
          ...(r.needs_retest
            ? ([["Retest", <StatusBadge key="r" kind="execution" status="needs_retest" />]] as [
                string,
                ReactNode,
              ][])
            : []),
          [
            "Assignee",
            <span key="a" className="flex items-center gap-2">
              {r.assignee?.display_name ?? <span className="text-ink-muted">— pool —</span>}
              {!r.assignee && open && canExecute && !r.superseded_by_run_id ? (
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={claim.isPending}
                  onClick={() => {
                    claim.mutate(r.id, {
                      onSuccess: () => {
                        toast(`${r.test_case.key} is yours`);
                      },
                      onError,
                    });
                  }}
                >
                  Claim
                </Button>
              ) : null}
            </span>,
          ],
          ["Version", `v${r.pinned_version_no}`],
          ["Priority", <PriorityIcon key="p" priority={r.test_case.priority} />],
          [
            "Case",
            <a
              key="c"
              href={`/p/${project.key}/cases/${r.test_case.key}`}
              className="font-mono text-[12.5px] text-link hover:underline"
            >
              {r.test_case.key}
            </a>,
          ],
        ]}
      />

      <section>
        <h3 className="mb-2 text-[13px] font-semibold text-ink">Attempts</h3>
        {(r.history ?? []).length === 0 ? (
          <p className="text-[13px] text-ink-muted">No attempts yet.</p>
        ) : (
          <ol className="grid gap-1.5 text-[13px]">
            {(r.history ?? []).map((a) => (
              <li key={a.id} className="flex items-center gap-2">
                <span className="tabular w-8 text-ink-muted">#{a.attempt_no}</span>
                <StatusBadge kind="execution" status={a.status ?? "in_progress"} />
                <span className="min-w-0 flex-1 truncate text-ink-secondary">
                  {a.executed_by?.display_name ?? "—"} · {formatDateTime(a.finished_at ?? a.started_at)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
