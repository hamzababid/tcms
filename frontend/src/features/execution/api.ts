/**
 * Execution server state (docs/06 §4.6). TanStack Query only; keys live here (US-080…087).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { useRoles, type ProjectMember } from "@/api/queries";
import type { components } from "@/api/schema";

export type CycleRead = components["schemas"]["CycleRead"];
export type CycleListItem = components["schemas"]["CycleListItem"];
export type CycleCreate = components["schemas"]["CycleCreate"];
export type CyclePatch = components["schemas"]["CyclePatch"];
export type CycleCreateResponse = components["schemas"]["CycleCreateResponse"];
export type AddRunsResponse = components["schemas"]["AddRunsResponse"];
export type ExecutionSummary = components["schemas"]["ExecutionSummaryRead"];
export type GroupProgress = components["schemas"]["GroupProgress"];
export type RunListItem = components["schemas"]["RunListItem"];
export type RunRead = components["schemas"]["RunRead"];
export type CycleStatus = CycleRead["status"];
export type RunStatus = RunListItem["status"];

export interface CycleQuery {
  q?: string;
  status?: string;
  release_id?: string;
  plan_id?: string;
  environment_id?: string;
  owner_id?: string;
  include_archived?: boolean;
  sort?: string;
  page: number;
  page_size: number;
}

/** Runs list filters and sorts (docs/06 §4.6). `assignee_id` takes a user id, `me` or `none`. */
export interface RunQuery {
  status?: string;
  assignee_id?: string;
  folder_id?: string;
  priority?: string;
  tag?: string;
  q?: string;
  needs_retest?: boolean;
  include_superseded?: boolean;
  sort?: string;
  page: number;
  page_size: number;
}

export const cycleKeys = {
  all: (pid: string) => ["projects", pid, "cycles"] as const,
  list: (pid: string, query: CycleQuery) => ["projects", pid, "cycles", "list", query] as const,
  cycle: (id: string) => ["cycle", id] as const,
  runs: (id: string, query: RunQuery) => ["cycle", id, "runs", query] as const,
  run: (id: string) => ["run", id] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const useCycles = (pid: string, query: CycleQuery) =>
  useQuery({
    queryKey: cycleKeys.list(pid, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/cycles", {
            params: { path: { project_id: pid }, query },
          })
        ).data,
      ),
  });

/** While runs are created in the background (`runs_pending`), poll every 2 s (docs/04 §5.2). */
export const useCycle = (id: string | undefined) =>
  useQuery({
    queryKey: cycleKeys.cycle(id ?? ""),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data?.runs_pending ? 2000 : false),
    queryFn: async () =>
      must((await api.GET("/api/v1/cycles/{cycle_id}", { params: { path: { cycle_id: id ?? "" } } })).data),
  });

export const useRuns = (id: string | undefined, query: RunQuery, pending = false) =>
  useQuery({
    queryKey: cycleKeys.runs(id ?? "", query),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
    refetchInterval: pending ? 2000 : false,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/cycles/{cycle_id}/runs", {
            params: { path: { cycle_id: id ?? "" }, query },
          })
        ).data,
      ),
  });

export const useRun = (id: string | undefined) =>
  useQuery({
    queryKey: cycleKeys.run(id ?? ""),
    enabled: Boolean(id),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/runs/{run_id}", {
            params: { path: { run_id: id ?? "" }, query: { include: "history" } },
          })
        ).data,
      ),
  });

/** After any cycle or run write: lists, the cycle, its runs and open run panels. */
export function useInvalidateCycle() {
  const qc = useQueryClient();
  return (pid: string, cycleId?: string) => {
    void qc.invalidateQueries({ queryKey: cycleKeys.all(pid) });
    void qc.invalidateQueries({ queryKey: ["run"] });
    // Plans show their cycles' progress (plan detail › Cycles, Cases).
    void qc.invalidateQueries({ queryKey: ["plan"] });
    if (cycleId) void qc.invalidateQueries({ queryKey: ["cycle", cycleId] });
  };
}

/** Wraps a cycle-scoped API call as a mutation that refreshes the cycle afterwards. */
function useCycleMutation<A, R>(pid: string, cycleId: string, fn: (args: A) => Promise<R | undefined>) {
  const invalidate = useInvalidateCycle();
  return useMutation({
    mutationFn: async (args: A) => must(await fn(args)),
    onSuccess: () => {
      invalidate(pid, cycleId);
    },
  });
}

