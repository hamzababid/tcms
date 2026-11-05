import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import type { ProjectMember } from "@/api/queries";
import { useToast, errorMessage } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Select } from "@/components/ui/field";
import { can } from "@/lib/permissions";

import { useInvalidateCase, useReviewers, type BulkRequest, type Folder, type Tag } from "./api";
import { AUTOMATION, CASE_TYPES, PRIORITY_LABELS } from "./labels";

type Action = BulkRequest["action"];

interface ActionSpec {
  label: string;
  permission: string;
  /** What the dialog asks for; none = confirm only. */
  input?: "folder" | "tags" | "priority" | "type" | "owner" | "reviewer" | "automation";
}

const ACTIONS: Partial<Record<Action, ActionSpec>> = {
  move: { label: "Move", permission: "testcase.edit", input: "folder" },
  add_tags: { label: "Add tags", permission: "testcase.edit", input: "tags" },
  remove_tags: { label: "Remove tags", permission: "testcase.edit", input: "tags" },
  set_priority: { label: "Priority", permission: "testcase.edit", input: "priority" },
  set_type: { label: "Type", permission: "testcase.edit", input: "type" },
  set_owner: { label: "Owner", permission: "testcase.edit", input: "owner" },
  set_reviewer: { label: "Reviewer", permission: "testcase.edit", input: "reviewer" },
  set_automation_status: { label: "Automation", permission: "testcase.edit", input: "automation" },
  deprecate: { label: "Deprecate", permission: "testcase.archive" },
  archive: { label: "Archive", permission: "testcase.archive" },
  restore: { label: "Restore", permission: "testcase.archive" },
};

export interface Selection {
  ids: string[];
  /** "Select all matching": the action runs on the list filter instead of ids. */
  filter: Record<string, string> | null;
  count: number;
}

export function BulkBar({
  projectId,
  selection,
  total,
  perms,
  folders,
  tags,
  members,
  onSelectAll,
  onClear,
}: {
  projectId: string;
  selection: Selection;
  total: number;
  perms: Set<string>;
  folders: Folder[];
  tags: Tag[];
  members: ProjectMember[];
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const [action, setAction] = useState<Action | null>(null);
  const available = (Object.entries(ACTIONS) as [Action, ActionSpec][]).filter(([, s]) =>
    can(perms, s.permission),
  );
  if (available.length === 0) return null;
  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-accent-border bg-accent-tint px-4 py-2 text-[13px]"
    >
      <span className="tabular font-semibold text-accent-ink">
        {selection.count.toLocaleString()} selected
      </span>
      {selection.filter === null && total > selection.ids.length ? (
        <Button variant="link" size="xs" onClick={onSelectAll}>
          Select all {total.toLocaleString()} matching
        </Button>
      ) : null}
      <Button variant="link" size="xs" onClick={onClear}>
        Clear
      </Button>
      <span className="flex-1" />
      {available.map(([a, s]) => (
        <Button
          key={a}
          variant="tint"
          size="xs"
          onClick={() => {
            setAction(a);
          }}
        >
          {s.label}
        </Button>
      ))}
      {action ? (
        <BulkDialog
          projectId={projectId}
          action={action}
          spec={ACTIONS[action] as ActionSpec}
          selection={selection}
          folders={folders}
          tags={tags}
          members={members}
          onDone={() => {
            setAction(null);
            onClear();
          }}
          onCancel={() => {
            setAction(null);
          }}
        />
      ) : null}
    </div>
  );
}

function BulkDialog({
  projectId,
  action,
  spec,
  selection,
  folders,
  tags,
  members,
  onDone,
  onCancel,
}: {
  projectId: string;
  action: Action;
  spec: ActionSpec;
  selection: Selection;
  folders: Folder[];
  tags: Tag[];
  members: ProjectMember[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const toast = useToast();
  const invalidate = useInvalidateCase();
  const [value, setValue] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const reviewers = useReviewers(members);
  const run = useMutation({
    mutationFn: async () => {
      const params: Record<string, unknown> =
        spec.input === "folder"
          ? { folder_id: value }
          : spec.input === "tags"
            ? { tags: picked }
            : spec.input
              ? { value: value === "" ? null : value }
              : {};
      const body: BulkRequest = {
        action,
        params,
        ...(selection.filter ? { filter: selection.filter } : { case_ids: selection.ids }),
      };
      const { data } = await api.POST("/api/v1/projects/{project_id}/test-cases/bulk", {
        params: { path: { project_id: projectId } },
        body,
      });
      return data;
    },
    onSuccess: (data) => {
      invalidate(projectId);
      if (data?.job_id) toast("Running in the background. Refresh the list shortly to see the changes.");
      else {
        const skipped = data?.skipped.length ?? 0;
        toast(
          `${(data?.updated ?? 0).toLocaleString()} updated${skipped ? `, ${skipped.toLocaleString()} skipped` : ""}`,
          skipped ? "error" : "ok",
        );
      }
      onDone();
    },
  });
  const needsValue =
    spec.input === "folder" ||
    spec.input === "priority" ||
    spec.input === "type" ||
    spec.input === "automation";
  const ready = spec.input === "tags" ? picked.length > 0 : !needsValue || value !== "";
  const options: [string, string][] =
    spec.input === "folder"
      ? folders.filter((f) => !f.archived).map((f) => [f.id, `${"  ".repeat(f.depth - 1)}${f.name}`])
      : spec.input === "priority"
        ? Object.entries(PRIORITY_LABELS)
        : spec.input === "type"
          ? Object.entries(CASE_TYPES)
          : spec.input === "automation"
            ? Object.entries(AUTOMATION)
            : spec.input === "owner"
              ? members.map((m) => [m.user.id, m.user.display_name])
              : spec.input === "reviewer"
                ? reviewers.map((m) => [m.user.id, m.user.display_name])
                : [];
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
      title={`${spec.label} · ${selection.count.toLocaleString()} cases`}
      {...(selection.count > 200 ? { description: "More than 200 cases run in the background." } : {})}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            disabled={!ready || run.isPending}
            onClick={() => {
              run.mutate();
            }}
          >
            Apply
          </Button>
        </>
      }
    >
      {spec.input === "tags" ? (
        <fieldset className="flex flex-wrap gap-2">
          <legend className="mb-2 text-[13px] font-medium text-ink">Tags</legend>
          {tags.map((t) => (
            <label
              key={t.id}
              className="flex items-center gap-1.5 rounded-full border border-border px-2 py-1 text-xs"
            >
              <input
                type="checkbox"
                checked={picked.includes(t.name)}
                onChange={(e) => {
                  setPicked((p) => (e.target.checked ? [...p, t.name] : p.filter((x) => x !== t.name)));
                }}
              />
              {t.name}
            </label>
          ))}
        </fieldset>
      ) : spec.input ? (
        <Field label={spec.label} required={needsValue}>
          {(p) => (
            <Select
              {...p}
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
              }}
            >
              <option value="">{needsValue ? "Choose…" : "None"}</option>
              {options.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          )}
        </Field>
      ) : (
        <p className="text-sm text-ink-secondary">
          {spec.label} {selection.count.toLocaleString()} cases? Cases where this is not possible are skipped.
        </p>
      )}
      {run.error ? (
        <p role="alert" className="mt-3 text-[13px] text-danger">
          {errorMessage(run.error)}
        </p>
      ) : null}
    </Dialog>
  );
}
