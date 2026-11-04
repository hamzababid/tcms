/**
 * Server state through TanStack Query only (docs/04 §11.2). Query keys are built here.
 */
import { useQuery } from "@tanstack/react-query";

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
  activity: (id: string, page: number, entityType: string | null) =>
    ["projects", id, "activity", page, entityType] as const,
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

export const useActivity = (id: string, page: number, entityType: string | null) =>
  useQuery({
    queryKey: keys.activity(id, page, entityType),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/activity", {
            params: {
              path: { project_id: id },
              query: { page, page_size: 50, ...(entityType ? { entity_type: entityType } : {}) },
            },
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
