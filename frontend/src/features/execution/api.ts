/**
 * Execution server state (docs/06 §4.6). TanStack Query only; keys live here (US-080…087).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type CycleRead = components["schemas"]["CycleRead"];
export type CycleListItem = components["schemas"]["CycleListItem"];
export type CycleCreate = components["schemas"]["CycleCreate"];
export type CycleCreateResponse = components["schemas"]["CycleCreateResponse"];
export type RunRead = components["schemas"]["RunRead"];
export type CycleStatus = CycleRead["status"];
export type RunStatus = RunRead["status"];

export interface CycleQuery {
  q?: string;
  status?: string;
  release_id?: string;
  plan_id?: string;
  sort?: string;
  page: number;
  page_size: number;
}

export interface RunQuery {
  status?: string;
  assignee_id?: string;
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

export const useCycle = (id: string | undefined) =>
  useQuery({
    queryKey: cycleKeys.cycle(id ?? ""),
    enabled: Boolean(id),
    queryFn: async () =>
      must((await api.GET("/api/v1/cycles/{cycle_id}", { params: { path: { cycle_id: id ?? "" } } })).data),
  });

export const useRuns = (id: string | undefined, query: RunQuery) =>
  useQuery({
    queryKey: cycleKeys.runs(id ?? "", query),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/cycles/{cycle_id}/runs", {
            params: { path: { cycle_id: id ?? "" }, query },
          })
        ).data,
      ),
  });

export function useInvalidateCycle() {
  const qc = useQueryClient();
  return (pid: string, cycleId?: string) => {
    void qc.invalidateQueries({ queryKey: cycleKeys.all(pid) });
    if (cycleId) void qc.invalidateQueries({ queryKey: cycleKeys.cycle(cycleId) });
    if (cycleId) void qc.invalidateQueries({ queryKey: ["cycle", cycleId, "runs"] });
  };
}

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

/** A cycle lifecycle action without a body (start, archive, sync-from-plan). */
type SimpleCycleAction = "start" | "archive" | "sync-from-plan";

export function useCycleAction(pid: string, cycleId: string) {
  const invalidate = useInvalidateCycle();
  const run = async (fn: () => Promise<unknown>) => {
    await fn();
    invalidate(pid, cycleId);
  };
  return {
    simple: (action: SimpleCycleAction) =>
      run(() =>
        api.POST(`/api/v1/cycles/{cycle_id}/${action}` as "/api/v1/cycles/{cycle_id}/start", {
          params: { path: { cycle_id: cycleId } },
        }),
      ),
    close: (discardDrafts: boolean) =>
      run(() =>
        api.POST("/api/v1/cycles/{cycle_id}/close", {
          params: { path: { cycle_id: cycleId } },
          body: { discard_drafts: discardDrafts },
        }),
      ),
    reopen: (reason: string) =>
      run(() =>
        api.POST("/api/v1/cycles/{cycle_id}/reopen", {
          params: { path: { cycle_id: cycleId } },
          body: { reason },
        }),
      ),
    assign: (runIds: string[], assigneeId: string | null) =>
      run(() =>
        api.POST("/api/v1/cycles/{cycle_id}/runs/assign", {
          params: { path: { cycle_id: cycleId } },
          body: { run_ids: runIds, assignee_id: assigneeId },
        }),
      ),
    addCases: (caseIds: string[]) =>
      run(() =>
        api.POST("/api/v1/cycles/{cycle_id}/runs", {
          params: { path: { cycle_id: cycleId } },
          body: { case_ids: caseIds },
        }),
      ),
    reorder: (orderedRunIds: string[]) =>
      run(() =>
        api.POST("/api/v1/cycles/{cycle_id}/runs/reorder", {
          params: { path: { cycle_id: cycleId } },
          body: { ordered_run_ids: orderedRunIds },
        }),
      ),
  };
}

export function useClaimRun(pid: string, cycleId: string) {
  const invalidate = useInvalidateCycle();
  return useMutation({
    mutationFn: async (runId: string) =>
      must((await api.POST("/api/v1/runs/{run_id}/claim", { params: { path: { run_id: runId } } })).data),
    onSuccess: () => {
      invalidate(pid, cycleId);
    },
  });
}
