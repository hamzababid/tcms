import { useNavigate } from "@tanstack/react-router";
import { PlayCircle, Plus } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { useEnvironments, type Project } from "@/api/queries";
import { DataTable, type ServerState } from "@/components/common/DataTable";
import { EmptyState, Page, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import type { ColumnDef } from "@tanstack/react-table";

import { usePlans } from "@/features/planning/api";

import { useCycles, useCreateCycle, type CycleListItem, type CycleQuery } from "./api";
import { CYCLE_STATUS_LABEL, CYCLE_STATUS_OPTIONS } from "./labels";

/** Test cycles list (docs/07 §5.7; US-080). */
export function CyclesPage({ project, canManage }: { project: Project; canManage: boolean }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState<CycleQuery>({ page: 1, page_size: 25 });
  const [creating, setCreating] = useState(false);
  const cycles = useCycles(project.id, query);

  const columns: ColumnDef<CycleListItem>[] = [
    {
      id: "key",
      header: "Key",
      accessorKey: "key",
      cell: (c) => <span className="font-mono text-[12.5px] text-ink-secondary">{c.row.original.key}</span>,
      meta: { width: "w-32" },
    },
    { id: "name", header: "Name", accessorKey: "name" },
    {
      id: "status",
      header: "Status",
      accessorFn: (r) => r.status,
      cell: (c) => CYCLE_STATUS_LABEL[c.row.original.status],
      meta: { width: "w-32", filter: { kind: "select", options: CYCLE_STATUS_OPTIONS } },
    },
    {
      id: "progress",
      header: "Runs",
      cell: (c) => {
        const s = c.row.original.summary;
        return (
          <span className="tabular text-[12.5px] text-ink-secondary">
            {s.total} {s.total === 1 ? "run" : "runs"}
          </span>
        );
      },
      meta: { width: "w-24", align: "right" },
    },
  ];

  const server: ServerState = {
    total: cycles.data?.total ?? 0,
    pagination: { pageIndex: query.page - 1, pageSize: query.page_size },
    onPaginationChange: (p) => {
      setQuery((q) => ({ ...q, page: p.pageIndex + 1, page_size: p.pageSize }));
    },
    sorting: [],
    onSortingChange: () => undefined,
    filters: query.status ? [{ id: "status", value: query.status }] : [],
    onFiltersChange: (f) => {
      const status = f.find((x) => x.id === "status")?.value;
      setQuery((q) => ({ ...q, status: typeof status === "string" ? status : undefined, page: 1 }));
    },
  };

  return (
    <Page
      title="Test cycles"
      subtitle="Execute a plan or a slice of the repository, assign testers and track progress."
      width="full"
      actions={
        canManage ? (
          <Button
            onClick={() => {
              setCreating(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            New cycle
          </Button>
        ) : undefined
      }
    >
      <DataTable
        label="Test cycles"
        columns={columns}
        data={cycles.data?.items ?? []}
        server={server}
        loading={cycles.isPending}
        error={cycles.error}
        noun={["cycle", "cycles"]}
        getRowId={(r) => r.id}
        rowProps={(r) => ({
          className: "cursor-pointer",
          onClick: () =>
            void navigate({
              to: "/p/$projectKey/cycles/$cycleKey",
              params: { projectKey: project.key, cycleKey: r.key },
            }),
        })}
        empty={
          <EmptyState
            icon={<PlayCircle className="size-5" />}
            text="No cycles yet. Create one from a plan or the repository."
            action={
              canManage ? (
                <Button
                  size="sm"
                  onClick={() => {
                    setCreating(true);
                  }}
                >
                  New cycle
                </Button>
              ) : undefined
            }
          />
        }
      />
      {creating ? (
        <CreateCycleDialog
          project={project}
          onClose={() => {
            setCreating(false);
          }}
          onCreated={(key) => {
            setCreating(false);
            void navigate({
              to: "/p/$projectKey/cycles/$cycleKey",
              params: { projectKey: project.key, cycleKey: key },
            });
          }}
        />
      ) : null}
    </Page>
  );
}

function CreateCycleDialog({
  project,
  onClose,
  onCreated,
}: {
  project: Project;
  onClose: () => void;
  onCreated: (key: string) => void;
}) {
  const toast = useToast();
  const create = useCreateCycle(project.id);
  const environments = useEnvironments(project.id);
  const plans = usePlans(project.id, { page: 1, page_size: 100, status: "active" });
  const [name, setName] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [planId, setPlanId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const activeEnvs = (environments.data ?? []).filter((e) => !e.archived);

  const submit = async () => {
    setError(null);
    try {
      const result = await create.mutateAsync({
        name: name.trim(),
        environment_id: environmentId,
        ...(planId ? { plan_id: planId } : {}),
        selection: { from_plan: Boolean(planId) },
      });
      toast(
        result.runs_pending ? "Cycle created; runs are being added" : `Cycle created (${result.added} runs)`,
      );
      onCreated(result.key);
    } catch (e) {
      setError(
        e instanceof ApiError ? (e.errors[0]?.message ?? e.detail ?? e.code) : "Could not create cycle",
      );
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="New test cycle"
      description="Pick an environment and, optionally, a plan to pull cases from."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            form="create-cycle"
            type="submit"
            disabled={create.isPending || name.trim().length < 3 || !environmentId}
          >
            Create
          </Button>
        </>
      }
    >
      <form
        id="create-cycle"
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
              placeholder="e.g. Regression Cycle 1"
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Environment" required>
          {(p) => (
            <Select
              {...p}
              value={environmentId}
              onChange={(e) => {
                setEnvironmentId(e.target.value);
              }}
            >
              <option value="">Select an environment…</option>
              {activeEnvs.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="From plan" hint="Leave empty to add cases later from the repository.">
          {(p) => (
            <Select
              {...p}
              value={planId}
              onChange={(e) => {
                setPlanId(e.target.value);
              }}
            >
              <option value="">No plan</option>
              {(plans.data?.items ?? []).map((pl) => (
                <option key={pl.id} value={pl.id}>
                  {pl.key} — {pl.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </form>
    </Dialog>
  );
}