const path = (cycleId: string) => ({ params: { path: { cycle_id: cycleId } } });

export function useCreateCycle(pid: string) {
  const invalidate = useInvalidateCycle();
  return useMutation({
    mutationFn: async (body: CycleCreate) =>
      must(
        (
          await api.POST("/api/v1/projects/{project_id}/cycles", {
            params: { path: { project_id: pid } },
            body,
          })
        ).data,
      ),
    onSuccess: () => {
      invalidate(pid);
    },
  });
}

export const usePatchCycle = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (body: CyclePatch) =>
      (await api.PATCH("/api/v1/cycles/{cycle_id}", { ...path(cycleId), body })).data,
  );

export const useStartCycle = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async () => (await api.POST("/api/v1/cycles/{cycle_id}/start", path(cycleId))).data,
  );

export const useCloseCycle = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (discardDrafts: boolean) =>
      (
        await api.POST("/api/v1/cycles/{cycle_id}/close", {
          ...path(cycleId),
          body: { discard_drafts: discardDrafts },
        })
      ).data,
  );

export const useReopenCycle = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (reason: string) =>
      (await api.POST("/api/v1/cycles/{cycle_id}/reopen", { ...path(cycleId), body: { reason } })).data,
  );

export const useArchiveCycle = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async () => (await api.POST("/api/v1/cycles/{cycle_id}/archive", path(cycleId))).data,
  );

export const useCloneCycle = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (body: { name: string; only_statuses: ("failed" | "blocked" | "not_run")[] | null }) =>
      (await api.POST("/api/v1/cycles/{cycle_id}/clone", { ...path(cycleId), body })).data,
  );

export const useSyncFromPlan = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async () => (await api.POST("/api/v1/cycles/{cycle_id}/sync-from-plan", path(cycleId))).data,
  );

export const useAddRuns = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (body: { case_ids: string[]; folder_ids: string[]; tags: string[] }) =>
      (await api.POST("/api/v1/cycles/{cycle_id}/runs", { ...path(cycleId), body })).data,
  );

export const useRemoveRuns = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (runIds: string[]) =>
      (await api.DELETE("/api/v1/cycles/{cycle_id}/runs", { ...path(cycleId), body: { run_ids: runIds } }))
        .data,
  );

/** Selected runs, or every run matching `filter` (TCMS-055 "assign by folder"). */
export const useAssignRuns = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (body: { run_ids?: string[]; filter?: Record<string, string>; assignee_id: string | null }) =>
      (await api.POST("/api/v1/cycles/{cycle_id}/runs/assign", { ...path(cycleId), body })).data,
  );

export const useSortRuns = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async (sortBy: "folder" | "priority") =>
      (
        await api.POST("/api/v1/cycles/{cycle_id}/runs/reorder", {
          ...path(cycleId),
          body: { sort_by: sortBy },
        })
      ).data,
  );

export const useUpdateNotRunVersions = (pid: string, cycleId: string) =>
  useCycleMutation(
    pid,
    cycleId,
    async () => (await api.POST("/api/v1/cycles/{cycle_id}/runs/update-versions", path(cycleId))).data,
  );

type RunAction = "claim" | "update-version" | "replace";

/** Per-run actions (claim, update to latest, replace with new run; US-082, US-086). */
export const useRunAction = (pid: string, cycleId: string, action: RunAction) =>
  useCycleMutation(pid, cycleId, async (runId: string) => {
    const p = { params: { path: { run_id: runId } } };
    if (action === "claim") return (await api.POST("/api/v1/runs/{run_id}/claim", p)).data;
    if (action === "update-version") return (await api.POST("/api/v1/runs/{run_id}/update-version", p)).data;
    return (await api.POST("/api/v1/runs/{run_id}/replace", p)).data;
  });

/** Members who may be assigned runs: their role holds `run.execute` (docs/02 §7.1, §2.3). */
export function useExecutors(members: ProjectMember[]): ProjectMember[] {
  const roles = useRoles();
  const executing = new Set(
    (roles.data ?? []).filter((r) => r.permissions.includes("run.execute")).map((r) => r.code),
  );
  return members.filter((m) => m.user.is_active && executing.has(m.role.code));
}
