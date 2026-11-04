import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { RepositoryPage } from "@/features/testdesign/RepositoryPage";
import { projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

interface RepositorySearch {
  folder?: string;
  case?: string;
}

export const Route = createFileRoute("/_app/p/$projectKey/repository")({
  validateSearch: (s: Record<string, unknown>): RepositorySearch => ({
    ...(typeof s.folder === "string" ? { folder: s.folder } : {}),
    ...(typeof s.case === "string" ? { case: s.case } : {}),
  }),
  component: function Repository() {
    const project = useRouteProject();
    const me = useMe();
    const search = Route.useSearch();
    const navigate = Route.useNavigate();
    if (!me.data) return <Skeleton />;
    return (
      <RepositoryPage
        project={project}
        me={me.data}
        perms={projectPermissions(me.data, project.id)}
        folderId={search.folder ?? null}
        caseKey={search.case ?? null}
        onFolder={(folder) => void navigate({ search: (s) => ({ ...s, folder: folder ?? undefined }) })}
        onCase={(key) => void navigate({ search: (s) => ({ ...s, case: key ?? undefined }) })}
      />
    );
  },
});
