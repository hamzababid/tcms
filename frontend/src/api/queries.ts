/**
 * Server state through TanStack Query only (docs/04 §11.2). Query keys are built here.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type Me = components["schemas"]["MeResponse"];
export type Project = components["schemas"]["ProjectRead"];
export type ProjectMember = components["schemas"]["ProjectMemberRead"];
export type Environment = components["schemas"]["EnvironmentRead"];
export type Release = components["schemas"]["ReleaseRead"];
export type Activity = components["schemas"]["ActivityItem"];
export type Organization = components["schemas"]["OrganizationRead"];
export type OrgMember = components["schemas"]["OrgMemberRead"];
export type Invitation = components["schemas"]["InvitationRead"];
export type ApiToken = components["schemas"]["ApiTokenRead"];
export type SessionInfo = components["schemas"]["SessionRead"];
export type Role = components["schemas"]["RoleRead"];

export const keys = {
  me: ["me"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  members: (id: string) => ["projects", id, "members"] as const,
  environments: (id: string) => ["projects", id, "environments"] as const,
  releases: (id: string) => ["projects", id, "releases"] as const,
  activity: (id: string, query: object) => ["projects", id, "activity", query] as const,
  organization: ["organization"] as const,
  orgMembers: ["organization", "members"] as const,
  invitations: ["organization", "invitations"] as const,
  roles: ["organization", "roles"] as const,
  sessions: ["me", "sessions"] as const,
  tokens: ["me", "api-tokens"] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const useMe = () =>
  useQuery({
    queryKey: keys.me,
    queryFn: async () => must((await api.GET("/api/v1/auth/me")).data),
    retry: false,
  });

export const useProjects = () =>
  useQuery({ queryKey: keys.projects, queryFn: async () => must((await api.GET("/api/v1/projects")).data) });

export const useProject = (id: string) =>
  useQuery({
    queryKey: keys.project(id),
    queryFn: async () =>
      must((await api.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })).data),
  });

export const useMembers = (id: string) =>
  useQuery({
    queryKey: keys.members(id),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/projects/{project_id}/members", { params: { path: { project_id: id } } }))
          .data,
      ),
  });

export const useEnvironments = (id: string) =>
  useQuery({
    queryKey: keys.environments(id),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/environments", {
            params: { path: { project_id: id }, query: { include_archived: true } },
          })
        ).data,
      ),
  });

export const useReleases = (id: string) =>
  useQuery({
    queryKey: keys.releases(id),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/projects/{project_id}/releases", { params: { path: { project_id: id } } }))
          .data,
      ),
  });

/** A human key (`SPARK-TC-12`, `SPARK-PL-3`, `SPARK-CY-12`) → its id (docs/04 §11.1, docs/06 §4.4). */
export const useResolvedKey = (pid: string, key: string) =>
  useQuery({
    queryKey: ["projects", pid, "resolve", key] as const,
    staleTime: Infinity,
    retry: false,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/resolve", {
            params: { path: { project_id: pid }, query: { key } },
          })
        ).data,
      ),
  });

/** A record's audit history (US-161; docs/06 §4.12): pages only, newest first. */
export const useRecordHistory = (
  entityType: string,
  entityId: string,
  page: { page: number; page_size: number },
) =>
  useQuery({
    queryKey: ["history", entityType, entityId, page] as const,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/audit-events/entity/{entity_type}/{entity_id}", {
            params: { path: { entity_type: entityType, entity_id: entityId }, query: page },
          })
        ).data,
      ),
  });

export interface AuditQuery {
  page: number;
  page_size: number;
  entity_type?: string;
  actor_id?: string;
  action?: string;
  occurred_at__gte?: string;
  occurred_at__lte?: string;
  q?: string;
}

export const useActivity = (id: string, query: AuditQuery) =>
  useQuery({
    queryKey: keys.activity(id, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/activity", {
            params: { path: { project_id: id }, query },
          })
        ).data,
      ),
  });

export const useOrganization = () =>
  useQuery({
    queryKey: keys.organization,
    queryFn: async () => must((await api.GET("/api/v1/organization")).data),
  });

export const useOrgMembers = (enabled = true) =>
  useQuery({
    queryKey: keys.orgMembers,
    enabled,
    queryFn: async () => must((await api.GET("/api/v1/organization/members")).data),
  });

export const useInvitations = () =>
  useQuery({
    queryKey: keys.invitations,
    queryFn: async () => must((await api.GET("/api/v1/organization/invitations")).data),
  });

export const useRoles = () =>
  useQuery({
    queryKey: keys.roles,
    queryFn: async () => must((await api.GET("/api/v1/organization/roles")).data),
  });

export const useSessions = () =>
  useQuery({
    queryKey: keys.sessions,
    queryFn: async () => must((await api.GET("/api/v1/me/sessions")).data),
  });

export const useTokens = () =>
  useQuery({
    queryKey: keys.tokens,
    queryFn: async () => must((await api.GET("/api/v1/me/api-tokens")).data),
  });
