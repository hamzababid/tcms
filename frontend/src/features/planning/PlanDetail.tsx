import { useNavigate } from "@tanstack/react-router";
import type { ColumnDef, PaginationState } from "@tanstack/react-table";
import { Archive, Copy, MoreHorizontal, Pencil, Plus } from "lucide-react";
import { useState, type ReactNode } from "react";

import { useEnvironments, useMembers, useReleases, type Project } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import {
  Card,
  EmptyState,
  ErrorState,
  Facts,
  Page,
  Skeleton,
  errorMessage,
  useToast,
} from "@/components/common/feedback";
import { MarkdownView } from "@/components/common/Markdown";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Tabs } from "@/components/ui/tabs";
import { CreateCycleDialog } from "@/features/execution/CreateCycleDialog";
import { nextCycleName } from "@/features/execution/labels";
import { RecordHistory } from "@/features/projects/RecordHistory";
import { usePlanReadiness } from "@/features/reporting/api";
import { ReadinessRules, ReadyBadge } from "@/features/reporting/readiness";
import { PlanRequirements } from "@/features/requirements/components";
import { AddCasesDialog } from "@/features/testdesign/CaseSelector";
import { formatDate, formatPercent } from "@/lib/format";

import {
  useAddPlanCases,
  useArchivePlan,
  useClonePlan,
  usePatchPlan,
  usePlan,
  usePlanCases,
  useRemovePlanCases,
  type ExitRule,
  type PlanCaseItem,
  type PlanCycle,
  type PlanRead,
  type Risk,
} from "./api";
import { PlanForm } from "./PlanForm";
import { PLAN_TYPE_LABEL, RISK_IMPACTS, STATUS_ACTION_LABEL, ruleText } from "./labels";

