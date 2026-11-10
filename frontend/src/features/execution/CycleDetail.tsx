import { Link } from "@tanstack/react-router";
import type { ColumnDef, ColumnFiltersState, SortingState } from "@tanstack/react-table";
import { AlertTriangle, ChevronDown, Lock, MoreHorizontal, Play, Plus } from "lucide-react";
import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { useNavigate } from "@tanstack/react-router";

import { api } from "@/api/client";
import { useMembers, type Me, type Project } from "@/api/queries";
import { DataTable, filterValue, sortParam, usePaging } from "@/components/common/DataTable";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import { Card, ErrorState, PageHeader, Skeleton, errorMessage, useToast } from "@/components/common/feedback";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { ProgressBar } from "@/components/common/ProgressBar";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/field";
import { SavedViewsMenu, useSavedViews } from "@/features/views/SavedViews";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { Tabs } from "@/components/ui/tabs";
import { useCycleBugLinks, type BugLink } from "@/features/bugs/api";
import { BugChips, trackerOf } from "@/features/bugs/components";
import { RecordHistory } from "@/features/projects/RecordHistory";
import { useFolders } from "@/features/testdesign/api";
import { AddCasesDialog } from "@/features/testdesign/CaseSelector";
import { PRIORITY_LABELS } from "@/features/testdesign/labels";
import { formatDate, formatDateTime, formatRate } from "@/lib/format";
import { can } from "@/lib/permissions";

import {
  useAddRuns,
  useArchiveCycle,
  useAssignRuns,
  useCycle,
  useExecutors,
  useRemoveRuns,
  useReopenCycle,
  useRunAction,
  useRuns,
  useSortRuns,
  useStartCycle,
  useSyncFromPlan,
  useUpdateNotRunVersions,
  type CycleRead,
  type GroupProgress,
  type RunListItem,
  type RunQuery,
} from "./api";
import { AssignDialog, CloneCycleDialog, CloseCycleDialog, EditCycleDialog } from "./CycleDialogs";
import { LEGEND, RUN_STATUS_OPTIONS } from "./labels";
import { RunPanel } from "./RunPanel";

type Dialog =
  | "edit"
  | "close"
  | "reopen"
  | "clone"
  | "archive"
  | "add"
  | "assign-folder"
  | "assign-selected"
  | "remove"
  | null;

