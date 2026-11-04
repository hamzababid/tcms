/**
 * Test design server state (docs/06 §4.4, §4.12). TanStack Query only; keys live here.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { useRoles, type ProjectMember } from "@/api/queries";
import type { components } from "@/api/schema";

export type Folder = components["schemas"]["FolderRead"];
export type CaseListItem = components["schemas"]["CaseListItem"];
export type CaseRead = components["schemas"]["CaseRead"];
export type VersionRead = components["schemas"]["VersionRead"];
export type VersionListItem = components["schemas"]["VersionListItem"];
export type CompareRead = components["schemas"]["CompareRead"];
export type Tag = components["schemas"]["TagRead"];
export type Comment = components["schemas"]["CommentRead"];
export type Attachment = components["schemas"]["AttachmentRead"];
export type Execution = components["schemas"]["ExecutionRead"];
export type ContentIn = components["schemas"]["ContentIn"];
export type StepIn = components["schemas"]["StepIn"];
export type BulkRequest = components["schemas"]["BulkRequest"];
export type CaseStatus = CaseRead["status"];

export const tdKeys = {
  all: (pid: string) => ["projects", pid, "td"] as const,
  folders: (pid: string, archived: boolean) => ["projects", pid, "td", "folders", archived] as const,
  cases: (pid: string, query: CaseQuery) => ["projects", pid, "td", "cases", query] as const,
  tags: (pid: string) => ["projects", pid, "td", "tags"] as const,
  case: (id: string) => ["case", id] as const,
  caseVersion: (id: string, version: number | null) => ["case", id, "version", version] as const,
  versions: (id: string) => ["case", id, "versions"] as const,
  compare: (id: string, from: number, to: number) => ["case", id, "compare", from, to] as const,
  executions: (id: string) => ["case", id, "executions"] as const,
  history: (id: string, page: number) => ["case", id, "history", page] as const,
  comments: (entityType: string, id: string) => ["comments", entityType, id] as const,
  resolve: (pid: string, key: string) => ["projects", pid, "resolve", key] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const useFolders = (pid: string, includeArchived: boolean) =>
  useQuery({
    queryKey: tdKeys.folders(pid, includeArchived),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/folders", {
            params: { path: { project_id: pid }, query: { include_archived: includeArchived } },
          })
        ).data,
      ),
  });

/** List filters of docs/06 §2.6 as sent to `GET /test-cases`. */
export interface CaseQuery {
  folder_id?: string;
  include_subfolders?: boolean;
  include_archived?: boolean;
  q?: string;
  status?: string;
  priority?: string;
  type?: string;
  tag?: string;
  owner_id?: string;
  sort?: string;
  page: number;
  page_size: number;
}

export const useCases = (pid: string, query: CaseQuery) =>
  useQuery({
    queryKey: tdKeys.cases(pid, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/test-cases", {
            params: { path: { project_id: pid }, query },
          })
        ).data,
      ),
  });

export const useTags = (pid: string) =>
  useQuery({
    queryKey: tdKeys.tags(pid),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/projects/{project_id}/tags", { params: { path: { project_id: pid } } })).data,
      ),
  });

/** `SPARK-TC-12` → case id (docs/04 §11.1). */
export const useResolvedCase = (pid: string, key: string) =>
  useQuery({
    queryKey: tdKeys.resolve(pid, key),
    staleTime: Infinity,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/resolve", {
            params: { path: { project_id: pid }, query: { key } },
          })
        ).data,
      ),
  });

export const useCase = (id: string | undefined, version: number | null = null) =>
  useQuery({
    queryKey: tdKeys.caseVersion(id ?? "", version),
    enabled: Boolean(id),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-cases/{case_id}", {
            params: { path: { case_id: id ?? "" }, query: version ? { version } : {} },
          })
        ).data,
      ),
  });

export const useVersions = (id: string) =>
  useQuery({
    queryKey: tdKeys.versions(id),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/test-cases/{case_id}/versions", { params: { path: { case_id: id } } })).data,
      ),
  });

export const useCompare = (id: string, from: number, to: number, enabled = true) =>
  useQuery({
    queryKey: tdKeys.compare(id, from, to),
    enabled,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-cases/{case_id}/compare", {
            params: { path: { case_id: id }, query: { from, to } },
          })
        ).data,
      ),
  });

export const useExecutions = (id: string) =>
  useQuery({
    queryKey: tdKeys.executions(id),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/test-cases/{case_id}/executions", { params: { path: { case_id: id } } }))
          .data,
      ),
  });

export const useCaseHistory = (id: string, page: number) =>
  useQuery({
    queryKey: tdKeys.history(id, page),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-cases/{case_id}/history", {
            params: { path: { case_id: id }, query: { page, page_size: 50 } },
          })
        ).data,
      ),
  });

export const useComments = (entityType: "test_case" | "test_case_version", id: string) =>
  useQuery({
    queryKey: tdKeys.comments(entityType, id),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/comments", { params: { query: { entity_type: entityType, entity_id: id } } }))
          .data,
      ),
  });

/** After any case write: the case itself, its project lists and tree counts. */
export function useInvalidateCase() {
  const qc = useQueryClient();
  return (pid: string, caseId?: string) => {
    void qc.invalidateQueries({ queryKey: tdKeys.all(pid) });
    if (caseId) void qc.invalidateQueries({ queryKey: ["case", caseId] });
  };
}

export async function uploadAttachment(
  entityType: "test_case" | "test_case_step",
  entityId: string,
  file: File,
) {
  const form = new FormData();
  form.append("file", file);
  form.append("entity_type", entityType);
  form.append("entity_id", entityId);
  const { data } = await api.POST("/api/v1/attachments", {
    // openapi-fetch sends FormData unchanged when the body is serialised by this callback
    body: form as unknown as components["schemas"]["Body_upload_api_v1_attachments_post"],
    bodySerializer: (b) => b as unknown as FormData,
  });
  return must(data);
}

/** Converts the editor's content into the API shape, dropping empty optional fields. */
export function emptyToNull(value: string | null | undefined): string | null {
  const v = (value ?? "").trim();
  return v === "" ? null : (value ?? null);
}

/** Members whose role may approve cases (reviewer must hold `testcase.approve`, docs/02 §5.2). */
export function useReviewers(members: ProjectMember[]): ProjectMember[] {
  const roles = useRoles();
  const approving = new Set(
    (roles.data ?? []).filter((r) => r.permissions.includes("testcase.approve")).map((r) => r.code),
  );
  return members.filter((m) => approving.has(m.role.code));
}