/** Plan detail: Overview, Cases, Cycles, History (docs/07 §5.7; US-070…074). */
export function PlanDetail({
  project,
  planId,
  canManage,
  canManageCycles,
  canLinkRequirements,
}: {
  project: Project;
  planId: string;
  canManage: boolean;
  canManageCycles: boolean;
  canLinkRequirements: boolean;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const plan = usePlan(planId);
  const setStatus = usePatchPlan(project.id, planId);
  const archive = useArchivePlan(project.id, planId);
  const clone = useClonePlan(project.id, planId);
  const [tab, setTab] = useState("overview");
  const [editing, setEditing] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [creatingCycle, setCreatingCycle] = useState(false);

  if (plan.isPending)
    return (
      <div className="p-6">
        <Skeleton rows={6} />
      </div>
    );
  if (plan.isError)
    return (
      <div className="p-6">
        <ErrorState error={plan.error} onRetry={() => void plan.refetch()} />
      </div>
    );

  const p = plan.data;
  const writable = canManage && !p.archived && project.status !== "archived";
  const cycles = p.cycles ?? [];
  const openCycle = (key: string) =>
    void navigate({
      to: "/p/$projectKey/cycles/$cycleKey",
      params: { projectKey: project.key, cycleKey: key },
    });

  return (
    <Page
      title={p.name}
      eyebrow={
        <span className="flex items-center gap-2">
          <span className="font-mono">{p.key}</span>
          <StatusBadge kind="plan" status={p.status} />
        </span>
      }
      width="full"
      actions={
        writable ? (
          <>
            {p.allowed_transitions.map((target) => (
              <Button
                key={target}
                variant={target === "active" || target === "completed" ? "primary" : "secondary"}
                disabled={setStatus.isPending}
                onClick={() => {
                  setStatus.mutate(
                    { status: target, row_version: p.row_version },
                    {
                      onSuccess: (saved) => {
                        toast(`${saved.key} is ${saved.status}`);
                      },
                      onError: (e) => {
                        toast(errorMessage(e), "error");
                      },
                    },
                  );
                }}
              >
                {STATUS_ACTION_LABEL[target]}
              </Button>
            ))}
            <Button
              variant="secondary"
              onClick={() => {
                setEditing(true);
              }}
            >
              <Pencil aria-hidden="true" className="size-4" />
              Edit
            </Button>
            <Menu>
              <MenuTrigger asChild>
                <Button variant="secondary" size="icon" aria-label="More plan actions">
                  <MoreHorizontal aria-hidden="true" className="size-4" />
                </Button>
              </MenuTrigger>
              <MenuContent align="end">
                <MenuItem
                  onSelect={() => {
                    setCloning(true);
                  }}
                >
                  <Copy aria-hidden="true" className="size-4" />
                  Clone plan
                </MenuItem>
                <MenuItem
                  danger
                  onSelect={() => {
                    setConfirmArchive(true);
                  }}
                >
                  <Archive aria-hidden="true" className="size-4" />
                  Archive plan
                </MenuItem>
              </MenuContent>
            </Menu>
          </>
        ) : undefined
      }
    >
      {p.archived ? (
        <div
          role="status"
          className="mb-4 rounded-card border border-border bg-surface-muted px-4 py-2.5 text-[13px] text-ink-secondary"
        >
          This plan is archived and read-only. Its cycles are unaffected.
        </div>
      ) : null}
      <Tabs
        label="Plan sections"
        value={tab}
        onValueChange={setTab}
        contentClassName="pt-5"
        items={[
          { value: "overview", label: "Overview", content: <Overview project={project} plan={p} /> },
          {
            value: "cases",
            label: "Cases",
            count: p.case_count,
            content: <PlanCases project={project} plan={p} writable={writable} />,
          },
          {
            value: "requirements",
            label: "Requirements",
            count: p.requirement_count,
            content: (
              <PlanRequirements
                project={project}
                planId={p.id}
                releaseId={p.release_id}
                canManage={writable}
                canLink={canLinkRequirements && project.status !== "archived"}
              />
            ),
          },
          {
            value: "cycles",
            label: "Cycles",
            count: cycles.length,
            content: (
              <PlanCycles
                cycles={cycles}
                onOpen={openCycle}
                onCreate={
                  canManageCycles && !p.archived && project.status !== "archived"
                    ? () => {
                        setCreatingCycle(true);
                      }
                    : null
                }
              />
            ),
          },
          {
            value: "history",
            label: "History",
            content: <RecordHistory entityType="test_plan" entityId={p.id} />,
          },
        ]}
      />

      {editing ? (
        <PlanForm
          project={project}
          plan={p}
          onClose={() => {
            setEditing(false);
          }}
          onSaved={() => {
            setEditing(false);
          }}
        />
      ) : null}
      {creatingCycle ? (
        <CreateCycleDialog
          project={project}
          defaults={{ planId: p.id, name: nextCycleName(p.name, cycles.length), releaseId: p.release_id }}
          onClose={() => {
            setCreatingCycle(false);
          }}
          onOpen={openCycle}
        />
      ) : null}
      <PromptDialog
        open={cloning}
        onOpenChange={(o) => {
          setCloning(o);
          if (!o) clone.reset();
        }}
        title={`Clone ${p.key}`}
        label="Name of the copy"
        initial={`Copy of ${p.name}`}
        submitLabel="Clone"
        pending={clone.isPending}
        error={clone.error}
        onSubmit={(name) => {
          clone.mutate(name, {
            onSuccess: (created) => {
              setCloning(false);
              toast(`Cloned as ${created.key}`);
              void navigate({
                to: "/p/$projectKey/plans/$planKey",
                params: { projectKey: project.key, planKey: created.key },
              });
            },
          });
        }}
      />
      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={(o) => {
          setConfirmArchive(o);
          if (!o) archive.reset();
        }}
        title={`Archive ${p.key}?`}
        description="Archived plans are hidden from the default list and become read-only. Existing cycles are unaffected."
        confirmLabel="Archive"
        destructive
        pending={archive.isPending}
        error={archive.error}
        onConfirm={() => {
          archive.mutate(undefined, {
            onSuccess: () => {
              toast(`${p.key} archived`);
              setConfirmArchive(false);
            },
          });
        }}
      />
    </Page>
  );
}

function Overview({ project, plan }: { project: Project; plan: PlanRead }) {
  const readiness = usePlanReadiness(plan.id);
  const environments = useEnvironments(project.id);
  const releases = useReleases(project.id);
  const members = useMembers(project.id);
  const envNames = plan.environment_ids
    .map((id) => environments.data?.find((e) => e.id === id)?.name)
    .filter(Boolean)
    .join(", ");
  const memberNames = plan.member_ids
    .map((id) => members.data?.find((m) => m.user.id === id)?.user.display_name)
    .filter(Boolean)
    .join(", ");
  const release = releases.data?.find((r) => r.id === plan.release_id)?.name;
  const rules = plan.exit_rules as unknown as ExitRule[];
  const risks = plan.risks as unknown as Risk[];
  const text: [string, string | null][] = [
    ["Objectives", plan.objectives],
    ["In scope", plan.scope_in],
    ["Out of scope", plan.scope_out],
    ["Entry criteria", plan.entry_criteria],
    ["Acceptance criteria", plan.acceptance_criteria],
  ];
  return (
    <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
      <Card title="Details">
        <Facts
          items={[
            ["Type", PLAN_TYPE_LABEL[plan.type]],
            ["Status", <StatusBadge key="s" kind="plan" status={plan.status} />],
            ["Release", release ?? "—"],
            ["Owner", plan.owner?.display_name ?? "—"],
            [
              "Dates",
              plan.start_date || plan.end_date
                ? `${formatDate(plan.start_date)} → ${formatDate(plan.end_date)}`
                : "—",
            ],
            ["Environments", envNames || "—"],
            ["QA members", memberNames || "—"],
            ["Cases", plan.case_count.toLocaleString()],
          ]}
        />
      </Card>
      <div className="grid content-start gap-5">
        <Card
          title="Exit criteria"
          description="Each rule is checked against this plan's cycles (in its release, when it has one)."
          actions={readiness.data && rules.length ? <ReadyBadge ready={readiness.data.ready} /> : null}
        >
          {rules.length === 0 && !plan.exit_criteria_notes ? (
            <p className="text-[13px] text-ink-muted">No exit criteria yet.</p>
          ) : (
            <>
              {rules.length ? (
                <div className="mb-3">
                  {readiness.data ? (
                    <ReadinessRules rules={readiness.data.rules} showPlan={false} />
                  ) : (
                    <ul className="flex flex-wrap gap-2">
                      {rules.map((r, i) => (
                        <li
                          key={i}
                          className="rounded-full border border-border bg-ground px-2.5 py-1 text-[12.5px] text-ink"
                        >
                          {ruleText(r)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}
              <MarkdownView text={plan.exit_criteria_notes} />
            </>
          )}
        </Card>
        {text.some(([, v]) => v) ? (
          <Card title="Scope and criteria">
            <div className="grid gap-4">
              {text
                .filter(([, v]) => v)
                .map(([label, v]) => (
                  <section key={label}>
                    <h3 className="mb-1 text-[13px] font-semibold text-ink-secondary">{label}</h3>
                    <MarkdownView text={v} />
                  </section>
                ))}
            </div>
          </Card>
        ) : null}
        <Card title="Risks" flush>
          {risks.length === 0 ? (
            <p className="p-5 text-[13px] text-ink-muted">No risks recorded.</p>
          ) : (
            <table className="w-full text-[13px]">
              <thead className="bg-ground text-left text-xs text-ink-secondary">
                <tr>
                  <th className="px-5 py-2 font-medium">Description</th>
                  <th className="w-28 px-3 py-2 font-medium">Impact</th>
                  <th className="px-3 py-2 font-medium">Mitigation</th>
                </tr>
              </thead>
              <tbody>
                {risks.map((r, i) => (
                  <tr key={i} className="border-t border-border align-top">
                    <td className="px-5 py-2">{r.description}</td>
                    <td className="px-3 py-2">
                      {(RISK_IMPACTS as Record<string, string | undefined>)[r.impact] ?? r.impact}
                    </td>
                    <td className="px-3 py-2 text-ink-secondary">{r.mitigation ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </div>
  );
}

function PlanCases({ project, plan, writable }: { project: Project; plan: PlanRead; writable: boolean }) {
  const toast = useToast();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const cases = usePlanCases(plan.id, { page: pagination.pageIndex + 1, page_size: pagination.pageSize });
  const addCases = useAddPlanCases(project.id, plan.id);
  const remove = useRemovePlanCases(project.id, plan.id);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const items = cases.data?.items ?? [];
  const allOnPage = items.length > 0 && items.every((c) => checked.has(c.case_id));
  const toggle = (id: string, on: boolean) => {
    setChecked((cur) => {
      const next = new Set(cur);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const columns: ColumnDef<PlanCaseItem>[] = [
    ...(writable
      ? ([
          {
            id: "select",
            header: () => (
              <input
                type="checkbox"
                aria-label="Select page"
                checked={allOnPage}
                onChange={(e) => {
                  for (const c of items) toggle(c.case_id, e.target.checked);
                }}
              />
            ),
            enableSorting: false,
            cell: (c) => (
              <input
                type="checkbox"
                aria-label={`Select ${c.row.original.key}`}
                checked={checked.has(c.row.original.case_id)}
                onChange={(e) => {
                  toggle(c.row.original.case_id, e.target.checked);
                }}
              />
            ),
            meta: { width: "w-10", fixed: true, label: "Select" },
          },
        ] satisfies ColumnDef<PlanCaseItem>[])
      : []),
    {
      id: "key",
      header: "Case",
      accessorKey: "key",
      enableSorting: false,
      cell: (c) => (
        <a
          href={`/p/${project.key}/cases/${c.row.original.key}`}
          className="whitespace-nowrap font-mono text-[12.5px] font-medium text-link hover:underline"
        >
          {c.row.original.key}
        </a>
      ),
      meta: { width: "w-32", fixed: true },
    },
    {
      id: "title",
      header: "Title",
      accessorKey: "title",
      enableSorting: false,
      cell: (c) => (
        <span className="block truncate" title={c.row.original.title}>
          {c.row.original.title}
        </span>
      ),
      meta: { fixed: true, cellClassName: "max-w-0 min-w-[200px]" },
    },
    {
      id: "priority",
      header: "Priority",
      accessorKey: "priority",
      enableSorting: false,
      cell: (c) => <PriorityIcon priority={c.row.original.priority} />,
      meta: { width: "w-28" },
    },
    {
      id: "status",
      header: "Case status",
      accessorKey: "status",
      enableSorting: false,
      cell: (c) => <StatusBadge kind="case" status={c.row.original.status} />,
      meta: { width: "w-36" },
    },
    {
      id: "results",
      header: "Result per cycle",
      enableSorting: false,
      cell: (c) => {
        const results = c.row.original.results;
        if (results.length === 0) return <span className="text-[12.5px] text-ink-muted">Not in a cycle</span>;
        return (
          <span className="flex flex-wrap gap-1.5">
            {results.map((r) => (
              <span key={r.cycle_id} className="inline-flex items-center gap-1">
                <span className="font-mono text-[11.5px] text-ink-secondary">{r.cycle_key}</span>
                <StatusBadge kind="execution" status={r.status} compact />
              </span>
            ))}
          </span>
        );
      },
      meta: { width: "w-64" },
    },
  ];

  return (
    <>
      <DataTable
        label="Plan cases"
        columns={columns}
        data={items}
        getRowId={(r) => r.case_id}
        loading={cases.isPending}
        error={cases.error}
        onRetry={() => void cases.refetch()}
        noun={["case", "cases"]}
        hideFilters
        emptyText="No cases on this page."
        empty={
          <EmptyState
            text="No cases in this plan yet. Add them by folder, tag or search."
            {...(writable
              ? {
                  action: (
                    <Button
                      size="sm"
                      onClick={() => {
                        setAdding(true);
                      }}
                    >
                      Add cases
                    </Button>
                  ),
                }
              : {})}
          />
        }
        toolbar={
          writable ? (
            <Button
              size="sm"
              onClick={() => {
                setAdding(true);
              }}
            >
              <Plus aria-hidden="true" className="size-4" />
              Add cases
            </Button>
          ) : undefined
        }
        banner={
          checked.size > 0 ? (
            <div
              role="region"
              aria-label="Bulk actions"
              className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-accent-border bg-accent-tint px-4 py-2 text-[13px]"
            >
              <span className="tabular font-semibold text-accent-ink">{checked.size} selected</span>
              <Button
                variant="link"
                size="xs"
                onClick={() => {
                  setChecked(new Set());
                }}
              >
                Clear
              </Button>
              <span className="flex-1" />
              <Button
                variant="tint"
                size="xs"
                onClick={() => {
                  setConfirmRemove(true);
                }}
              >
                Remove from plan
              </Button>
            </div>
          ) : undefined
        }
        server={{
          total: cases.data?.total ?? 0,
          pagination,
          onPaginationChange: setPagination,
          sorting: [],
          onSortingChange: () => undefined,
          filters: [],
          onFiltersChange: () => undefined,
        }}
      />
      {adding ? (
        <AddCasesDialog
          title={`Add cases to ${plan.key}`}
          projectId={project.id}
          onClose={() => {
            setAdding(false);
          }}
          pending={addCases.isPending}
          error={addCases.error}
          onAdd={(sel) => addCases.mutateAsync({ ...sel, include_subfolders: true })}
          savedViews
        />
      ) : null}
      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={(o) => {
          setConfirmRemove(o);
          if (!o) remove.reset();
        }}
        title={`Remove ${checked.size} ${checked.size === 1 ? "case" : "cases"} from ${plan.key}?`}
        description="Existing cycles keep their runs; only new cycles and syncs are affected."
        confirmLabel="Remove"
        destructive
        pending={remove.isPending}
        error={remove.error}
        onConfirm={() => {
          remove.mutate([...checked], {
            onSuccess: (r) => {
              toast(`Removed ${r.count} ${r.count === 1 ? "case" : "cases"}`);
              setChecked(new Set());
              setConfirmRemove(false);
            },
          });
        }}
      />
    </>
  );
}

function PlanCycles({
  cycles,
  onOpen,
  onCreate,
}: {
  cycles: PlanCycle[];
  onOpen: (key: string) => void;
  onCreate: (() => void) | null;
}) {
  const columns: ColumnDef<PlanCycle>[] = [
    {
      id: "key",
      header: "Key",
      accessorKey: "key",
      cell: (c) => <span className="font-mono text-[12.5px] font-medium">{c.row.original.key}</span>,
      meta: { width: "w-32" },
    },
    { id: "name", header: "Name", accessorKey: "name" },
    {
      id: "status",
      header: "Status",
      accessorKey: "status",
      cell: (c) => <StatusBadge kind="cycle" status={c.row.original.status} />,
      meta: { width: "w-32" },
    },
    {
      id: "executed",
      header: "Executed",
      enableSorting: false,
      cell: (c) => <Ratio n={c.row.original.executed} d={c.row.original.total} />,
      meta: { width: "w-44" },
    },
    {
      id: "passed",
      header: "Passed",
      enableSorting: false,
      cell: (c) => <Ratio n={c.row.original.passed} d={c.row.original.executed} />,
      meta: { width: "w-44" },
    },
  ];
  return (
    <DataTable
      label="Cycles from this plan"
      columns={columns}
      data={cycles}
      getRowId={(r) => r.id}
      noun={["cycle", "cycles"]}
      hideFilters
      toolbar={
        onCreate ? (
          <Button size="sm" onClick={onCreate}>
            <Plus aria-hidden="true" className="size-4" />
            Create cycle
          </Button>
        ) : undefined
      }
      empty={
        <EmptyState
          text="No cycles from this plan yet."
          {...(onCreate
            ? {
                action: (
                  <Button size="sm" onClick={onCreate}>
                    Create cycle
                  </Button>
                ),
              }
            : {})}
        />
      }
      rowProps={(r) => ({
        tabIndex: 0,
        className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
        onClick: () => {
          onOpen(r.key);
        },
        onKeyDown: (e) => {
          if (e.key === "Enter") onOpen(r.key);
        },
      })}
    />
  );
}

/** "180 of 205 (88%)"; "—" when nothing to divide (BR-24). */
function Ratio({ n, d }: { n: number; d: number }): ReactNode {
  return (
    <span className="tabular whitespace-nowrap text-[13px]">
      {d === 0 ? "—" : `${n.toLocaleString()} of ${d.toLocaleString()} (${formatPercent(n / d)})`}
    </span>
  );
}