/** Cycle detail (docs/07 §5.8, docs/design/CycleDetail.dc.html; US-081…087). */
export function CycleDetail({
  project,
  cycleId,
  me,
  perms,
  runId,
  onRun,
}: {
  project: Project;
  cycleId: string;
  me: Me;
  perms: Set<string>;
  runId: string | null;
  onRun: (id: string | null) => void;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const cycle = useCycle(cycleId);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [section, setSection] = useState("runs");

  if (cycle.isPending)
    return (
      <div className="p-6">
        <Skeleton rows={8} />
      </div>
    );
  if (cycle.isError)
    return (
      <div className="p-6">
        <ErrorState error={cycle.error} onRetry={() => void cycle.refetch()} />
      </div>
    );

  const c = cycle.data;
  const projectWritable = project.status !== "archived";
  const canManage = projectWritable && can(perms, "cycle.manage") && !c.archived;
  const canReopen = projectWritable && can(perms, "cycle.reopen") && !c.archived;
  const canExecute = projectWritable && can(perms, "run.execute");
  const closed = c.status === "closed";
  const openCycle = (key: string) =>
    void navigate({
      to: "/p/$projectKey/cycles/$cycleKey",
      params: { projectKey: project.key, cycleKey: key },
    });

  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <PageHeader
        title={c.name}
        eyebrow={
          <span className="flex items-center gap-2">
            <span className="font-mono">{c.key}</span>
            <StatusBadge kind="cycle" status={c.status} />
            {c.archived ? <span className="text-ink-muted">Archived</span> : null}
          </span>
        }
        subtitle={metaLine(c)}
        actions={
          <CycleActions
            project={project}
            cycle={c}
            canManage={canManage}
            canReopen={canReopen}
            canExecute={canExecute}
            onDialog={setDialog}
          />
        }
      />
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto px-6 py-5">
          {c.plan ? (
            <p className="-mt-1 mb-3 text-[13px] text-ink-secondary">
              From plan{" "}
              <Link
                to="/p/$projectKey/plans/$planKey"
                params={{ projectKey: project.key, planKey: c.plan.key }}
                className="font-mono text-link hover:underline"
              >
                {c.plan.key}
              </Link>{" "}
              {c.plan.title}
            </p>
          ) : null}
          {c.runs_pending ? (
            <div
              role="status"
              className="mb-4 rounded-card border border-accent-border bg-accent-tint px-4 py-2.5 text-[13px] text-accent-ink"
            >
              Runs are being created in the background. This page refreshes as they arrive.
            </div>
          ) : null}
          {closed ? (
            <div
              role="status"
              className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-border bg-surface-muted px-4 py-2.5 text-[13px] text-ink"
            >
              <Lock aria-hidden="true" className="size-4 text-ink-secondary" />
              <span className="flex-1">
                Closed by {c.closed_by?.display_name ?? "someone"} on {formatDateTime(c.closed_at)}. The cycle
                is read-only.
              </span>
              {canReopen ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setDialog("reopen");
                  }}
                >
                  Reopen
                </Button>
              ) : null}
            </div>
          ) : null}

          <ProgressCard cycle={c} />

          <Tabs
            label="Cycle sections"
            value={section}
            onValueChange={setSection}
            className="mt-5"
            contentClassName="pt-4"
            items={[
              {
                value: "runs",
                label: "Runs",
                count: c.summary.total,
                content: (
                  <RunsSection
                    project={project}
                    cycle={c}
                    me={me}
                    canManage={canManage && !closed}
                    canExecute={canExecute && !closed}
                    selectedRun={runId}
                    onRun={onRun}
                    onDialog={setDialog}
                    dialog={dialog}
                  />
                ),
              },
              {
                value: "history",
                label: "History",
                content: <RecordHistory projectId={project.id} entityType="test_cycle" entityId={c.id} />,
              },
            ]}
          />
        </div>
        {runId ? (
          <RunPanel
            key={runId}
            project={project}
            cycleId={c.id}
            runId={runId}
            meId={me.user.id}
            canManage={canManage}
            canExecute={canExecute}
            onClose={() => {
              onRun(null);
            }}
            onOpenRun={onRun}
          />
        ) : null}
      </div>

      {dialog === "edit" ? (
        <EditCycleDialog
          project={project}
          cycle={c}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
      {dialog === "close" ? (
        <CloseCycleDialog
          project={project}
          cycle={c}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
      {dialog === "clone" ? (
        <CloneCycleDialog
          project={project}
          cycle={c}
          onClose={() => {
            setDialog(null);
          }}
          onOpen={(key) => {
            setDialog(null);
            openCycle(key);
          }}
        />
      ) : null}
      <ReopenDialog
        project={project}
        cycle={c}
        open={dialog === "reopen"}
        onClose={() => {
          setDialog(null);
        }}
      />
      <ArchiveDialog
        project={project}
        cycle={c}
        open={dialog === "archive"}
        onClose={() => {
          setDialog(null);
        }}
        onArchived={() => {
          setDialog(null);
          toast(`${c.key} archived`);
        }}
      />
    </div>
  );
}

/** "SPARK v2.5 · QA · build 2.5.0-rc1 · Nov 3 → Nov 10" (docs/design/CycleDetail.dc.html). */
function metaLine(c: CycleRead): string {
  const parts = [
    c.release?.name,
    c.environment.name,
    c.build ? `build ${c.build}` : null,
    c.start_date || c.due_date ? `${formatDate(c.start_date)} → ${formatDate(c.due_date)}` : null,
    c.owner ? `owner ${c.owner.display_name}` : null,
  ];
  return parts.filter(Boolean).join(" · ");
}

function CycleActions({
  project,
  cycle: c,
  canManage,
  canReopen,
  canExecute,
  onDialog,
}: {
  project: Project;
  cycle: CycleRead;
  canManage: boolean;
  canReopen: boolean;
  canExecute: boolean;
  onDialog: (d: Dialog) => void;
}) {
  const toast = useToast();
  const navigate = useNavigate();
  const start = useStartCycle(project.id, c.id);
  const sync = useSyncFromPlan(project.id, c.id);
  const sort = useSortRuns(project.id, c.id);
  const updateAll = useUpdateNotRunVersions(project.id, c.id);
  const closed = c.status === "closed";
  const onError = (e: unknown) => {
    toast(errorMessage(e), "error");
  };
  /** "Start testing" (docs/07 §5.8): my first open run, or the first open run when none is mine. */
  const startTesting = async () => {
    const open = { status: "not_run,in_progress", sort: "position", page: 1, page_size: 1 };
    const pick = async (extra: Record<string, string>) =>
      (
        await api.GET("/api/v1/cycles/{cycle_id}/runs", {
          params: { path: { cycle_id: c.id }, query: { ...open, ...extra } },
        })
      ).data?.items[0]?.id;
    try {
      const runId = (await pick({ assignee_id: "me" })) ?? (await pick({}));
      if (!runId) {
        toast("Every run of this cycle has a result");
        return;
      }
      void navigate({
        to: "/p/$projectKey/cycles/$cycleKey/run/$runId",
        params: { projectKey: project.key, cycleKey: c.key, runId },
      });
    } catch (e) {
      onError(e);
    }
  };
  const testing =
    canExecute && !closed && c.summary.total > 0 ? (
      <Button onClick={() => void startTesting()}>
        <Play aria-hidden="true" className="size-4" />
        Start testing
      </Button>
    ) : null;
  if (!canManage && !(closed && canReopen)) return testing;
  return (
    <>
      {canManage && !closed ? (
        <>
          <Button
            variant="secondary"
            onClick={() => {
              onDialog("add");
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            Add cases
          </Button>
          <Menu>
            <MenuTrigger asChild>
              <Button variant="secondary">
                Assign
                <ChevronDown aria-hidden="true" className="size-4" />
              </Button>
            </MenuTrigger>
            <MenuContent align="end">
              <MenuItem
                onSelect={() => {
                  onDialog("assign-folder");
                }}
              >
                Assign a folder…
              </MenuItem>
              <MenuItem disabled>Select runs below to assign them</MenuItem>
            </MenuContent>
          </Menu>
        </>
      ) : null}
      {canManage && c.status === "planned" ? (
        <Button
          disabled={start.isPending}
          onClick={() => {
            start.mutate(undefined, {
              onSuccess: () => {
                toast(`${c.key} started`);
              },
              onError,
            });
          }}
        >
          <Play aria-hidden="true" className="size-4" />
          Start cycle
        </Button>
      ) : null}
      {closed && canReopen ? (
        <Button
          variant="secondary"
          onClick={() => {
            onDialog("reopen");
          }}
        >
          Reopen
        </Button>
      ) : null}
      {canManage ? (
        <Menu>
          <MenuTrigger asChild>
            <Button variant="secondary" size="icon" aria-label="More cycle actions">
              <MoreHorizontal aria-hidden="true" className="size-4" />
            </Button>
          </MenuTrigger>
          <MenuContent align="end">
            {!closed ? (
              <MenuItem
                onSelect={() => {
                  onDialog("edit");
                }}
              >
                Edit details
              </MenuItem>
            ) : null}
            {c.status === "active" ? (
              <MenuItem
                onSelect={() => {
                  onDialog("close");
                }}
              >
                Close cycle
              </MenuItem>
            ) : null}
            <MenuItem
              onSelect={() => {
                onDialog("clone");
              }}
            >
              Clone cycle
            </MenuItem>
            {!closed ? (
              <>
                <MenuSeparator />
                {c.plan ? (
                  <MenuItem
                    onSelect={() => {
                      sync.mutate(undefined, {
                        onSuccess: (r) => {
                          toast(
                            r.added
                              ? `Added ${r.added} new ${r.added === 1 ? "case" : "cases"} from ${c.plan?.key ?? "the plan"}`
                              : "Already in sync with the plan",
                          );
                        },
                        onError,
                      });
                    }}
                  >
                    Sync from plan
                  </MenuItem>
                ) : null}
                <MenuItem
                  onSelect={() => {
                    updateAll.mutate(undefined, {
                      onSuccess: (r) => {
                        toast(
                          r.count
                            ? `Updated ${r.count} not-run ${r.count === 1 ? "run" : "runs"} to the latest version`
                            : "Every not-run run is on its latest version",
                        );
                      },
                      onError,
                    });
                  }}
                >
                  Update not-run runs to latest
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    sort.mutate("folder", {
                      onSuccess: () => {
                        toast("Runs sorted by folder");
                      },
                      onError,
                    });
                  }}
                >
                  Sort runs by folder
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    sort.mutate("priority", {
                      onSuccess: () => {
                        toast("Runs sorted by priority");
                      },
                      onError,
                    });
                  }}
                >
                  Sort runs by priority
                </MenuItem>
              </>
            ) : null}
            {closed && !c.archived ? (
              <>
                <MenuSeparator />
                <MenuItem
                  danger
                  onSelect={() => {
                    onDialog("archive");
                  }}
                >
                  Archive cycle
                </MenuItem>
              </>
            ) : null}
          </MenuContent>
        </Menu>
      ) : null}
      {testing}
    </>
  );
}

