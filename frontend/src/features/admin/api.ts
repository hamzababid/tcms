/** Administration server state (docs/06 §4.2, §4.12; M8b). */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { AuditQuery } from "@/api/queries";
import type { components } from "@/api/schema";

export type AuditEvent = components["schemas"]["AuditEventRead"];
export type AccessRow = components["schemas"]["AccessReviewRow"];
export type SystemStatus = components["schemas"]["SystemStatus"];
export type Job = components["schemas"]["JobRead"];
type AuditPage = components["schemas"]["Page_AuditEventRead_"];
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "dead";

export interface OrgAuditQuery extends AuditQuery {
  project_id?: string;
}

export const adminKeys = {
  all: ["admin"] as const,
  audit: (scope: string, query: object) => ["admin", "audit", scope, query] as const,
  accessReview: ["admin", "access-review"] as const,
  system: ["admin", "system"] as const,
  jobs: (statuses: JobStatus[], page: number) => ["admin", "jobs", statuses, page] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

/** The organization log, or one project's log when `projectId` is given. */
export const useAuditEvents = (query: OrgAuditQuery, projectId?: string) =>
  useQuery({
    queryKey: adminKeys.audit(projectId ?? "org", query),
    placeholderData: keepPreviousData,
    // These routes also answer with CSV (`?format=csv`), so the generated type is loose: JSON here.
    queryFn: async () =>
      must(
        (projectId
          ? (
              await api.GET("/api/v1/projects/{project_id}/audit-events", {
                params: { path: { project_id: projectId }, query },
              })
            ).data
          : (await api.GET("/api/v1/organization/audit-events", { params: { query } })).data) as
          AuditPage | undefined,
      ),
  });

export const useAccessReview = () =>
  useQuery({
    queryKey: adminKeys.accessReview,
    queryFn: async () =>
      must((await api.GET("/api/v1/organization/access-review")).data as AccessRow[] | undefined),
  });

export const useSystemStatus = () =>
  useQuery({
    queryKey: adminKeys.system,
    refetchInterval: 30_000,
    queryFn: async () => must((await api.GET("/api/v1/organization/system-status")).data),
  });

export const useJobs = (statuses: JobStatus[], page: number, pageSize: number, type?: string) =>
  useQuery({
    queryKey: [...adminKeys.jobs(statuses, page), pageSize, type ?? ""] as const,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/organization/jobs", {
            params: { query: { status: statuses, page, page_size: pageSize, ...(type ? { type } : {}) } },
          })
        ).data,
      ),
  });

export async function retryJob(jobId: string): Promise<Job> {
  return must(
    (await api.POST("/api/v1/organization/jobs/{job_id}/retry", { params: { path: { job_id: jobId } } }))
      .data,
  );
}

/** A GET download URL: the server answers with `Content-Disposition: attachment`. */
export function downloadUrl(path: string, query: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "") params.set(k, String(v));
  return `${path}?${params.toString()}`;
}
