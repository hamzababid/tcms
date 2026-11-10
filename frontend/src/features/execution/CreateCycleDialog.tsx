import { useState, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { useEnvironments, useMembers, useReleases, type Project } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { FormError } from "@/features/auth/AuthCard";
import { ChipPicker } from "@/features/planning/PlanForm";
import { usePlans } from "@/features/planning/api";
import { useFolders, useTags } from "@/features/testdesign/api";
import {
  AddResult,
  CaseSelector,
  emptySelection,
  selectionSize,
  type CaseSelection,
} from "@/features/testdesign/CaseSelector";
import { PRIORITIES, PRIORITY_LABELS } from "@/features/testdesign/labels";

import { useCreateCycle, useExecutors, type CycleCreate, type CycleCreateResponse } from "./api";

type Source = "plan" | "repository" | "none";

/** Prefill when opened from a plan (plan detail › Cycles › Create cycle, docs/07 §5.7). */
export interface CycleDefaults {
  planId: string;
  name: string;
  releaseId: string | null;
}

/**
 * New cycle (docs/07 §5.8; US-080, FR-EXE-001/002): 1 Basics, 2 Cases from a plan (narrowed by
 * priority, tag, folder) or from the repository, 3 Default assignee. After creating, the result
 * lists skipped cases with reasons (AC-PLN-01).
 */
export function CreateCycleDialog({
  project,
  defaults,
  onClose,
  onOpen,
}: {
  project: Project;
  defaults?: CycleDefaults;
  onClose: () => void;
  onOpen: (key: string) => void;
}) {
  const create = useCreateCycle(project.id);
  const environments = useEnvironments(project.id);
  const releases = useReleases(project.id);
  const members = useMembers(project.id);
  const executors = useExecutors(members.data ?? []);
  const plans = usePlans(project.id, { page: 1, page_size: 200, sort: "-key" });
  const folders = useFolders(project.id, false);
  const tags = useTags(project.id);

  const [name, setName] = useState(defaults?.name ?? "");
  const [releaseId, setReleaseId] = useState(defaults?.releaseId ?? "");
  const [environmentId, setEnvironmentId] = useState("");
  const [build, setBuild] = useState("");
  const [startDate, setStartDate] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState<Source>(defaults ? "plan" : "repository");
  const [planId, setPlanId] = useState(defaults?.planId ?? "");
  const [priorities, setPriorities] = useState<string[]>([]);
  const [planTags, setPlanTags] = useState<string[]>([]);
  const [planFolders, setPlanFolders] = useState<string[]>([]);
  const [selection, setSelection] = useState<CaseSelection>(emptySelection);
  const [assignee, setAssignee] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<CycleCreateResponse | null>(null);

  const activeEnvs = (environments.data ?? []).filter((e) => !e.archived);
  const planOptions = (plans.data?.items ?? []).filter((p) => !p.archived);

  const submit = async () => {
    setFormError(null);
    const local: Record<string, string> = {};
    const n = name.trim().length;
    if (n < 3 || n > 120) local.name = "Use 3 to 120 characters";
    if (!environmentId) local.environment_id = "Choose an environment";
    if (source === "plan" && !planId) local.plan_id = "Choose a plan";
    if (startDate && dueDate && dueDate < startDate) local.due_date = "The due date is before the start";
    setErrors(local);
    if (Object.keys(local).length) return;
    const body: CycleCreate = {
      name: name.trim(),
      environment_id: environmentId,
      release_id: releaseId || null,
      build: build.trim() || null,
      start_date: startDate || null,
      due_date: dueDate || null,
      description: description.trim() || null,
      default_assignee_id: assignee || null,
      ...(source === "plan" ? { plan_id: planId } : {}),
      selection:
        source === "plan"
          ? {
              from_plan: true,
              case_ids: [],
              folder_ids: planFolders,
              tags: planTags,
              priorities: priorities as ("critical" | "high" | "medium" | "low")[],
            }
          : source === "repository"
            ? { from_plan: false, ...selection, priorities: [] }
            : { from_plan: false, case_ids: [], folder_ids: [], tags: [], priorities: [] },
    };
    try {
      setResult(await create.mutateAsync(body));
    } catch (e) {
      if (e instanceof ApiError && e.code === "name_taken")
        setErrors({ name: e.detail ?? "A cycle with this name already exists" });
      else if (e instanceof ApiError && e.errors.length) {
        setErrors(
          Object.fromEntries(e.errors.map((fe) => [fe.field.split(/[.[]/)[0] ?? fe.field, fe.message])),
        );
        setFormError(e.detail);
      } else setFormError(e instanceof ApiError ? (e.detail ?? e.code) : "Could not create the cycle");
    }
  };

  if (result) {
    const key = result.cycle.key;
    return (
      <Dialog
        open
        onOpenChange={(o) => {
          if (!o) onClose();
        }}
        title={`${key} created`}
        description={result.cycle.name}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            <Button
              onClick={() => {
                onOpen(key);
              }}
            >
              Open cycle
            </Button>
          </>
        }
      >
        {result.runs_pending ? (
          <p role="status" className="text-[13px] text-ink-secondary">
            The cycle is large, so its runs are being created in the background. The cycle fills in shortly.
          </p>
        ) : (
          <AddResult added={result.added} skipped={result.skipped} noun="runs" />
        )}
      </Dialog>
    );
  }

  return (
    <Dialog
      open
      wide
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="New cycle"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-cycle" disabled={create.isPending}>
            Create
          </Button>
        </>
      }
    >
      <form
        id="create-cycle"
        noValidate
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <FormError message={formError} />
        <Step n={1} title="Basics">
          <Field label="Name" required error={errors.name}>
            {(p) => (
              <Input
                {...p}
                value={name}
                placeholder="e.g. Regression Cycle 01"
                onChange={(e) => {
                  setName(e.target.value);
                }}
              />
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Release" error={errors.release_id}>
              {(p) => (
                <Select
                  {...p}
                  value={releaseId}
                  onChange={(e) => {
                    setReleaseId(e.target.value);
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
            <Field label="Environment" required error={errors.environment_id}>
              {(p) => (
                <Select
                  {...p}
                  value={environmentId}
                  onChange={(e) => {
                    setEnvironmentId(e.target.value);
                  }}
                >
                  <option value="">Choose an environment…</option>
                  {activeEnvs.map((e) => (
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
                  value={build}
                  placeholder="e.g. 2.5.0-rc1"
                  onChange={(e) => {
                    setBuild(e.target.value);
                  }}
                />
              )}
            </Field>
            <Field label="Start" error={errors.start_date}>
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  value={startDate}
                  onChange={(e) => {
                    setStartDate(e.target.value);
                  }}
                />
              )}
            </Field>
            <Field label="Due" error={errors.due_date}>
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  value={dueDate}
                  onChange={(e) => {
                    setDueDate(e.target.value);
                  }}
                />
              )}
            </Field>
          </div>
          <Field label="Description" error={errors.description}>
            {(p) => (
              <Textarea
                {...p}
                rows={2}
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                }}
              />
            )}
          </Field>
        </Step>

        <Step n={2} title="Cases">
          <fieldset className="grid gap-3">
            <legend className="sr-only">Where the cases come from</legend>
            <Radio
              name="source"
              checked={source === "plan"}
              onChange={() => {
                setSource("plan");
              }}
            >
              From plan
            </Radio>
            {source === "plan" ? (
              <div className="ml-6 grid gap-3">
                <Field label="Plan" required error={errors.plan_id}>
                  {(p) => (
                    <Select
                      {...p}
                      value={planId}
                      onChange={(e) => {
                        setPlanId(e.target.value);
                      }}
                    >
                      <option value="">Choose a plan…</option>
                      {planOptions.map((pl) => (
                        <option key={pl.id} value={pl.id}>
                          {pl.key} · {pl.name} ({pl.case_count} cases)
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                {plans.data && plans.data.total > plans.data.items.length ? (
                  <p className="text-xs text-ink-secondary">
                    The newest {plans.data.items.length} of {plans.data.total.toLocaleString()} plans are
                    listed. For an older plan, create the cycle from the plan&apos;s page.
                  </p>
                ) : null}
                <p className="text-xs text-ink-muted">Optionally narrow the plan&apos;s cases:</p>
                <ChipPicker
                  legend="Priority"
                  options={PRIORITIES.map((p) => ({ id: p, label: PRIORITY_LABELS[p] ?? p }))}
                  value={priorities}
                  onChange={setPriorities}
                  empty=""
                />
                <ChipPicker
                  legend="Tag"
                  options={(tags.data ?? []).map((t) => ({ id: t.name, label: t.name }))}
                  value={planTags}
                  onChange={setPlanTags}
                  empty="No tags yet."
                />
                <ChipPicker
                  legend="Folder"
                  options={(folders.data ?? []).map((f) => ({ id: f.id, label: f.name }))}
                  value={planFolders}
                  onChange={setPlanFolders}
                  empty="No folders yet."
                />
              </div>
            ) : null}
            <Radio
              name="source"
              checked={source === "repository"}
              onChange={() => {
                setSource("repository");
              }}
            >
              From repository
            </Radio>
            {source === "repository" ? (
              <div className="ml-6">
                <CaseSelector projectId={project.id} value={selection} onChange={setSelection} />
                {selectionSize(selection) === 0 ? (
                  <p className="mt-1 text-xs text-ink-muted">With nothing selected the cycle starts empty.</p>
                ) : null}
              </div>
            ) : null}
            <Radio
              name="source"
              checked={source === "none"}
              onChange={() => {
                setSource("none");
              }}
            >
              No cases yet (add them from the cycle)
            </Radio>
          </fieldset>
          <p className="text-xs text-ink-muted">
            Archived, deprecated and unapproved cases are skipped; you see which after creating.
          </p>
        </Step>

        <Step n={3} title="Assign">
          <Field
            label="Default assignee"
            hint="Every new run goes to this tester. Assign later in the cycle."
          >
            {(p) => (
              <Select
                {...p}
                value={assignee}
                onChange={(e) => {
                  setAssignee(e.target.value);
                }}
              >
                <option value="">— leave in pool —</option>
                {executors.map((m) => (
                  <option key={m.user.id} value={m.user.id}>
                    {m.user.display_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </Step>
      </form>
    </Dialog>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="grid grid-cols-[28px_minmax(0,1fr)] gap-x-3">
      <span
        aria-hidden="true"
        className="mt-0.5 flex size-6 items-center justify-center rounded-full bg-accent-tint text-xs font-semibold text-accent-ink"
      >
        {n}
      </span>
      <div className="grid gap-4">
        <h3 className="text-[13.5px] font-semibold text-ink">{title}</h3>
        {children}
      </div>
    </section>
  );
}

function Radio({
  name,
  checked,
  onChange,
  children,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  children: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[13px] font-medium text-ink">
      <input type="radio" name={name} checked={checked} onChange={onChange} />
      {children}
    </label>
  );
}
