import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { ImportWizard } from "@/features/imports/ImportWizard";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/import")({
  validateSearch: (
    s: Record<string, unknown>,
  ): { entity?: "test_case" | "requirement"; transfer?: string } => ({
    ...(s.entity === "requirement" || s.entity === "test_case" ? { entity: s.entity } : {}),
    ...(typeof s.transfer === "string" ? { transfer: s.transfer } : {}),
  }),
  component: function Import() {
    const project = useRouteProject();
    const { entity } = Route.useSearch();
    const me = useMe();
    if (!me.data)
      return (
        <div className="p-6">
          <Skeleton />
        </div>
      );
    const perms = projectPermissions(me.data, project.id);
    return (
      <ImportWizard
        key={entity ?? "test_case"}
        project={project}
        entity={entity ?? "test_case"}
        canImportCases={can(perms, "testcase.create")}
        canImportRequirements={can(perms, "requirement.manage")}
      />
    );
  },
});
