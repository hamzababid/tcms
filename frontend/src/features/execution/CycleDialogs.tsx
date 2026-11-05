import { useState } from "react";

import { ApiError } from "@/api/client";
import { useEnvironments, useReleases, type Project, type ProjectMember } from "@/api/queries";
import { ConflictDialog } from "@/components/common/dialogs";
import { errorMessage, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { FormError } from "@/features/auth/AuthCard";
import type { Folder } from "@/features/testdesign/api";
import { AddResult } from "@/features/testdesign/CaseSelector";

import { useCloneCycle, useCloseCycle, usePatchCycle, type CycleCreateResponse, type CycleRead } from "./api";

/** Edit cycle basics (docs/06 §4.6 PATCH; the environment is fixed once runs have attempts). */
export function EditCycleDialog({
  project,
  cycle,
  onClose,
}: {
  project: Project;
  cycle: CycleRead;
  onClose: () => void;
}) {
  const toast = useToast();
  const patch = usePatchCycle(project.id, cycle.id);
  const environments = useEnvironments(project.id);
  const releases = useReleases(project.id);
  const [v, setV] = useState({
    name: cycle.name,
    release_id: cycle.release?.id ?? "",
    environment_id: cycle.environment.id,
    build: cycle.build ?? "",
    start_date: cycle.start_date ?? "",
    due_date: cycle.due_date ?? "",
    description: cycle.description ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<unknown>(null);
  const set = (k: keyof typeof v, value: string) => {
    setV((cur) => ({ ...cur, [k]: value }));
  };
  const envs = (environments.data ?? []).filter((e) => !e.archived || e.id === cycle.environment.id);

  const submit = () => {
    setFormError(null);
    const n = v.name.trim().length;
    if (n < 3 || n > 120) {
      setErrors({ name: "Use 3 to 120 characters" });
      return;
    }
    setErrors({});
    patch.mutate(
      {
        name: v.name.trim(),
        release_id: v.release_id || null,
        environment_id: v.environment_id,
        build: v.build.trim() || null,
        start_date: v.start_date || null,
        due_date: v.due_date || null,
        description: v.description.trim() || null,
        row_version: cycle.row_version,
      },
      {
        onSuccess: () => {
          toast("Cycle saved");
          onClose();
        },
        onError: (e) => {
          if (e instanceof ApiError && e.code === "stale_row_version") setConflict(e);
          else if (e instanceof ApiError && e.code === "name_taken")
            setErrors({ name: e.detail ?? "A cycle with this name already exists" });
          else if (e instanceof ApiError && e.errors.length) {
            setErrors(
              Object.fromEntries(e.errors.map((fe) => [fe.field.split(/[.[]/)[0] ?? fe.field, fe.message])),
            );
            setFormError(e.detail);
          } else setFormError(errorMessage(e));
        },
      },
    );
  };

  return (
    <Dialog
      open
      wide
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={`Edit ${cycle.key}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="edit-cycle" disabled={patch.isPending}>
            Save
          </Button>
        </>
      }
    >
      <form
        id="edit-cycle"
        noValidate
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <FormError message={formError} />
        <Field label="Name" required error={errors.name}>
          {(p) => (
            <Input
              {...p}
              value={v.name}
              onChange={(e) => {
                set("name", e.target.value);
              }}
            />
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Release" error={errors.release_id}>
            {(p) => (
              <Select
                {...p}
                value={v.release_id}
                onChange={(e) => {
                  set("release_id", e.target.value);
                }}
              >
                <option value="">No release</option>
                {(releases.data ?? []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field
            label="Environment"
            required
            error={errors.environment_id}
            hint="Fixed once any run has an attempt."
          >
            {(p) => (
              <Select
                {...p}
                value={v.environment_id}
                onChange={(e) => {
                  set("environment_id", e.target.value);
                }}
              >
                {envs.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Build" error={errors.build}>
            {(p) => (
              <Input
                {...p}
                value={v.build}
                onChange={(e) => {
                  set("build", e.target.value);
                }}
              />
            )}
          </Field>
          <Field label="Start" error={errors.start_date}>
            {(p) => (
              <Input
                {...p}
                type="date"
                value={v.start_date}
                onChange={(e) => {
                  set("start_date", e.target.value);
                }}
              />
            )}
          </Field>
          <Field label="Due" error={errors.due_date}>
            {(p) => (
              <Input
                {...p}
                type="date"
                value={v.due_date}
                onChange={(e) => {
                  set("due_date", e.target.value);
                }}
              />
            )}
          </Field>
        </div>
        <Field label="Description" error={errors.description}>
          {(p) => (
            <Textarea
              {...p}
              rows={3}
              value={v.description}
              onChange={(e) => {
                set("description", e.target.value);
              }}
            />
          )}
        </Field>
      </form>
      <ConflictDialog
        error={conflict}
        onClose={() => {
          setConflict(null);
        }}
        onReload={() => {
          setConflict(null);
          onClose();
        }}
      />
    </Dialog>
  );
}

interface Draft {
  run_id: string;
  case_key: string;
  executed_by: string | null;
}

/**
 * Close (US-084, BR-11, TCMS-058): a first attempt without discarding; when the server answers
 * `409 draft_exists` the drafts are listed and closing again discards them.
 */
export function CloseCycleDialog({
  project,
  cycle,
  onClose,
}: {
  project: Project;
  cycle: CycleRead;
  onClose: () => void;
}) {
  const toast = useToast();
  const close = useCloseCycle(project.id, cycle.id);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const run = (discard: boolean) => {
    setError(null);
    close.mutate(discard, {
      onSuccess: () => {
        toast(discard ? `${cycle.key} closed; drafts discarded` : `${cycle.key} closed`);
        onClose();
      },
      onError: (e) => {
        const listed = e instanceof ApiError && e.code === "draft_exists" ? e.body.drafts : undefined;
        if (Array.isArray(listed)) setDrafts(listed as Draft[]);
        else setError(e);
      },
    });
  };
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={`Close ${cycle.key}?`}
      description="A closed cycle is read-only: nothing can be executed, assigned or added until it is reopened."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          {drafts ? (
            <Button
              variant="destructive"
              disabled={close.isPending}
              onClick={() => {
                run(true);
              }}
            >
              Discard {drafts.length} {drafts.length === 1 ? "draft" : "drafts"} and close
            </Button>
          ) : (
            <Button
              disabled={close.isPending}
              onClick={() => {
                run(false);
              }}
            >
              Close cycle
            </Button>
          )}
        </>
      }
    >
      {drafts ? (
        <div role="alert" className="grid gap-2 text-[13px]">
          <p className="text-ink">
            These runs have unfinished draft attempts. Closing discards the drafts; each run keeps its last
            final result.
          </p>
          <ul className="max-h-48 overflow-y-auto rounded-control border border-border p-2">
            {drafts.map((d) => (
              <li key={d.run_id} className="flex gap-3 py-0.5">
                <span className="w-32 shrink-0 font-mono text-[12.5px]">{d.case_key}</span>
                <span className="text-ink-secondary">{d.executed_by ?? "Unknown tester"}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-[13px] text-ink-secondary">
          {cycle.summary.not_run > 0
            ? `${cycle.summary.not_run.toLocaleString()} runs are not run yet and stay not run.`
            : "Every run has a result."}
        </p>
      )}
      {error ? (
        <p role="alert" className="mt-3 text-[13px] text-danger">
          {errorMessage(error)}
        </p>
      ) : null}
    </Dialog>
  );
}

const CLONE_STATUSES = [
  ["failed", "Failed"],
  ["blocked", "Blocked"],
  ["not_run", "Not run"],
] as const;

/** Clone (US-084, TCMS-060): same cases at their current eligible versions, no results. */
export function CloneCycleDialog({
  project,
  cycle,
  onClose,
  onOpen,
}: {
  project: Project;
  cycle: CycleRead;
  onClose: () => void;
  onOpen: (key: string) => void;
}) {
  const clone = useCloneCycle(project.id, cycle.id);
  const [name, setName] = useState(`Copy of ${cycle.name}`);
  const [only, setOnly] = useState<("failed" | "blocked" | "not_run")[]>([]);
  const [result, setResult] = useState<CycleCreateResponse | null>(null);
  const fieldError =
    clone.error instanceof ApiError
      ? clone.error.code === "name_taken"
        ? (clone.error.detail ?? "A cycle with this name already exists")
        : clone.error.errors.find((e) => e.field.startsWith("name"))?.message
      : undefined;

  if (result)
    return (
      <Dialog
        open
        onOpenChange={(o) => {
          if (!o) onClose();
        }}
        title={`${result.cycle.key} created`}
        description={result.cycle.name}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            <Button
              onClick={() => {
                onOpen(result.cycle.key);
              }}
            >
              Open cycle
            </Button>
          </>
        }
      >
        {result.runs_pending ? (
          <p role="status" className="text-[13px] text-ink-secondary">
            Runs are being created in the background.
          </p>
        ) : (
          <AddResult added={result.added} skipped={result.skipped} noun="runs" />
        )}
      </Dialog>
    );

  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={`Clone ${cycle.key}`}
      description="The new cycle gets the same cases at their latest approved versions, with no results."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="clone-cycle" disabled={clone.isPending || name.trim().length < 3}>
            Clone
          </Button>
        </>
      }
    >
      <form
        id="clone-cycle"
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          clone.mutate(
            { name: name.trim(), only_statuses: only.length ? only : null },
            { onSuccess: setResult },
          );
        }}
      >
        <Field label="Name" required error={fieldError}>
          {(p) => (
            <Input
              {...p}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          )}
        </Field>
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium text-ink">Only runs that are</legend>
          <div className="flex flex-wrap gap-4 text-[13px]">
            {CLONE_STATUSES.map(([value, label]) => (
              <label key={value} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={only.includes(value)}
                  onChange={(e) => {
                    setOnly((cur) => (e.target.checked ? [...cur, value] : cur.filter((x) => x !== value)));
                  }}
                />
                {label}
              </label>
            ))}
          </div>
          <p className="mt-1 text-xs text-ink-muted">Leave all unchecked to clone every run.</p>
        </fieldset>
        {clone.error && !fieldError ? (
          <p role="alert" className="text-[13px] text-danger">
            {errorMessage(clone.error)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

/**
 * Assign runs (US-082, TCMS-055): to a tester or back to the pool. Without a selection it assigns
 * every run of a folder ("assign by folder").
 */
export function AssignDialog({
  title,
  executors,
  folders,
  byFolder,
  pending,
  error,
  onAssign,
  onClose,
}: {
  title: string;
  executors: ProjectMember[];
  folders: Folder[];
  byFolder: boolean;
  pending: boolean;
  error: unknown;
  onAssign: (assigneeId: string | null, folderId: string | null) => void;
  onClose: () => void;
}) {
  const [assignee, setAssignee] = useState("");
  const [folder, setFolder] = useState("");
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={pending || (byFolder && !folder)}
            onClick={() => {
              onAssign(assignee === "" ? null : assignee, byFolder ? folder : null);
            }}
          >
            Assign
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        {byFolder ? (
          <Field label="Folder" required hint="Every run of this folder and its subfolders.">
            {(p) => (
              <Select
                {...p}
                value={folder}
                onChange={(e) => {
                  setFolder(e.target.value);
                }}
              >
                <option value="">Choose a folder…</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {`${"\u00a0\u00a0".repeat(f.depth - 1)}${f.name}`}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        ) : null}
        <Field label="Assignee">
          {(p) => (
            <Select
              {...p}
              value={assignee}
              onChange={(e) => {
                setAssignee(e.target.value);
              }}
            >
              <option value="">— pool (unassigned) —</option>
              {executors.map((m) => (
                <option key={m.user.id} value={m.user.id}>
                  {m.user.display_name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {error ? (
          <p role="alert" className="text-[13px] text-danger">
            {errorMessage(error)}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
