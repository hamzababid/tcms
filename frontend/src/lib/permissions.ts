import type { Me } from "@/api/queries";

/** UI hint only; the server enforces every permission (docs/04 §11.2). */
export function projectPermissions(me: Me | undefined, projectId: string): Set<string> {
  if (!me) return new Set();
  const m = me.memberships.find((x) => x.project.id === projectId);
  if (m) return new Set(m.permissions);
  return me.is_org_admin ? new Set(["*"]) : new Set();
}

export function can(perms: Set<string>, permission: string): boolean {
  return perms.has("*") || perms.has(permission);
}

export const ROLE_LABELS: Record<string, string> = {
  qa_manager: "QA Manager",
  qa_lead: "QA Lead",
  qa_engineer: "QA Engineer",
  developer: "Developer",
  pm_ba: "PM / BA",
  viewer: "Viewer",
};

const LAST_PROJECT = "assay.lastProject";

export function rememberProject(key: string): void {
  try {
    localStorage.setItem(LAST_PROJECT, key);
  } catch {
    /* storage unavailable: nothing to remember */
  }
}

export function lastProject(): string | null {
  try {
    return localStorage.getItem(LAST_PROJECT);
  } catch {
    return null;
  }
}