/** Progress card (docs/07 §5.8): bar, executed and pass rates with counts, legend, retest flag. */
function ProgressCard({ cycle: c }: { cycle: CycleRead }) {
  const s = c.summary;
  return (
    <Card>
      <div className="grid gap-3">
        <ProgressBar counts={s} className="h-2.5" />
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 text-[13.5px]">
          <span className="tabular text-ink">
            <span className="font-semibold">Executed</span> {formatRate(s.execution_progress)}
          </span>
          <span className="tabular text-ink">
            <span className="font-semibold">Passed</span> {formatRate(s.pass_rate)}
          </span>
        </div>
        <ul aria-label="Runs by status" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px]">
          {LEGEND.map((k) => (
            <li key={k} className="flex items-center gap-1.5">
              <StatusBadge kind="execution" status={k} compact />
              <span className="tabular text-ink">{s[k].toLocaleString()}</span>
            </li>
          ))}
          <li className="tabular text-ink-secondary">(N/A {s.not_applicable.toLocaleString()})</li>
          <li className="flex-1" />
          {s.needs_retest > 0 ? (
            <li className="flex items-center gap-1.5 text-[var(--status-retest-fg)]">
              <AlertTriangle aria-hidden="true" className="size-4" />
              {s.needs_retest.toLocaleString()} need retest
            </li>
          ) : null}
          {c.superseded_runs > 0 ? (
            <li className="text-ink-secondary">{c.superseded_runs.toLocaleString()} superseded</li>
          ) : null}
        </ul>
      </div>
    </Card>
  );
}

