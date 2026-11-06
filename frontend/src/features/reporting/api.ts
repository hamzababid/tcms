/**
 * Dashboards, readiness, decisions, reports and exports (docs/06 §4.3, §4.10, §4.13, §5.9; M7).
 * Every number comes from the server (BR-24, CLAUDE.md rule 5); the client only formats.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, readCookie, toApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type Readiness = components["schemas"]["ReadinessRead"];
export type RuleResult = components["schemas"]["RuleRead"];
export type Decision = components["schemas"]["DecisionDetail"];
export type DecisionKind = components["schemas"]["DecisionCreate"]["decision"];
export type ReleaseSummary = components["schemas"]["ReleaseListItem"];
export type ManagerDashboard = components["schemas"]["ManagerDashboard"];
export type QualityDashboard = components["schemas"]["QualityDashboard"];
export type OrgDashboard = components["schemas"]["OrgDashboard"];
export type Summary = components["schemas"]["ExecutionSummaryRead"];
export type ReportPage = components["schemas"]["ReportRead"];
export type Transfer = components["schemas"]["TransferRead"];

export interface DashboardFilters {
  release_id?: string;
  cycle_ids?: string;
  environment_id?: string;
  module_folder_id?: string;
  tester_id?: string;
  date_from?: string;
  date_to?: string;
}

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const repKeys = {
  all: ["reporting"] as const,
  manager: (pid: string, f: DashboardFilters) => ["reporting", pid, "manager", f] as const,
  quality: (pid: string, f: object) => ["reporting", pid, "quality", f] as const,
  releases: (pid: string) => ["reporting", pid, "releases"] as const,
  readiness: (id: string) => ["reporting", "readiness", id] as const,
  planReadiness: (id: string) => ["reporting", "plan-readiness", id] as const,
  decisions: (id: string) => ["reporting", "decisions", id] as const,
  report: (pid: string, name: string, q: object) => ["reporting", pid, "report", name, q] as const,
  org: ["reporting", "org"] as const,
  transfer: (id: string) => ["reporting", "transfer", id] as const,
};

export const useManagerDashboard = (pid: string, f: DashboardFilters) =>
  useQuery({
    queryKey: repKeys.manager(pid, f),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/dashboards/manager", {
            params: { path: { project_id: pid }, query: f },
          })
        ).data,
      ),
  });

export const useQualityDashboard = (
  pid: string,
  f: { release_id?: string; date_from?: string; date_to?: string },
) =>
  useQuery({
    queryKey: repKeys.quality(pid, f),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/dashboards/quality", {
            params: { path: { project_id: pid }, query: f },
          })
        ).data,
      ),
  });

export const useOrgDashboard = () =>
  useQuery({
    queryKey: repKeys.org,
    queryFn: async () => must((await api.GET("/api/v1/organization/dashboard")).data),
  });

export const useReleaseSummaries = (pid: string) =>
  useQuery({
    queryKey: repKeys.releases(pid),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/release-summaries", {
            params: { path: { project_id: pid } },
          })
        ).data,
      ),
  });

export const useReleaseReadiness = (releaseId: string | undefined) =>
  useQuery({
    queryKey: repKeys.readiness(releaseId ?? ""),
    enabled: Boolean(releaseId),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/releases/{release_id}/readiness", {
            params: { path: { release_id: releaseId ?? "" } },
          })
        ).data,
      ),
  });

export const usePlanReadiness = (planId: string | undefined) =>
  useQuery({
    queryKey: repKeys.planReadiness(planId ?? ""),
    enabled: Boolean(planId),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-plans/{plan_id}/readiness", {
            params: { path: { plan_id: planId ?? "" } },
          })
        ).data,
      ),
  });

export const useDecisions = (releaseId: string | undefined) =>
  useQuery({
    queryKey: repKeys.decisions(releaseId ?? ""),
    enabled: Boolean(releaseId),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/releases/{release_id}/decisions", {
            params: { path: { release_id: releaseId ?? "" } },
          })
        ).data,
      ),
  });

export async function recordDecision(
  releaseId: string,
  body: { decision: DecisionKind; comment: string; risks?: string | null },
) {
  return must(
    (
      await api.POST("/api/v1/releases/{release_id}/decisions", {
        params: { path: { release_id: releaseId } },
        body,
      })
    ).data,
  );
}

export async function refreshMetrics(pid: string): Promise<void> {
  await api.POST("/api/v1/projects/{project_id}/metrics/refresh", { params: { path: { project_id: pid } } });
}

export const useReport = (pid: string, name: string, query: Record<string, string | number>) =>
  useQuery({
    queryKey: repKeys.report(pid, name, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/reports/{report}", {
            params: {
              path: { project_id: pid, report: name },
              // Report filters differ per report (docs/02 §11.5); the server rejects unknown ones.
              query: query,
            },
          })
        ).data,
      ),
  });

/** CSV/XLSX export: the file downloads at once (≤ 10,000 rows) or the server builds it in the
 * background and returns a transfer to poll (AC-RPT-04). */
export async function exportReport(
  pid: string,
  name: string,
  format: "csv" | "xlsx",
  filters: Record<string, string>,
): Promise<{ downloaded: true } | { transferId: string; rows: number }> {
  const res = await fetch(`/api/v1/projects/${pid}/reports/${name}/export`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": readCookie("tcms_csrf") ?? "" },
    body: JSON.stringify({ format, filters }),
  });
  if (res.status === 202) {
    const body = (await res.json()) as { transfer_id: string; rows: number };
    return { transferId: body.transfer_id, rows: body.rows };
  }
  if (!res.ok) throw await toApiError(res);
  const blob = await res.blob();
  const name_ =
    /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `${name}.${format}`;
  saveBlob(blob, name_);
  return { downloaded: true };
}

export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const useTransfer = (id: string | null) =>
  useQuery({
    queryKey: repKeys.transfer(id ?? ""),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data?.status === "generating" ? 2000 : false),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/data-transfers/{transfer_id}", {
            params: { path: { transfer_id: id ?? "" } },
          })
        ).data,
      ),
  });

export function useInvalidateReporting() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: repKeys.all });
  };
}

export const DECISION_LABEL: Record<DecisionKind, string> = {
  go: "Go",
  go_with_risks: "Go with risks",
  no_go: "No-go",
};
