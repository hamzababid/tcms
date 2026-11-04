import { createFileRoute } from "@tanstack/react-router";

import { useMe, useMembers } from "@/api/queries";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { useResolvedCase } from "@/features/testdesign/api";
import { CaseDetail } from "@/features/testdesign/CaseDetail";
import { projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/cases/$caseKey/")({
  component: function CasePage() {
    const project = useRouteProject();
    const { caseKey } = Route.useParams();
    const navigate = Route.useNavigate();
    const me = useMe();
    const members = useMembers(project.id);
    const resolved = useResolvedCase(project.id, caseKey);
    if (!me.data || resolved.isPending) return <Skeleton rows={8} />;
    if (resolved.isError) return <ErrorState error={resolved.error} />;
    return (
      <div className="mx-auto max-w-5xl rounded-card border border-border bg-surface p-6">
        <CaseDetail
          key={resolved.data.id}
          project={project}
          caseId={resolved.data.id}
          me={me.data}
          perms={projectPermissions(me.data, project.id)}
          members={members.data ?? []}
          variant="page"
          onDeleted={() =>
            void navigate({ to: "/p/$projectKey/repository", params: { projectKey: project.key } })
          }
          onDuplicated={(key) =>
            void navigate({
              to: "/p/$projectKey/cases/$caseKey",
              params: { projectKey: project.key, caseKey: key },
            })
          }
        />
      </div>
    );
  },
});