type View = "all" | "assignee" | "folder";

function RunsSection({
  project,
  cycle: c,
  me,
  canManage,
  canExecute,
  selectedRun,
  onRun,
  onDialog,
  dialog,
}: {
  project: Project;
  cycle: CycleRead;
  me: Me;
  canManage: boolean;
  canExecute: boolean;
  selectedRun: string | null;
  onRun: (id: string | null) => void;
  onDialog: (d: Dialog) => void;
  dialog: Dialog;
}) {
  const toast = useToast();
  const members = useMembers(project.id);
  const executors = useExecutors(members.data ?? []);
  const folders = useFolders(project.id, false);
  const assign = useAssignRuns(project.id, c.id);
  const addRuns = useAddRuns(project.id, c.id);
  const remove = useRemoveRuns(project.id, c.id);
  const update = useRunAction(project.id, c.id, "update-version");
  const claim = useRunAction(project.id, c.id, "claim");
  const [view, setView] = useState<View>("all");
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([]);
  const views = useSavedViews(project.id, "test_run", { filters, setFilters, sorting, setSorting });
  const [needsRetest, setNeedsRetest] = useState(false);
  const [showSuperseded, setShowSuperseded] = useState(false);

  const filter: Record<string, string> = {};
  for (const [col, param] of [
    ["status", "status"],
    ["assignee", "assignee_id"],
    ["folder", "folder_id"],
    ["priority", "priority"],
    ["title", "q"],
  ] as const) {
    const v = filterValue(filters, col);
    if (v) filter[param] = v;
  }
  if (needsRetest) filter.needs_retest = "true";
  const where = {
    ...filter,
    ...(showSuperseded ? { include_superseded: true } : {}),
    sort: sortParam(sorting, { case: "key" }) ?? "position",
  };
  // A new filter, toggle, sort or saved view starts on page 1.
  const [pagination, setPagination] = usePaging(JSON.stringify(where));
  const query: RunQuery = { ...where, page: pagination.pageIndex + 1, page_size: pagination.pageSize };
  const runs = useRuns(c.id, query, c.runs_pending);
  const items = runs.data?.items ?? [];
  // Bugs column (docs/07 §5.8): distinct references linked to any attempt of each run.
  const tracker = trackerOf(project);
  const bugLinks = useCycleBugLinks(c.id).data ?? [];
  const bugsByRun = new Map<string, BugLink[]>();
  for (const l of bugLinks) {
    if (!l.run_id) continue;
    const list = bugsByRun.get(l.run_id) ?? [];
    if (!list.some((x) => x.reference.toUpperCase() === l.reference.toUpperCase())) list.push(l);
    bugsByRun.set(l.run_id, list);
  }
  const total = runs.data?.total ?? 0;

  // Selection belongs to one filter, like the repository list (docs/07 §4.1).
  const filterKey = JSON.stringify(filter);
  const [sel, setSel] = useState<{ key: string; ids: Set<string>; all: boolean }>({
    key: filterKey,
    ids: new Set(),
    all: false,
  });
  const current = sel.key === filterKey ? sel : { key: filterKey, ids: new Set<string>(), all: false };
  const checked = current.ids;
  const count = current.all ? total : checked.size;
  const setChecked = (fn: (s: Set<string>) => Set<string>) => {
    setSel({ key: filterKey, ids: fn(checked), all: false });
  };
  const clearSelection = () => {
    setSel({ key: filterKey, ids: new Set(), all: false });
  };
  const toggle = (id: string) => {
    setChecked((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const selectable = items.filter((r) => !r.superseded);
  const allOnPage = selectable.length > 0 && selectable.every((r) => checked.has(r.id));
  const onError = (e: unknown) => {
    toast(errorMessage(e), "error");
  };
  const target = current.all ? { filter } : { run_ids: [...checked] };

  const doAssign = (
    assigneeId: string | null,
    body: { run_ids?: string[]; filter?: Record<string, string> },
  ) => {
    assign.mutate(
      { ...body, assignee_id: assigneeId },
      {
        onSuccess: (r) => {
          const who = assigneeId
            ? (executors.find((m) => m.user.id === assigneeId)?.user.display_name ?? "the tester")
            : "the pool";
          toast(`Assigned ${r.count} ${r.count === 1 ? "run" : "runs"} to ${who}`);
          onDialog(null);
          clearSelection();
        },
        onError,
      },
    );
  };

  const folderList = folders.data ?? [];
  const columns: ColumnDef<RunListItem>[] = [
    ...(canManage
      ? ([
          {
            id: "select",
            header: () => (
              <input
                type="checkbox"
                aria-label="Select page"
                checked={allOnPage}
                onChange={(e) => {
                  setChecked((s) => {
                    const next = new Set(s);
                    for (const r of selectable) {
                      if (e.target.checked) next.add(r.id);
                      else next.delete(r.id);
                    }
                    return next;
                  });
                }}
              />
            ),
            enableSorting: false,
            cell: (x) =>
              x.row.original.superseded ? null : (
                <input
                  type="checkbox"
                  aria-label={`Select ${x.row.original.test_case.key}`}
                  checked={current.all || checked.has(x.row.original.id)}
                  onChange={() => {
                    toggle(x.row.original.id);
                  }}
                />
              ),
            meta: { width: "w-10", fixed: true, label: "Select" },
          },
        ] satisfies ColumnDef<RunListItem>[])
      : []),
    {
      id: "position",
      header: "#",
      accessorKey: "position",
      cell: (x) => <span className="tabular text-ink-muted">{x.row.original.position}</span>,
      meta: { width: "w-14", align: "right", fixed: true },
    },
    {
      id: "case",
      header: "Case",
      accessorFn: (r) => r.test_case.key,
      cell: (x) => (
        <span className="whitespace-nowrap font-mono text-[12.5px] font-medium">
          {x.row.original.test_case.key}
        </span>
      ),
      meta: { width: "w-32", fixed: true },
    },
    {
      id: "title",
      header: "Title",
      enableSorting: false,
      accessorFn: (r) => r.test_case.title,
      cell: (x) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate" title={x.row.original.test_case.title}>
            {x.row.original.test_case.title}
          </span>
          {x.row.original.superseded ? (
            <span className="shrink-0 text-xs text-ink-muted">superseded</span>
          ) : null}
        </span>
      ),
      meta: {
        filter: { kind: "text", placeholder: "Key or text" },
        fixed: true,
        cellClassName: "max-w-0 min-w-[200px]",
      },
    },
    {
      id: "folder",
      header: "Folder",
      enableSorting: false,
      accessorFn: (r) => r.test_case.folder_name,
      cell: (x) => (
        <span className="whitespace-nowrap text-ink-secondary">{x.row.original.test_case.folder_name}</span>
      ),
      meta: {
        width: "w-40",
        filter: { kind: "select", options: folderList.map((f) => ({ value: f.id, label: f.name })) },
      },
    },
    {
      id: "priority",
      header: "Priority",
      accessorFn: (r) => r.test_case.priority,
      cell: (x) => <PriorityIcon priority={x.row.original.test_case.priority} compact />,
      meta: {
        width: "w-24",
        filter: {
          kind: "select",
          options: Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ value, label })),
        },
      },
    },
    {
      id: "version",
      header: "Ver",
      enableSorting: false,
      cell: (x) => {
        const r = x.row.original;
        return r.newer_version_no ? (
          <span
            className="whitespace-nowrap font-medium text-link"
            title={`v${r.newer_version_no} available. Open the run to update or replace it.`}
          >
            v{r.pinned_version_no}↑<span className="sr-only"> (v{r.newer_version_no} available)</span>
          </span>
        ) : (
          <span className="text-ink-secondary">v{r.pinned_version_no}</span>
        );
      },
      meta: { width: "w-16" },
    },
    {
      id: "assignee",
      header: "Assignee",
      enableSorting: false,
      accessorFn: (r) => r.assignee?.display_name ?? "",
      cell: (x) => {
        const r = x.row.original;
        if (r.assignee) return <span className="whitespace-nowrap">{r.assignee.display_name}</span>;
        return (
          <span className="flex items-center gap-2 whitespace-nowrap text-ink-secondary">
            — pool —
            {canExecute && !r.superseded ? (
              <Button
                variant="ghost"
                size="xs"
                aria-label={`Claim ${r.test_case.key}`}
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
          </span>
        );
      },
      meta: {
        width: "w-44",
        filter: {
          kind: "select",
          options: [
            { value: "me", label: "Me" },
            { value: "none", label: "Unassigned" },
            ...(members.data ?? [])
              .filter((m) => m.user.id !== me.user.id)
              .map((m) => ({ value: m.user.id, label: m.user.display_name })),
          ],
        },
      },
    },
    {
      id: "status",
      header: "Status",
      accessorKey: "status",
      cell: (x) => (
        <span className="flex items-center gap-1.5">
          <StatusBadge kind="execution" status={x.row.original.status} />
          {x.row.original.needs_retest ? (
            <StatusBadge kind="execution" status="needs_retest" compact />
          ) : null}
        </span>
      ),
      meta: { width: "w-40", filter: { kind: "select", options: RUN_STATUS_OPTIONS } },
    },
    {
      id: "bugs",
      header: "Bugs",
      enableSorting: false,
      cell: (x) => (
        <BugChips
          links={bugsByRun.get(x.row.original.id) ?? []}
          project={project}
          tracker={tracker}
          canRetest={canManage}
          compact
        />
      ),
      meta: { width: "w-40" },
    },
  ];

  const onRowClick = (e: MouseEvent, r: RunListItem) => {
    if ((e.target as HTMLElement).closest("input,button,a")) return;
    onRun(r.id);
  };
  const onRowKey = (e: KeyboardEvent<HTMLTableRowElement>, r: RunListItem) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter") onRun(r.id);
    else if (e.key === "x" && canManage && !r.superseded) toggle(r.id);
    else return;
    e.preventDefault();
  };

  const groups: GroupProgress[] = view === "assignee" ? c.progress_by_assignee : c.progress_by_folder;
  const viewToggle = (
    <div
      role="group"
      aria-label="Group runs"
      className="inline-flex rounded-control border border-border p-0.5"
    >
      {(
        [
          ["all", "All runs"],
          ["assignee", "By assignee"],
          ["folder", "By folder"],
        ] as const
      ).map(([v, label]) => (
        <button
          key={v}
          type="button"
          aria-pressed={view === v}
          onClick={() => {
            setView(v);
          }}
          className="h-7 rounded-[5px] px-2.5 text-[12.5px] font-medium text-ink-secondary aria-pressed:bg-accent-tint aria-pressed:text-accent-ink"
        >
          {label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="grid gap-3">
      {viewToggle}
      {view !== "all" ? (
        <GroupTable
          label={view === "assignee" ? "Progress by assignee" : "Progress by folder"}
          groups={groups}
          onPick={(g) => {
            const col = view === "assignee" ? "assignee" : "folder";
            const value = view === "assignee" ? (g.id ?? "none") : g.id;
            setFilters(value ? [{ id: col, value }] : []);
            setPagination((p) => ({ ...p, pageIndex: 0 }));
            setView("all");
          }}
        />
      ) : (
        <DataTable
          label="Runs"
          columns={columns}
          data={items}
          getRowId={(r) => r.id}
          loading={runs.isPending}
          error={runs.error}
          onRetry={() => void runs.refetch()}
          noun={["run", "runs"]}
          initialPageSize={50}
          emptyText={
            c.summary.total === 0 ? "No runs yet. Add cases to this cycle." : "No runs match these filters."
          }
          toolbar={
            <>
              <SavedViewsMenu views={views} canShare={canManage} />
              <Checkbox
                label="Needs retest"
                checked={needsRetest}
                onChange={(e) => {
                  setNeedsRetest(e.target.checked);
                }}
              />
              {c.superseded_runs > 0 ? (
                <Checkbox
                  label={`Show ${c.superseded_runs} superseded`}
                  checked={showSuperseded}
                  onChange={(e) => {
                    setShowSuperseded(e.target.checked);
                  }}
                />
              ) : null}
            </>
          }
          banner={
            count > 0 && canManage ? (
              <div
                role="region"
                aria-label="Bulk actions"
                className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-accent-border bg-accent-tint px-4 py-2 text-[13px]"
              >
                <span className="tabular font-semibold text-accent-ink">
                  {count.toLocaleString()} selected
                </span>
                {!current.all && total > checked.size ? (
                  <Button
                    variant="link"
                    size="xs"
                    onClick={() => {
                      setSel({ key: filterKey, ids: checked, all: true });
                    }}
                  >
                    Select all {total.toLocaleString()} matching
                  </Button>
                ) : null}
                <Button variant="link" size="xs" onClick={clearSelection}>
                  Clear
                </Button>
                <span className="flex-1" />
                <Button
                  variant="tint"
                  size="xs"
                  onClick={() => {
                    onDialog("assign-selected");
                  }}
                >
                  Assign
                </Button>
                <Button
                  variant="tint"
                  size="xs"
                  disabled={assign.isPending}
                  onClick={() => {
                    doAssign(null, target);
                  }}
                >
                  Unassign
                </Button>
                <Button
                  variant="tint"
                  size="xs"
                  disabled={current.all || update.isPending}
                  title={current.all ? "Select runs on this page to update them" : undefined}
                  onClick={() => {
                    const ids = items.filter((r) => checked.has(r.id) && r.newer_version_no).map((r) => r.id);
                    if (ids.length === 0) {
                      toast("None of the selected runs has a newer version", "error");
                      return;
                    }
                    void Promise.allSettled(ids.map((id) => update.mutateAsync(id))).then((res) => {
                      const ok = res.filter((x) => x.status === "fulfilled").length;
                      toast(
                        `Updated ${ok} of ${ids.length} ${ids.length === 1 ? "run" : "runs"}${
                          ok < ids.length ? "; runs with results need Replace (open the run)" : ""
                        }`,
                        ok < ids.length ? "error" : "ok",
                      );
                      clearSelection();
                    });
                  }}
                >
                  Update to latest
                </Button>
                <Button
                  variant="tint"
                  size="xs"
                  disabled={current.all}
                  title={current.all ? "Select runs on this page to remove them" : undefined}
                  onClick={() => {
                    onDialog("remove");
                  }}
                >
                  Remove
                </Button>
              </div>
            ) : undefined
          }
          rowProps={(r) => ({
            tabIndex: 0,
            selected: r.id === selectedRun,
            "aria-selected": r.id === selectedRun,
            className: `cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none ${
              r.superseded ? "text-ink-muted" : ""
            }`,
            onClick: (e) => {
              onRowClick(e, r);
            },
            onKeyDown: (e) => {
              onRowKey(e, r);
            },
          })}
          server={{
            total,
            pagination,
            onPaginationChange: setPagination,
            sorting,
            onSortingChange: setSorting,
            filters,
            onFiltersChange: setFilters,
          }}
        />
      )}

      {dialog === "add" ? (
        <AddCasesDialog
          title={`Add cases to ${c.key}`}
          projectId={project.id}
          noun="runs"
          pending={addRuns.isPending}
          error={addRuns.error}
          onAdd={(s) => addRuns.mutateAsync(s)}
          onClose={() => {
            addRuns.reset();
            onDialog(null);
          }}
        />
      ) : null}
      {dialog === "assign-folder" || dialog === "assign-selected" ? (
        <AssignDialog
          title={
            dialog === "assign-folder"
              ? `Assign a folder in ${c.key}`
              : `Assign ${count.toLocaleString()} ${count === 1 ? "run" : "runs"}`
          }
          executors={executors}
          folders={folderList}
          byFolder={dialog === "assign-folder"}
          pending={assign.isPending}
          error={assign.error}
          onAssign={(assigneeId, folderId) => {
            doAssign(assigneeId, folderId ? { filter: { folder_id: folderId } } : target);
          }}
          onClose={() => {
            assign.reset();
            onDialog(null);
          }}
        />
      ) : null}
      <ConfirmDialog
        open={dialog === "remove"}
        onOpenChange={(o) => {
          if (!o) {
            remove.reset();
            onDialog(null);
          }
        }}
        title={`Remove ${checked.size} ${checked.size === 1 ? "run" : "runs"} from ${c.key}?`}
        description="Only runs that are not run and have no attempts can be removed. Runs with results stay."
        confirmLabel="Remove"
        destructive
        pending={remove.isPending}
        error={remove.error}
        onConfirm={() => {
          remove.mutate([...checked], {
            onSuccess: (r) => {
              toast(`Removed ${r.count} ${r.count === 1 ? "run" : "runs"}`);
              clearSelection();
              onDialog(null);
            },
          });
        }}
      />
    </div>
  );
}

function GroupTable({
  label,
  groups,
  onPick,
}: {
  label: string;
  groups: GroupProgress[];
  onPick: (g: GroupProgress) => void;
}) {
  const columns: ColumnDef<GroupProgress>[] = [
    {
      id: "name",
      header: label.endsWith("assignee") ? "Assignee" : "Folder",
      accessorKey: "name",
      cell: (x) => (
        <span className={x.row.original.id ? "" : "text-ink-secondary"}>
          {x.row.original.id ? x.row.original.name : "— pool —"}
        </span>
      ),
    },
    {
      id: "bar",
      header: "Progress",
      enableSorting: false,
      cell: (x) => <ProgressBar counts={x.row.original.summary} />,
      meta: { width: "w-56" },
    },
    {
      id: "executed",
      header: "Executed",
      enableSorting: false,
      cell: (x) => (
        <span className="tabular whitespace-nowrap">
          {formatRate(x.row.original.summary.execution_progress)}
        </span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "passed",
      header: "Passed",
      enableSorting: false,
      cell: (x) => (
        <span className="tabular whitespace-nowrap">{formatRate(x.row.original.summary.pass_rate)}</span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "total",
      header: "Runs",
      enableSorting: false,
      cell: (x) => <span className="tabular">{x.row.original.summary.total.toLocaleString()}</span>,
      meta: { width: "w-20", align: "right" },
    },
  ];
  return (
    <DataTable
      label={label}
      columns={columns}
      data={groups}
      getRowId={(g) => g.id ?? "none"}
      hideFilters
      noun={["group", "groups"]}
      emptyText="No runs yet."
      rowProps={(g) => ({
        tabIndex: 0,
        title: "Show these runs",
        className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
        onClick: () => {
          onPick(g);
        },
        onKeyDown: (e) => {
          if (e.key === "Enter") onPick(g);
        },
      })}
    />
  );
}

function ReopenDialog({
  project,
  cycle,
  open,
  onClose,
}: {
  project: Project;
  cycle: CycleRead;
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const reopen = useReopenCycle(project.id, cycle.id);
  return (
    <PromptDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          reopen.reset();
          onClose();
        }
      }}
      title={`Reopen ${cycle.key}`}
      label="Reason"
      submitLabel="Reopen"
      multiline
      pending={reopen.isPending}
      error={reopen.error}
      onSubmit={(reason) => {
        reopen.mutate(reason, {
          onSuccess: () => {
            toast(`${cycle.key} reopened`);
            onClose();
          },
        });
      }}
    />
  );
}

function ArchiveDialog({
  project,
  cycle,
  open,
  onClose,
  onArchived,
}: {
  project: Project;
  cycle: CycleRead;
  open: boolean;
  onClose: () => void;
  onArchived: () => void;
}) {
  const archive = useArchiveCycle(project.id, cycle.id);
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          archive.reset();
          onClose();
        }
      }}
      title={`Archive ${cycle.key}?`}
      description="Archived cycles are hidden from the default list; their results stay in reports."
      confirmLabel="Archive"
      destructive
      pending={archive.isPending}
      error={archive.error}
      onConfirm={() => {
        archive.mutate(undefined, { onSuccess: onArchived });
      }}
    />
  );
}
