import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";

import { api } from "@/api/client";
import { useRoles } from "@/api/queries";
import { Card, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { ROLE_LABELS } from "@/lib/permissions";

const ROLE_ORDER = ["qa_manager", "qa_lead", "qa_engineer", "developer", "pm_ba", "viewer"];

/** Plain-language names for the permission codes (docs/02 §3.2). */
const PERMISSION_LABELS: Record<string, string> = {
  "project.view": "See the project",
  "project.configure": "Change project settings",
  "project.members.manage": "Manage members",
  "project.audit.view": "See the project audit log",
  "folder.manage": "Manage folders",
  "testcase.create": "Create test cases",
  "testcase.edit": "Edit test cases",
  "testcase.approve": "Approve or return cases",
  "testcase.archive": "Archive test cases",
  "testcase.delete": "Delete test cases",
  "plan.manage": "Manage test plans",
  "cycle.manage": "Manage cycles and runs",
  "cycle.reopen": "Reopen closed cycles",
  "run.execute": "Execute runs",
  "defect.create": "Link bugs",
  "defect.edit": "Edit bug links",
  "requirement.manage": "Manage requirement references",
  "requirement.link": "Link requirements to cases",
  "release.manage": "Manage releases and record decisions",
  "data.export": "Export data",
  "comment.create": "Comment",
};

/** docs/07 §5.13: the system roles and their permissions; read-only in the MVP (docs/02 §3.2). */
export function RolesPage() {
  const roles = useRoles();
  const catalog = useQuery({
    queryKey: ["meta", "permissions"],
    staleTime: Infinity,
    queryFn: async () => (await api.GET("/api/v1/meta/permissions")).data ?? [],
  });
  if (roles.isError) return <ErrorState error={roles.error} />;
  if (roles.isPending || catalog.isPending) return <Skeleton />;
  const ordered = ROLE_ORDER.map((code) => roles.data.find((r) => r.code === code)).filter(
    (r): r is NonNullable<typeof r> => Boolean(r),
  );
  // Bug status lives in the team's tracker (ADR-023): the defect transition permissions are unused.
  const projectPerms = (catalog.data ?? [])
    .filter((p) => p.scope === "project" && !p.permission.startsWith("defect.transition."))
    .map((p) => p.permission);
  const granted = new Map(ordered.map((r) => [r.code, new Set(r.permissions)]));
  return (
    <Page
      title="Roles"
      subtitle="What each project role can do. Roles are fixed in this version; custom roles come later."
      width="full"
    >
      <div className="flex flex-col gap-5">
        <Card>
          <div className="overflow-x-auto">
            <table aria-label="Role permissions" className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border text-left text-ink-secondary">
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Permission
                  </th>
                  {ordered.map((r) => (
                    <th key={r.code} scope="col" className="px-3 py-2 text-center font-medium">
                      {ROLE_LABELS[r.code] ?? r.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {projectPerms.map((p) => (
                  <tr key={p} className="border-b border-border last:border-0">
                    <th scope="row" className="py-2 pr-4 text-left font-normal">
                      <span className="text-ink">{PERMISSION_LABELS[p] ?? p}</span>
                      <span className="ml-2 font-mono text-[11.5px] text-ink-muted">{p}</span>
                    </th>
                    {ordered.map((r) => {
                      const yes = granted.get(r.code)?.has(p) ?? false;
                      return (
                        <td key={r.code} className="px-3 py-2 text-center">
                          {yes ? (
                            <Check aria-label="Yes" className="mx-auto size-4 text-accent" />
                          ) : (
                            <span aria-label="No" className="text-ink-faint">
                              ·
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Organization administrators">
          <p className="text-[13px] text-ink-secondary">
            Administrators have every permission in every project, manage users and the security policy, and
            see the audit log, access review and system status. Opening a project they are not a member of is
            recorded in the audit log.
          </p>
        </Card>
      </div>
    </Page>
  );
}
