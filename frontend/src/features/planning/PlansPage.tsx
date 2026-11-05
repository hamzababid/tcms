import { useNavigate } from "@tanstack/react-router";
import { ClipboardList, Plus } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import type { Project } from "@/api/queries";
import { DataTable, sortParam, type ServerState } from "@/components/common/DataTable";
import { EmptyState, Page, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import type { ColumnDef } from "@tanstack/react-table";

import { usePlans, useCreatePlan, type PlanListItem, type PlanQuery, type PlanType } from "./api";
import { PLAN_STATUS_LABEL, PLAN_TYPES } from "./labels";

/** Test plans list (docs/07; US-070). */
export function PlansPage({ project, canManage }: { project: Project; canManage: boolean }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState<PlanQuery>({ page: 1, page_size: 25 });
  const [creating, setCreating] = useState(false);
  const plans = usePlans(project.id, query);

  const columns: ColumnDef<PlanListItem>[] = [
    {
      id: "key",
      header: "Key",
      accessorKey: "key",
      cell: (c) => <span className="font-mono text-[12.5px] text-ink-secondary">{c.row.original.key}</span>,
      meta: { width: "w-32" },
    },
    { id: "name", header: "Name", accessorKey: "name", cell: (c) => c.row.original.name },
    {
      id: "type",
      header: "Type",
      accessorFn: (r) => r.type,
      cell: (c) => <span className="capitalize">{c.row.original.type.replace(/_/g, " ")}</span>,
      meta: { width: "w-40", filter: { kind: "select", options: PLAN_TYPES } },
    },
    {
      id: "status",
      header: "Status",
      accessorFn: (r) => r.status,
      cell: (c) => PLAN_STATUS_LABEL[c.row.original.status],
      meta: { width: "w-32" },
    },
    {
      id: "case_count",
      header: "Cases",
      accessorFn: (r) => r.case_count,
      cell: (c) => <span className="tabular">{c.row.original.case_count}</span>,
      meta: { width: "w-20", align: "right" },
    },
  ];

  const server: ServerState = {
    total: plans.data?.total ?? 0,
    pagination: { pageIndex: query.page - 1, pageSize: query.page_size },
    onPaginationChange: (p) => {
      setQuery((q) => ({ ...q, page: p.pageIndex + 1, page_size: p.pageSize }));
    },
    sorting: [],
    onSortingChange: (s) => {
      setQuery((q) => ({ ...q, sort: sortParam(s, {}) ?? undefined, page: 1 }));
    },
    filters: [],
    onFiltersChange: () => undefined,
  };

  return (
    <Page
      title="Test plans"
      subtitle="Group cases into a reusable plan, then generate cycles from it."
      width="full"
      actions={
        canManage ? (
          <Button
            onClick={() => {
              setCreating(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            New plan
          </Button>
        ) : undefined
      }
    >
      <DataTable
        label="Test plans"
        columns={columns}
        data={plans.data?.items ?? []}
        server={server}
        loading={plans.isPending}
        error={plans.error}
        noun={["plan", "plans"]}
        getRowId={(r) => r.id}
        rowProps={(r) => ({
          className: "cursor-pointer",
          onClick: () =>
            void navigate({
              to: "/p/$projectKey/plans/$planKey",
              params: { projectKey: project.key, planKey: r.key },
            }),
        })}
        empty={
          <EmptyState
            icon={<ClipboardList className="size-5" />}
            text="No test plans yet. Create one to organise a test effort."
            action={
              canManage ? (
                <Button
                  size="sm"
                  onClick={() => {
                    setCreating(true);
                  }}
                >
                  New plan
                </Button>
              ) : undefined
            }
          />
        }
      />
      {creating ? (
        <CreatePlanDialog
          projectId={project.id}
          onClose={() => {
            setCreating(false);
          }}
          onCreated={(key) => {
            setCreating(false);
            void navigate({
              to: "/p/$projectKey/plans/$planKey",
              params: { projectKey: project.key, planKey: key },
            });
          }}
        />
      ) : null}
    </Page>
  );
}

function CreatePlanDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: (key: string) => void;
}) {
  const toast = useToast();
  const create = useCreatePlan(projectId);
  const [name, setName] = useState("");
  const [type, setType] = useState<PlanType>("regression");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      const plan = await create.mutateAsync({ name: name.trim(), type });
      toast("Plan created");
      onCreated(plan.key);
    } catch (e) {
      setError(
        e instanceof ApiError ? (e.errors[0]?.message ?? e.detail ?? e.code) : "Could not create plan",
      );
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="New test plan"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button form="create-plan" type="submit" disabled={create.isPending || name.trim().length < 3}>
            Create
          </Button>
        </>
      }
    >
      <form
        id="create-plan"
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field label="Name" required error={error ?? undefined}>
          {(p) => (
            <Input
              {...p}
              value={name}
              placeholder="e.g. SPARK v2.5 regression"
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Type" required>
          {(p) => (
            <Select
              {...p}
              value={type}
              onChange={(e) => {
                setType(e.target.value as PlanType);
              }}
            >
              {PLAN_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </form>
    </Dialog>
  );
}
