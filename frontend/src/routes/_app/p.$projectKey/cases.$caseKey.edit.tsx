import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { useMe, useMembers } from "@/api/queries";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/feedback";
import { useCase, useFolders, useResolvedCase, useTags } from "@/features/testdesign/api";
import { CaseEditor } from "@/features/testdesign/CaseEditor";
import { can, projectPermissions } from "@/lib/permissions";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/cases/$caseKey/edit")({
  component: function EditCase() {
    const project = useRouteProject();
    const { caseKey } = Route.useParams();
    const navigate = Route.useNavigate();
    const me = useMe();
    const resolved = useResolvedCase(project.id, caseKey);
    const existing = useCase(resolved.data?.id);
    const folders = useFolders(project.id, true);
    const members = useMembers(project.id);
    const tags = useTags(project.id);
    const [generation, setGeneration] = useState(0);
    if (!me.data || resolved.isPending || existing.isPending || folders.isPending || members.isPending) {
      return <Skeleton rows={8} />;
    }
    if (resolved.isError) return <ErrorState error={resolved.error} />;
    if (existing.isError) return <ErrorState error={existing.error} />;
    if (folders.isError) return <ErrorState error={folders.error} />;
    const c = existing.data;
    if (!can(projectPermissions(me.data, project.id), "testcase.edit") || project.status === "archived") {
      return <EmptyState text="You can't edit test cases in this project." />;
    }
    if (c.status === "archived") return <EmptyState text={`${c.key} is archived. Restore it to edit.`} />;
    const toDetail = () =>
      void navigate({
        to: "/p/$projectKey/repository",
        params: { projectKey: project.key },
        search: { folder: c.folder.id, case: c.key },
      });
    return (
      <CaseEditor
        key={`${c.id}-${generation}`}
        project={project}
        me={me.data}
        existing={c}
        initialFolderId={c.folder.id}
        folders={folders.data}
        members={members.data ?? []}
        tags={tags.data ?? []}
        onCancel={toDetail}
        onReload={() => {
          void existing.refetch().then(() => {
            setGeneration((g) => g + 1);
          });
        }}
        onSaved={(saved, next) => {
          if (next === "new") {
            void navigate({
              to: "/p/$projectKey/cases/new",
              params: { projectKey: project.key },
              search: { folder: saved.folder.id },
            });
          } else {
            void navigate({
              to: "/p/$projectKey/repository",
              params: { projectKey: project.key },
              search: { folder: saved.folder.id, case: saved.key },
            });
          }
        }}
      />
    );
  },
});
