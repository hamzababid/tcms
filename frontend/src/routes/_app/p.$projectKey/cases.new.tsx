import { createFileRoute } from "@tanstack/react-router";

import { useMe, useMembers } from "@/api/queries";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/feedback";
import { useFolders, useTags } from "@/features/testdesign/api";
import { CaseEditor } from "@/features/testdesign/CaseEditor";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/cases/new")({
  validateSearch: (s: Record<string, unknown>): { folder?: string } =>
    typeof s.folder === "string" ? { folder: s.folder } : {},
  component: function NewCase() {
    const project = useRouteProject();
    const me = useMe();
    const { folder } = Route.useSearch();
    const navigate = Route.useNavigate();
    const folders = useFolders(project.id, false);
    const members = useMembers(project.id);
    const tags = useTags(project.id);
    if (!me.data || folders.isPending || members.isPending)
      return (
        <div className="p-6">
          <Skeleton rows={8} />
        </div>
      );
    if (folders.isError)
      return (
        <div className="p-6">
          <ErrorState error={folders.error} />
        </div>
      );
    const start = folders.data.find((f) => f.id === folder) ?? folders.data[0];
    if (!start)
      return (
        <div className="p-6">
          <EmptyState text="Create a folder in the repository before adding cases." />
        </div>
      );
    return (
      <CaseEditor
        key={folder ?? "new"}
        project={project}
        me={me.data}
        existing={null}
        initialFolderId={start.id}
        folders={folders.data}
        members={members.data ?? []}
        tags={tags.data ?? []}
        onCancel={() =>
          void navigate({
            to: "/p/$projectKey/repository",
            params: { projectKey: project.key },
            search: { folder: start.id },
          })
        }
        onReload={() => undefined}
        onSaved={(saved, next) => {
          if (next === "detail") {
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
