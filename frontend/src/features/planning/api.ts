/**
 * Planning server state (docs/06 §4.5). TanStack Query only; keys live here (US-070…074).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type PlanRead = components["schemas"]["PlanRead"];
export type PlanListItem = components["schemas"]["PlanListItem"];
export type PlanCaseItem = components["schemas"]["PlanCaseItem"];
export type PlanCreate = components["schemas"]["PlanCreate"];
export type PlanPatch = components["schemas"]["PlanPatch"];
export type PlanType = PlanRead["type"];
export type PlanStatus = PlanRead["status"];

export interface PlanQuery {
  q?: string;
  status?: string;
  type?: string;
  sort?: string;
  page: number;
  page_size: number;
}

export const planKeys = {
  all: (pid: string) => ["projects", pid, "plans"] as const,
  list: (pid: string, query: PlanQuery) => ["projects", pid, "plans", "list", query] as const,
  plan: (id: string) => ["plan", id] as const,
  cases: (id: string) => ["plan", id, "cases"] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const usePlans = (pid: string, query: PlanQuery) =>
  useQuery({
    queryKey: planKeys.list(pid, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/test-plans", {
            params: { path: { project_id: pid }, query },
          })
        ).data,
      ),
  });

export const usePlan = (id: string | undefined) =>
  useQuery({
    queryKey: planKeys.plan(id ?? ""),
    enabled: Boolean(id),
    queryFn: async () =>
      must((await api.GET("/api/v1/test-plans/{plan_id}", { params: { path: { plan_id: id ?? "" } } })).data),
  });

export const usePlanCases = (id: string | undefined) =>
  useQuery({
    queryKey: planKeys.cases(id ?? ""),
    enabled: Boolean(id),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-plans/{plan_id}/cases", {
            params: { path: { plan_id: id ?? "" }, query: { page: 1, page_size: 200 } },
          })
        ).data,
      ),
  });

export function useInvalidatePlans() {
  const qc = useQueryClient();
  return (pid: string, planId?: string) => {
    void qc.invalidateQueries({ queryKey: planKeys.all(pid) });
    if (planId) void qc.invalidateQueries({ queryKey: planKeys.plan(planId) });
  };
}

export function useCreatePlan(pid: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (body: PlanCreate) =>
      must(
        (
          await api.POST("/api/v1/projects/{project_id}/test-plans", {
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

export function useArchivePlan(pid: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (planId: string) =>
      must(
        (await api.POST("/api/v1/test-plans/{plan_id}/archive", { params: { path: { plan_id: planId } } }))
          .data,
      ),
    onSuccess: (_d, planId) => {
      invalidate(pid, planId);
    },
  });
}

export function useSetPlanStatus(pid: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (args: { planId: string; status: PlanStatus; rowVersion: number }) =>
      must(
        (
          await api.PATCH("/api/v1/test-plans/{plan_id}", {
            params: { path: { plan_id: args.planId } },
            body: { status: args.status, row_version: args.rowVersion },
          })
        ).data,
      ),
    onSuccess: (_d, args) => {
      invalidate(pid, args.planId);
    },
  });
}

export function useClonePlan(pid: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (planId: string) =>
      must(
        (
          await api.POST("/api/v1/test-plans/{plan_id}/clone", {
            params: { path: { plan_id: planId } },
            body: {},
          })
        ).data,
      ),
    onSuccess: () => {
      invalidate(pid);
    },
  });
}
