import { useNavigate } from "@tanstack/react-router";
import { Archive, Copy } from "lucide-react";
import { useState } from "react";

import type { Project } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { ConfirmDialog } from "@/components/common/dialogs";
import { Card, ErrorState, Facts, Page, Skeleton, useToast } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import type { ColumnDef } from "@tanstack/react-table";

import { useArchivePlan, useClonePlan, usePlan, usePlanCases, type PlanCaseItem } from "./api";
import { PLAN_STATUS_LABEL, PLAN_TYPE_LABEL } from "./labels";

/** Plan detail with its case list and per-cycle results (US-074). */
export function PlanDetail({
  project,
  planId,
  canManage,
}: {
  project: Project;
  planId: string | undefined;
  canManage: boolean;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const plan = usePlan(planId);
  const cases = usePlanCases(planId);
  const archive = useArchivePlan(project.id);
  const clone = useClonePlan(project.id);
  const [confirmArchive, setConfirmArchive] = useState(false);

  if (plan.isPending)
    return (
      <div className="p-6">
        <Skeleton />
      </div>
    );
  if (plan.isError)
    return (
      <div className="p-6">
        <ErrorState error={plan.error} />
      </div>
    );

  const p = plan.data;

  const columns: ColumnDef<PlanCaseItem>[] = [
    {
      id: "key",
      header: "Case",
      accessorKey: "key",
      cell: (c) => <span className="font-mono text-[12.5px] text-ink-secondary">{c.row.original.key}</span>,
      meta: { width: "w-36" },
    },
    { id: "title", header: "Title", accessorKey: "title" },
    {
      id: "results",
      header: "Latest result per cycle",
      cell: (c) => {
        const results = c.row.original.results;
        if (results.length === 0)
          return <span className="text-[12.5px] text-ink-faint">Not in any cycle</span>;
        return (
          <div className="flex flex-wrap gap-1.5">
            {results.map((r) => (
              <span key={r.cycle_id} className="inline-flex items-center gap-1">
                <span className="font-mono text-[11.5px] text-ink-faint">{r.cycle_key}</span>
                <StatusBadge kind="execution" status={r.status} compact />
              </span>
            ))}
          </div>
        );
      },
    },
  ];

  return (
    <Page
      title={p.name}
      eyebrow={<span className="font-mono">{p.key}</span>}
      width="full"
      actions={
        canManage ? (
          <>
            <Button
              variant="secondary"
              onClick={() => {
                void clone.mutateAsync(p.id).then((created) => {
                  toast("Plan cloned");
                  void navigate({
                    to: "/p/$projectKey/plans/$planKey",
                    params: { projectKey: project.key, planKey: created.key },
                  });
                });
              }}
              disabled={clone.isPending}
            >
              <Copy aria-hidden="true" className="size-4" />
              Clone
            </Button>
            {!p.archived ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setConfirmArchive(true);
                }}
              >
                <Archive aria-hidden="true" className="size-4" />
                Archive
              </Button>
            ) : null}
          </>
        ) : undefined
      }
    >
      <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card title="Details">
          <Facts
            items={[
              ["Type", PLAN_TYPE_LABEL[p.type]],
              ["Status", PLAN_STATUS_LABEL[p.status]],
              ["Cases", p.case_count],
              ["Requirements", p.requirement_count],
              ["Environments", p.environment_ids.length],
              ...(p.start_date ? ([["Start", p.start_date]] as [string, string][]) : []),
              ...(p.end_date ? ([["End", p.end_date]] as [string, string][]) : []),
            ]}
          />
          {p.objectives ? (
            <div className="mt-4 border-t border-border pt-3 text-[13px]">
              <p className="mb-1 font-medium text-ink-secondary">Objectives</p>
              <p className="whitespace-pre-wrap text-ink">{p.objectives}</p>
            </div>
          ) : null}
        </Card>
        <DataTable
          label="Plan cases"
          columns={columns}
          data={cases.data?.items ?? []}
          loading={cases.isPending}
          error={cases.error}
          noun={["case", "cases"]}
          getRowId={(r) => r.case_id}
          emptyText="No cases in this plan yet. Add cases from the repository."
        />
      </div>
      <ConfirmDialog
        open={confirmArchive}
        onOpenChange={setConfirmArchive}
        title="Archive this plan?"
        description="Archived plans are hidden from the default list and become read-only. Existing cycles are unaffected."
        confirmLabel="Archive"
        pending={archive.isPending}
        onConfirm={() => {
          void archive.mutateAsync(p.id).then(() => {
            toast("Plan archived");
            setConfirmArchive(false);
          });
        }}
      />
    </Page>
  );
}
