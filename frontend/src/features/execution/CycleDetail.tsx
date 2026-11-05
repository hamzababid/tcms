import { Lock, Play, RotateCcw } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { useMembers, type Project } from "@/api/queries";
import { DataTable, type ServerState } from "@/components/common/DataTable";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import { Card, ErrorState, Facts, Page, Skeleton, useToast } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import type { ColumnDef } from "@tanstack/react-table";

import { useClaimRun, useCycle, useCycleAction, useRuns, type RunQuery, type RunRead } from "./api";
import { CYCLE_STATUS_LABEL, RUN_STATUS_OPTIONS } from "./labels";

/** Cycle detail: summary, progress by status, and the runs table with lifecycle/assign actions. */
export function CycleDetail({
  project,
  cycleId,
  canManage,
  canReopen,
  canExecute,
}: {
  project: Project;
  cycleId: string | undefined;
  canManage: boolean;
  canReopen: boolean;
  canExecute: boolean;
}) {
  const toast = useToast();
  const cycle = useCycle(cycleId);
  const [runQuery, setRunQuery] = useState<RunQuery>({ page: 1, page_size: 25 });
  const runs = useRuns(cycleId, runQuery);
  const members = useMembers(project.id);
  const actions = useCycleAction(project.id, cycleId ?? "");
  const claim = useClaimRun(project.id, cycleId ?? "");
  const [reopening, setReopening] = useState(false);
  const [closing, setClosing] = useState(false);
  const [closeError, setCloseError] = useState<unknown>(null);

  if (cycle.isPending)
    return (
      <div className="p-6">
        <Skeleton />
      </div>
    );
  if (cycle.isError)
    return (
      <div className="p-6">
        <ErrorState error={cycle.error} />
      </div>
    );

  const c = cycle.data;
  const closed = c.status === "closed";
  const memberName = (id: string | null | undefined) =>
    id ? (members.data?.find((m) => m.user.id === id)?.user.display_name ?? "—") : "Unassigned";

  const runColumns: ColumnDef<RunRead>[] = [
    {
      id: "position",
      header: "#",
      accessorKey: "position",
      cell: (ctx) => <span className="tabular text-ink-faint">{ctx.row.original.position}</span>,
      meta: { width: "w-12", align: "right" },
    },
    {
      id: "case_key",
      header: "Case",
      accessorKey: "case_key",
      cell: (ctx) => (
        <span className="font-mono text-[12.5px] text-ink-secondary">{ctx.row.original.case_key}</span>
      ),
      meta: { width: "w-36" },
    },
    { id: "title", header: "Title", accessorKey: "title" },
    {
      id: "version",
      header: "Version",
      cell: (ctx) => {
        const r = ctx.row.original;
        const stale = r.latest_version_no > r.version_no;
        return (
          <span className={stale ? "text-[12.5px] text-status-blocked-fg" : "text-[12.5px] text-ink-faint"}>
            v{r.version_no}
            {stale ? ` (v${r.latest_version_no} available)` : ""}
          </span>
        );
      },
      meta: { width: "w-40" },
    },
    {
      id: "status",
      header: "Status",
      accessorFn: (r) => r.status,
      cell: (ctx) => <StatusBadge kind="execution" status={ctx.row.original.status} />,
      meta: { width: "w-36", filter: { kind: "select", options: RUN_STATUS_OPTIONS } },
    },
    {
      id: "assignee",
      header: "Assignee",
      cell: (ctx) => {
        const r = ctx.row.original;
        return <span className="text-[13px]">{memberName(r.assignee?.id)}</span>;
      },
      meta: { width: "w-44" },
    },
    {
      id: "actions",
      header: "",
      cell: (ctx) => {
        const r = ctx.row.original;
        if (closed) return null;
        if (!r.assignee && canExecute) {
          return (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                void claim.mutateAsync(r.id).then(() => {
                  toast("Run claimed");
                });
              }}
            >
              Claim
            </Button>
          );
        }
        return null;
      },
      meta: { width: "w-24", align: "right" },
    },
  ];

  const server: ServerState = {
    total: runs.data?.total ?? 0,
    pagination: { pageIndex: runQuery.page - 1, pageSize: runQuery.page_size },
    onPaginationChange: (p) => {
      setRunQuery((q) => ({ ...q, page: p.pageIndex + 1, page_size: p.pageSize }));
    },
    sorting: [],
    onSortingChange: () => undefined,
    filters: runQuery.status ? [{ id: "status", value: runQuery.status }] : [],
    onFiltersChange: (f) => {
      const status = f.find((x) => x.id === "status")?.value;
      setRunQuery((q) => ({ ...q, status: typeof status === "string" ? status : undefined, page: 1 }));
    },
  };

  const lifecycle = (
    <>
      {c.status === "planned" && canManage ? (
        <Button
          variant="secondary"
          onClick={() => {
            void actions.simple("start").then(() => {
              toast("Cycle started");
            });
          }}
        >
          <Play aria-hidden="true" className="size-4" />
          Start
        </Button>
      ) : null}
      {c.status === "active" && canManage ? (
        <Button
          variant="secondary"
          onClick={() => {
            setClosing(true);
          }}
        >
          <Lock aria-hidden="true" className="size-4" />
          Close
        </Button>
      ) : null}
      {closed && canReopen ? (
        <Button
          variant="secondary"
          onClick={() => {
            setReopening(true);
          }}
        >
          <RotateCcw aria-hidden="true" className="size-4" />
          Reopen
        </Button>
      ) : null}
      {c.plan_id && !closed && canManage ? (
        <Button
          variant="ghost"
          onClick={() => {
            void actions.simple("sync-from-plan").then(() => {
              toast("Synced from plan");
            });
          }}
        >
          Sync from plan
        </Button>
      ) : null}
    </>
  );

  return (
    <Page
      title={c.name}
      eyebrow={<span className="font-mono">{c.key}</span>}
      width="full"
      actions={lifecycle}
    >
      {c.runs_pending ? (
        <div className="mb-4 rounded-card border border-accent-border bg-accent-tint px-4 py-2.5 text-[13px] text-accent-ink">
          Runs are still being created in the background. This list will fill in shortly.
        </div>
      ) : null}
      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          <Card title="Cycle">
            <Facts
              items={[
                ["Status", CYCLE_STATUS_LABEL[c.status]],
                ["Runs", c.summary.total],
                ...(c.build ? ([["Build", c.build]] as [string, string][]) : []),
                ...(c.due_date ? ([["Due", c.due_date]] as [string, string][]) : []),
              ]}
            />
          </Card>
          <Card title="Progress">
            {c.summary.total === 0 ? (
              <p className="text-[13px] text-ink-faint">No runs yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {Object.entries(c.summary.by_status).map(([status, n]) => (
                  <li key={status} className="flex items-center justify-between gap-2">
                    <StatusBadge kind="execution" status={status} />
                    <span className="tabular text-[13px] text-ink">{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <DataTable
          label="Runs"
          columns={runColumns}
          data={runs.data?.items ?? []}
          server={server}
          loading={runs.isPending}
          error={runs.error}
          noun={["run", "runs"]}
          getRowId={(r) => r.id}
          emptyText="No runs match these filters."
        />
      </div>

      <PromptDialog
        open={reopening}
        onOpenChange={setReopening}
        title="Reopen this cycle"
        label="Reason"
        submitLabel="Reopen"
        multiline
        onSubmit={(reason) => {
          void actions.reopen(reason).then(() => {
            toast("Cycle reopened");
            setReopening(false);
          });
        }}
      />
      <ConfirmDialog
        open={closing}
        onOpenChange={(o) => {
          setClosing(o);
          if (!o) setCloseError(null);
        }}
        title="Close this cycle?"
        description="A closed cycle is read-only: no runs can be executed and assignments cannot change. Draft attempts must be discarded."
        confirmLabel="Close cycle"
        error={closeError}
        onConfirm={() => {
          setCloseError(null);
          void (async () => {
            try {
              await actions.close(false);
              toast("Cycle closed");
              setClosing(false);
            } catch (e) {
              // If drafts exist, retry with discard after confirming.
              if (e instanceof ApiError && e.code === "draft_exists") {
                await actions.close(true);
                toast("Cycle closed; drafts discarded");
                setClosing(false);
              } else {
                setCloseError(e);
              }
            }
          })();
        }}
      />
    </Page>
  );
}
