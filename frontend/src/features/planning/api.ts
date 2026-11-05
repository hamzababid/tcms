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
export type PlanCycle = components["schemas"]["PlanCycle"];
export type ExitRule = components["schemas"]["ExitRule"];
export type Risk = components["schemas"]["Risk"];
export type AddCasesRequest = components["schemas"]["tcms__planning__schemas__AddCasesRequest"];
export type AddCasesResponse = components["schemas"]["AddCasesResponse"];
export type PlanType = PlanRead["type"];
export type PlanStatus = PlanRead["status"];

export interface PlanQuery {
  q?: string;
  status?: string;
  type?: string;
  release_id?: string;
  owner_id?: string;
  include_archived?: boolean;
  sort?: string;
  page: number;
  page_size: number;
}

export const planKeys = {
  all: (pid: string) => ["projects", pid, "plans"] as const,
  list: (pid: string, query: PlanQuery) => ["projects", pid, "plans", "list", query] as const,
  plan: (id: string) => ["plan", id] as const,
  cases: (id: string, page: object) => ["plan", id, "cases", page] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const usePlans = (pid: string, query: PlanQuery, enabled = true) =>
  useQuery({
    queryKey: planKeys.list(pid, query),
    enabled,
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

/** The plan with its cycles (plan detail › Cycles, docs/07 §5.7). */
export const usePlan = (id: string | undefined) =>
  useQuery({
    queryKey: planKeys.plan(id ?? ""),
    enabled: Boolean(id),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-plans/{plan_id}", {
            params: { path: { plan_id: id ?? "" }, query: { include: "cycles" } },
          })
        ).data,
      ),
  });

export const usePlanCases = (id: string | undefined, page: { page: number; page_size: number }) =>
  useQuery({
    queryKey: planKeys.cases(id ?? "", page),
    enabled: Boolean(id),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-plans/{plan_id}/cases", {
            params: { path: { plan_id: id ?? "" }, query: page },
          })
        ).data,
      ),
  });

/** After any plan write: the project's plan lists and the plan with its cases. */
export function useInvalidatePlans() {
  const qc = useQueryClient();
  return (pid: string, planId?: string) => {
    void qc.invalidateQueries({ queryKey: planKeys.all(pid) });
    if (planId) void qc.invalidateQueries({ queryKey: ["plan", planId] });
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

/** Field edits and status changes (PATCH with row_version, docs/06 §2.8). */
export function usePatchPlan(pid: string, planId: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (body: PlanPatch) =>
      must(
        (
          await api.PATCH("/api/v1/test-plans/{plan_id}", {
            params: { path: { plan_id: planId } },
            body,
          })
        ).data,
      ),
    onSuccess: () => {
      invalidate(pid, planId);
    },
  });
}

export function useArchivePlan(pid: string, planId: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async () =>
      must(
        (await api.POST("/api/v1/test-plans/{plan_id}/archive", { params: { path: { plan_id: planId } } }))
          .data,
      ),
    onSuccess: () => {
      invalidate(pid, planId);
    },
  });
}

export function useClonePlan(pid: string, planId: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (name: string) =>
      must(
        (
          await api.POST("/api/v1/test-plans/{plan_id}/clone", {
            params: { path: { plan_id: planId } },
            body: { name },
          })
        ).data,
      ),
    onSuccess: () => {
      invalidate(pid);
    },
  });
}

export function useAddPlanCases(pid: string, planId: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (body: AddCasesRequest) =>
      must(
        (
          await api.POST("/api/v1/test-plans/{plan_id}/cases", {
            params: { path: { plan_id: planId } },
            body,
          })
        ).data,
      ),
    onSuccess: () => {
      invalidate(pid, planId);
    },
  });
}

export function useRemovePlanCases(pid: string, planId: string) {
  const invalidate = useInvalidatePlans();
  return useMutation({
    mutationFn: async (caseIds: string[]) =>
      must(
        (
          await api.DELETE("/api/v1/test-plans/{plan_id}/cases", {
            params: { path: { plan_id: planId } },
            body: { case_ids: caseIds },
          })
        ).data,
      ),
    onSuccess: () => {
      invalidate(pid, planId);
    },
  });
}
