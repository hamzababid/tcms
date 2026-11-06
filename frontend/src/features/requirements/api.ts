/**
 * Requirement references, coverage and traceability (docs/02 §10, docs/06 §4.9; ADR-024).
 * Requirements live in the team's tool; Assay keeps references and computes coverage.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type RequirementRef = components["schemas"]["RequirementRefRead"];
export type RequirementDetail = components["schemas"]["RequirementDetail"];
export type Traceability = components["schemas"]["TraceabilityRead"];
export type TraceRow = components["schemas"]["TraceRow"];
export type TraceCase = components["schemas"]["TraceCase"];
export type Coverage = components["schemas"]["CoverageRead"];
export type RefStatus = NonNullable<RequirementRef["status"]>;

export interface RequirementQuery {
  q?: string;
  linked?: boolean;
  plan_id?: string;
  release_id?: string;
  include_archived?: boolean;
  page: number;
  page_size: number;
}

export const reqKeys = {
  all: ["requirements"] as const,
  list: (pid: string, q: RequirementQuery) => ["requirements", pid, "list", q] as const,
  detail: (id: string, release: string | null) => ["requirements", "ref", id, release] as const,
  testCase: (id: string) => ["requirements", "case", id] as const,
  trace: (pid: string, q: object) => ["requirements", pid, "trace", q] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const useRequirements = (pid: string, query: RequirementQuery) =>
  useQuery({
    queryKey: reqKeys.list(pid, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/requirements", {
            params: { path: { project_id: pid }, query },
          })
        ).data,
      ),
  });

export const useRequirement = (id: string | null, releaseId: string | null) =>
  useQuery({
    queryKey: reqKeys.detail(id ?? "", releaseId),
    enabled: Boolean(id),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/requirements/{ref_id}", {
            params: { path: { ref_id: id ?? "" }, query: releaseId ? { release_id: releaseId } : {} },
          })
        ).data,
      ),
  });

export const useCaseRequirements = (caseId: string | undefined) =>
  useQuery({
    queryKey: reqKeys.testCase(caseId ?? ""),
    enabled: Boolean(caseId),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-cases/{case_id}/requirements", {
            params: { path: { case_id: caseId ?? "" } },
          })
        ).data,
      ),
  });

export interface TraceQuery {
  release_id?: string;
  status?: string;
  uncovered?: boolean;
  q?: string;
}

export const useTraceability = (pid: string, query: TraceQuery) =>
  useQuery({
    queryKey: reqKeys.trace(pid, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/traceability", {
            params: { path: { project_id: pid }, query },
          })
        ).data,
      ),
  });

export async function addRequirements(pid: string, references: string, url?: string, title?: string) {
  return must(
    (
      await api.POST("/api/v1/projects/{project_id}/requirements", {
        params: { path: { project_id: pid } },
        body: { references, url: url?.trim() || null, title: title?.trim() || null },
      })
    ).data,
  );
}

export async function patchRequirement(id: string, body: { url?: string | null; title?: string | null }) {
  return must(
    (await api.PATCH("/api/v1/requirements/{ref_id}", { params: { path: { ref_id: id } }, body })).data,
  );
}

export async function setRequirementArchived(id: string, archived: boolean) {
  const path = { params: { path: { ref_id: id } } };
  return must(
    (archived
      ? await api.POST("/api/v1/requirements/{ref_id}/archive", path)
      : await api.POST("/api/v1/requirements/{ref_id}/restore", path)
    ).data,
  );
}

/** Link cases picked by id, folder (with subfolders) or tag (the Add cases picker). */
export async function linkCases(
  refId: string,
  sel: { case_ids: string[]; folder_ids: string[]; tags: string[] },
) {
  return must(
    (
      await api.POST("/api/v1/requirements/{ref_id}/test-cases", {
        params: { path: { ref_id: refId } },
        body: { test_case_ids: sel.case_ids, folder_ids: sel.folder_ids, tags: sel.tags },
      })
    ).data,
  );
}

export async function unlinkCase(refId: string, caseId: string): Promise<void> {
  await api.DELETE("/api/v1/requirements/{ref_id}/test-cases/{case_id}", {
    params: { path: { ref_id: refId, case_id: caseId } },
  });
}

export async function linkCaseToRequirements(caseId: string, references: string) {
  return must(
    (
      await api.POST("/api/v1/test-cases/{case_id}/requirements", {
        params: { path: { case_id: caseId } },
        body: { references },
      })
    ).data,
  );
}

export async function bulkLink(pid: string, references: string, caseIds: string[]) {
  return must(
    (
      await api.POST("/api/v1/projects/{project_id}/requirements/link-cases", {
        params: { path: { project_id: pid } },
        body: { references, test_case_ids: caseIds },
      })
    ).data,
  );
}

export async function addPlanRequirements(planId: string, references: string) {
  return must(
    (
      await api.POST("/api/v1/test-plans/{plan_id}/requirements", {
        params: { path: { plan_id: planId } },
        body: { references },
      })
    ).data,
  );
}

export async function removePlanRequirement(planId: string, refId: string) {
  return must(
    (
      await api.DELETE("/api/v1/test-plans/{plan_id}/requirements", {
        params: { path: { plan_id: planId } },
        body: { requirement_ids: [refId] },
      })
    ).data,
  );
}

/** After a requirement write: every requirement list, traceability, plans and cases. */
export function useInvalidateRequirements() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: reqKeys.all });
    void qc.invalidateQueries({ queryKey: ["plan"] });
    void qc.invalidateQueries({ queryKey: ["case"] });
  };
}

export const STATUS_LABEL: Record<RefStatus, string> = {
  not_covered: "Not covered",
  failed: "Failed",
  blocked: "Blocked",
  not_run: "Not run",
  passed: "Passed",
};
