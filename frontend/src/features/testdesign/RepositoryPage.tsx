import { FolderPlus, Plus } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { useMembers, type Me, type Project } from "@/api/queries";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import { ErrorState, PageHeader, Skeleton, errorMessage, useToast } from "@/components/common/feedback";
import { Kbd } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/field";
import { can } from "@/lib/permissions";

import { useFolders, useInvalidateCase, useResolvedCase, useTags, type Folder } from "./api";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import { FolderTree, type FolderActions } from "./FolderTree";

type FolderDialog =
  | { kind: "create"; parent: Folder | null }
  | { kind: "rename"; folder: Folder }
  | { kind: "delete"; folder: Folder }
  | { kind: "move"; folder: Folder; parentId: string | null; position?: number }
  | null;

/** Test repository (docs/07 §5.4; US-040…045). */
export function RepositoryPage({
  project,
  me,
  perms,
  folderId,
  caseKey,
  onFolder,
  onCase,
}: {
  project: Project;
  me: Me;
  perms: Set<string>;
  folderId: string | null;
  caseKey: string | null;
  onFolder: (id: string | null) => void;
  onCase: (key: string | null) => void;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const invalidate = useInvalidateCase();
  const [showArchived, setShowArchived] = useState(false);
  const [dialog, setDialog] = useState<FolderDialog>(null);
  const folders = useFolders(project.id, showArchived);
  const tags = useTags(project.id);
  const members = useMembers(project.id);
  const writable = project.status !== "archived";
  const canFolders = writable && can(perms, "folder.manage");
  const canCreate = writable && can(perms, "testcase.create");
  const canEdit = writable && can(perms, "testcase.edit");

  const folderList = folders.data ?? [];
  const selected = folderList.find((f) => f.id === folderId) ?? null;
  const firstUsable = folderList.find((f) => !f.archived);

  const newCase = () => {
    void navigate({
      to: "/p/$projectKey/cases/new",
      params: { projectKey: project.key },
      search: { folder: selected?.id ?? firstUsable?.id },
    });
  };

  // Shortcuts (docs/07 §10): C new case, F new folder — not while typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (
        e.ctrlKey ||
        e.metaKey ||
        e.altKey ||
        !t ||
        /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) ||
        t.isContentEditable
      )
        return;
      if (document.querySelector("[role=dialog]")) return;
      if (e.key === "c" && canCreate && firstUsable) {
        e.preventDefault();
        newCase();
      } else if (e.key === "f" && canFolders) {
        e.preventDefault();
        setDialog({ kind: "create", parent: selected });
      } else if (e.key === "Escape" && caseKey) onCase(null);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  });

  const refresh = () => {
    invalidate(project.id);
  };
  const folderMut = useMutation({
    mutationFn: async (d: NonNullable<FolderDialog> & { name?: string }) => {
      switch (d.kind) {
        case "create":
          return (
            await api.POST("/api/v1/projects/{project_id}/folders", {
              params: { path: { project_id: project.id } },
              body: { name: d.name ?? "", parent_id: d.parent?.id ?? null },
            })
          ).data;
        case "rename":
          return (
            await api.PATCH("/api/v1/folders/{folder_id}", {
              params: { path: { folder_id: d.folder.id } },
              body: { name: d.name ?? "", row_version: d.folder.row_version },
            })
          ).data;
        case "delete":
          await api.DELETE("/api/v1/folders/{folder_id}", { params: { path: { folder_id: d.folder.id } } });
          return null;
        case "move":
          return (
            await api.POST("/api/v1/folders/{folder_id}/move", {
              params: { path: { folder_id: d.folder.id } },
              body: {
                parent_id: d.parentId,
                position: d.position ?? null,
                row_version: d.folder.row_version,
              },
            })
          ).data;
      }
    },
    onSuccess: (data, d) => {
      setDialog(null);
      refresh();
      if (d.kind === "create" && data) onFolder(data.id);
      if (d.kind === "delete" && d.folder.id === folderId) onFolder(null);
    },
    onError: (e, d) => {
      if (d.kind === "move") {
        setDialog(null);
        toast(errorMessage(e), "error");
      }
    },
  });
  const archiveMut = useMutation({
    mutationFn: async (f: Folder) =>
      f.archived
        ? api.POST("/api/v1/folders/{folder_id}/restore", { params: { path: { folder_id: f.id } } })
        : api.POST("/api/v1/folders/{folder_id}/archive", { params: { path: { folder_id: f.id } } }),
    onSuccess: (_d, f) => {
      refresh();
      toast(f.archived ? `Restored ${f.name}` : `Archived ${f.name}`);
    },
    onError: (e) => {
      toast(errorMessage(e), "error");
    },
  });
  const moveCases = useMutation({
    mutationFn: async ({ ids, folder }: { ids: string[]; folder: Folder }) =>
      (
        await api.POST("/api/v1/projects/{project_id}/test-cases/bulk", {
          params: { path: { project_id: project.id } },
          body: { action: "move", case_ids: ids, params: { folder_id: folder.id } },
        })
      ).data,
    onSuccess: (data, { folder }) => {
      refresh();
      toast(
        data?.job_id
          ? "Moving in the background"
          : `Moved ${(data?.updated ?? 0).toLocaleString()} to ${folder.name}`,
      );
    },
    onError: (e) => {
      toast(errorMessage(e), "error");
    },
  });

  const actions: FolderActions = {
    onNewSubfolder: (parent) => {
      setDialog({ kind: "create", parent });
    },
    onRename: (folder) => {
      setDialog({ kind: "rename", folder });
    },
    onToggleArchive: (folder) => {
      archiveMut.mutate(folder);
    },
    onDelete: (folder) => {
      setDialog({ kind: "delete", folder });
    },
    onMoveFolder: (folder, parentId, position) => {
      const target =
        position === undefined
          ? { kind: "move" as const, folder, parentId }
          : { kind: "move" as const, folder, parentId, position };
      // docs/07 §5.4: confirm when moving more than 100 cases to another folder (reordering needs no confirmation)
      if (folder.total_count > 100 && parentId !== folder.parent_id) setDialog(target);
      else folderMut.mutate(target);
    },
    onDropCases: (ids, folder) => {
      moveCases.mutate({ ids, folder });
    },
  };

  return (
    <div className="flex h-full min-h-[520px] flex-col">
      <PageHeader
        title="Repository"
        actions={
          <>
            {canFolders ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setDialog({ kind: "create", parent: selected });
                }}
              >
                <FolderPlus aria-hidden="true" className="size-4" />
                Folder
              </Button>
            ) : null}
            {canCreate && firstUsable ? (
              <Button size="sm" onClick={newCase}>
                <Plus aria-hidden="true" className="size-4" />
                New case <Kbd onAccent>C</Kbd>
              </Button>
            ) : null}
          </>
        }
      />
      <div className="flex min-h-0 flex-1">
        <aside
          aria-label="Folders"
          className="flex w-[264px] shrink-0 flex-col border-r border-border bg-surface p-3"
        >
          {folders.isPending ? (
            <Skeleton rows={6} />
          ) : folders.isError ? (
            <ErrorState error={folders.error} onRetry={() => void folders.refetch()} />
          ) : folderList.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-2 text-center text-[13px] text-ink-secondary">
              <p>No folders yet. Folders organise cases by module or feature.</p>
              {canFolders ? (
                <Button
                  size="sm"
                  onClick={() => {
                    setDialog({ kind: "create", parent: null });
                  }}
                >
                  Create a folder (F)
                </Button>
              ) : null}
            </div>
          ) : (
            <FolderTree
              folders={folderList}
              selectedId={folderId}
              onSelect={(id) => {
                onFolder(id);
              }}
              canManage={canFolders}
              canMoveCases={canEdit}
              actions={actions}
            />
          )}
          <div className="mt-2 border-t border-rule pt-2.5">
            <Checkbox
              label="Show archived"
              checked={showArchived}
              onChange={(e) => {
                setShowArchived(e.target.checked);
              }}
            />
          </div>
        </aside>
        <CaseList
          projectId={project.id}
          folderId={folderId}
          folderName={selected?.name ?? null}
          selectedKey={caseKey}
          onOpen={(c) => {
            onCase(c.key);
          }}
          onOpenFullPage={(c) => {
            window.open(`/p/${project.key}/cases/${c.key}`, "_blank", "noopener");
          }}
          perms={writable ? perms : new Set(["project.view"])}
          canEdit={canEdit}
          folders={folderList}
          tags={tags.data ?? []}
          members={members.data ?? []}
          onNewCase={canCreate && firstUsable ? newCase : null}
        />
        {caseKey ? (
          <aside
            aria-label={`${caseKey} details`}
            className="flex w-[clamp(380px,32vw,560px)] shrink-0 flex-col overflow-hidden border-l border-border bg-surface"
          >
            <PanelCase
              project={project}
              caseKey={caseKey}
              me={me}
              perms={perms}
              onClose={() => {
                onCase(null);
              }}
              onOpenKey={onCase}
            />
          </aside>
        ) : null}
      </div>

      <PromptDialog
        open={dialog?.kind === "create" || dialog?.kind === "rename"}
        onOpenChange={(o) => {
          if (!o) {
            setDialog(null);
            folderMut.reset();
          }
        }}
        title={
          dialog?.kind === "rename"
            ? `Rename ${dialog.folder.name}`
            : dialog?.kind === "create" && dialog.parent
              ? `New folder in ${dialog.parent.name}`
              : "New folder"
        }
        label="Name"
        initial={dialog?.kind === "rename" ? dialog.folder.name : ""}
        submitLabel={dialog?.kind === "rename" ? "Rename" : "Create"}
        pending={folderMut.isPending}
        error={folderMut.error}
        onSubmit={(name) => {
          if (dialog && (dialog.kind === "create" || dialog.kind === "rename"))
            folderMut.mutate({ ...dialog, name });
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === "delete"}
        onOpenChange={(o) => {
          if (!o) {
            setDialog(null);
            folderMut.reset();
          }
        }}
        title={dialog?.kind === "delete" ? `Delete ${dialog.folder.name}?` : ""}
        description="Only empty folders (no cases, including archived ones, and no subfolders) can be deleted."
        confirmLabel="Delete"
        destructive
        pending={folderMut.isPending}
        error={folderMut.error}
        onConfirm={() => {
          if (dialog?.kind === "delete") folderMut.mutate(dialog);
        }}
      />
      <ConfirmDialog
        open={dialog?.kind === "move"}
        onOpenChange={(o) => {
          if (!o) setDialog(null);
        }}
        title={dialog?.kind === "move" ? `Move ${dialog.folder.name}?` : ""}
        description={
          dialog?.kind === "move"
            ? `This moves ${dialog.folder.total_count.toLocaleString()} cases with the folder.`
            : ""
        }
        confirmLabel="Move"
        pending={folderMut.isPending}
        onConfirm={() => {
          if (dialog?.kind === "move") folderMut.mutate(dialog);
        }}
      />
    </div>
  );
}

function PanelCase({
  project,
  caseKey,
  me,
  perms,
  onClose,
  onOpenKey,
}: {
  project: Project;
  caseKey: string;
  me: Me;
  perms: Set<string>;
  onClose: () => void;
  onOpenKey: (key: string) => void;
}) {
  const resolved = useResolvedCase(project.id, caseKey);
  const members = useMembers(project.id);
  if (resolved.isPending)
    return (
      <div className="p-4">
        <Skeleton rows={6} />
      </div>
    );
  if (resolved.isError)
    return (
      <div className="p-4">
        <ErrorState error={resolved.error} />
      </div>
    );
  return (
    <CaseDetail
      key={resolved.data.id}
      project={project}
      caseId={resolved.data.id}
      me={me}
      perms={perms}
      members={members.data ?? []}
      variant="panel"
      onClose={onClose}
      onDeleted={onClose}
      onDuplicated={onOpenKey}
    />
  );
}
