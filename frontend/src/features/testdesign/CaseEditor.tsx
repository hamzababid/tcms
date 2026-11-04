import { useMutation } from "@tanstack/react-query";
import { useBlocker } from "@tanstack/react-router";
import { Info } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
} from "react";

import { api, ApiError } from "@/api/client";
import type { Me, Project, ProjectMember } from "@/api/queries";
import { ConflictDialog } from "@/components/common/dialogs";
import { errorMessage, useToast } from "@/components/common/feedback";
import { MarkdownEditor } from "@/components/common/Markdown";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/field";
import { formatDateTime } from "@/lib/format";

import {
  emptyToNull,
  uploadAttachment,
  useInvalidateCase,
  useReviewers,
  type CaseRead,
  type ContentIn,
  type Folder,
  type Tag,
} from "./api";
import { AUTOMATION, CASE_TYPES, PRIORITY_LABELS, TECHNIQUES } from "./labels";
import { AttachmentList } from "./AttachmentList";
import { newStep, StepGrid, type StepDraft } from "./StepGrid";

interface Draft {
  format: "steps" | "text";
  title: string;
  description: string;
  preconditions: string;
  test_data: string;
  expected_result: string;
  postconditions: string;
  text_body: string;
  steps: StepDraft[];
  folder_id: string;
  type: string;
  design_technique: string;
  priority: string;
  owner_id: string;
  reviewer_id: string;
  tags: string[];
  automation_status: string;
  automation_keys: string;
  estimated_minutes: string;
  change_note: string;
}

function fromCase(c: CaseRead): Draft {
  const v = c.version;
  return {
    format: v.format === "text" ? "text" : "steps",
    title: v.title,
    description: v.description ?? "",
    preconditions: v.preconditions ?? "",
    test_data: v.test_data ?? "",
    expected_result: v.expected_result ?? "",
    postconditions: v.postconditions ?? "",
    text_body: v.text_body ?? "",
    steps: v.steps.length
      ? v.steps.map((s) =>
          newStep({
            id: s.id,
            action: s.action,
            expected_result: s.expected_result ?? "",
            data: s.data ?? "",
          }),
        )
      : [newStep()],
    folder_id: c.folder.id,
    type: c.type,
    design_technique: c.design_technique ?? "",
    priority: c.priority,
    owner_id: c.owner?.id ?? "",
    reviewer_id: c.reviewer?.id ?? "",
    tags: c.tags,
    automation_status: c.automation_status,
    automation_keys: c.automation_keys.join("\n"),
    estimated_minutes: c.estimated_minutes === null ? "" : String(c.estimated_minutes),
    change_note: "",
  };
}

function blank(folderId: string, ownerId: string, keep?: Draft): Draft {
  return {
    format: keep?.format ?? "steps",
    title: "",
    description: "",
    preconditions: "",
    test_data: "",
    expected_result: "",
    postconditions: "",
    text_body: "",
    steps: [newStep()],
    folder_id: keep?.folder_id ?? folderId,
    type: keep?.type ?? "functional",
    design_technique: keep?.design_technique ?? "",
    priority: keep?.priority ?? "medium",
    owner_id: keep?.owner_id ?? ownerId,
    reviewer_id: keep?.reviewer_id ?? "",
    tags: keep?.tags ?? [],
    automation_status: keep?.automation_status ?? "manual",
    automation_keys: "",
    estimated_minutes: keep?.estimated_minutes ?? "",
    change_note: "",
  };
}

function content(d: Draft): ContentIn {
  return {
    format: d.format,
    title: d.title.trim(),
    description: emptyToNull(d.description),
    preconditions: emptyToNull(d.preconditions),
    test_data: emptyToNull(d.test_data),
    expected_result: emptyToNull(d.expected_result),
    postconditions: emptyToNull(d.postconditions),
    text_body: d.format === "text" ? emptyToNull(d.text_body) : null,
    steps:
      d.format === "steps"
        ? d.steps
            .filter((s) => s.action.trim() || s.expected_result.trim() || s.data.trim())
            .map((s) => ({
              action: s.action,
              expected_result: emptyToNull(s.expected_result),
              data: emptyToNull(s.data),
            }))
        : [],
  };
}

function metadata(d: Draft) {
  return {
    folder_id: d.folder_id,
    type: d.type as CaseRead["type"],
    design_technique: (d.design_technique || null) as CaseRead["design_technique"],
    priority: d.priority as CaseRead["priority"],
    owner_id: d.owner_id || null,
    reviewer_id: d.reviewer_id || null,
    tags: d.tags,
    automation_status: d.automation_status as CaseRead["automation_status"],
    automation_keys: d.automation_keys
      .split("\n")
      .map((k) => k.trim())
      .filter(Boolean),
    estimated_minutes: d.estimated_minutes.trim() === "" ? null : Number(d.estimated_minutes),
  };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function validate(d: Draft): {
  title?: string;
  steps: Record<number, string>;
  text_body?: string;
  estimate?: string;
} {
  const out: ReturnType<typeof validate> = { steps: {} };
  const t = d.title.trim();
  if (t.length < 3 || t.length > 255) out.title = "Title must be 3–255 characters";
  if (d.format === "steps") {
    const filled = d.steps.filter((s) => s.action.trim() || s.expected_result.trim() || s.data.trim());
    if (filled.length === 0) out.steps[0] = "Add at least one step";
    d.steps.forEach((s, i) => {
      if (!s.action.trim() && (s.expected_result.trim() || s.data.trim()))
        out.steps[i] = "Action is required";
    });
  } else if (!d.text_body.trim()) out.text_body = "Describe the procedure";
  const est = d.estimated_minutes.trim();
  if (est && (!/^\d+$/.test(est) || Number(est) > 1440)) out.estimate = "Whole minutes, 0–1440";
  return out;
}

const hasErrors = (e: ReturnType<typeof validate>) =>
  Boolean(e.title || e.text_body || e.estimate || Object.keys(e.steps).length);

const draftKey = (projectId: string, caseId: string | null) =>
  `assay.caseDraft.${projectId}.${caseId ?? "new"}`;

interface StoredDraft {
  savedAt: string;
  basedOn: number | null;
  draft: Draft;
}

function readDraft(key: string): StoredDraft | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as StoredDraft) : null;
  } catch {
    return null;
  }
}

function writeDraft(key: string, value: StoredDraft | null) {
  try {
    if (value) localStorage.setItem(key, JSON.stringify(value));
    else localStorage.removeItem(key);
  } catch {
    /* storage unavailable: no local draft */
  }
}

/** Case editor (docs/07 §5.5; US-050…052). */
export function CaseEditor({
  project,
  me,
  existing: latest,
  initialFolderId,
  folders,
  members,
  tags,
  onSaved,
  onCancel,
  onReload,
}: {
  project: Project;
  me: Me;
  existing: CaseRead | null;
  initialFolderId: string;
  folders: Folder[];
  members: ProjectMember[];
  tags: Tag[];
  onSaved: (saved: CaseRead, next: "detail" | "new") => void;
  onCancel: () => void;
  onReload: () => void;
}) {
  const toast = useToast();
  const invalidate = useInvalidateCase();
  // The version being edited is pinned at mount: a background refetch must neither reset the
  // draft nor move the row_version the save is based on (BR-25). Reload remounts the editor.
  const [existing] = useState(latest);
  const storageKey = draftKey(project.id, existing?.id ?? null);
  // The route remounts the editor (key) when the case's row_version changes.
  const [base, setBase] = useState<Draft>(() =>
    existing ? fromCase(existing) : blank(initialFolderId, me.user.id),
  );
  const [draft, setDraft] = useState<Draft>(base);
  const byStep = useMemo(
    () => Object.fromEntries((latest?.version.steps ?? []).map((s) => [s.id, s.attachments])),
    [latest],
  );
  const [restored, setRestored] = useState<StoredDraft | null>(() => {
    const stored = readDraft(storageKey);
    return stored && (!existing || stored.basedOn === existing.row_version) ? stored : null;
  });
  const [showData, setShowData] = useState(() => base.steps.some((s) => s.data.trim() !== ""));
  const [touched, setTouched] = useState(false);
  const [lastLocal, setLastLocal] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState("");
  const reviewers = useReviewers(members);
  const errors = validate(draft);
  const strip = (d: Draft) => ({
    ...d,
    steps: d.steps.map((s) => ({
      id: s.id,
      action: s.action,
      expected_result: s.expected_result,
      data: s.data,
    })),
  });
  const dirty = !same(strip(draft), strip(base));
  const titleRef = useRef<HTMLInputElement>(null);
  // A new case opens with the title focused for keyboard authoring (NFR-UX-01).
  useEffect(() => {
    if (!existing) titleRef.current?.focus();
  }, [existing]);
  const draftRef = useRef(draft);
  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  // Local draft every 10 s (docs/07 §5.5)
  useEffect(() => {
    if (!dirty) return;
    const t = window.setInterval(() => {
      const savedAt = new Date().toISOString();
      writeDraft(storageKey, { savedAt, basedOn: existing?.row_version ?? null, draft: draftRef.current });
      setLastLocal(savedAt);
    }, 10_000);
    return () => {
      window.clearInterval(t);
    };
  }, [dirty, storageKey, existing?.row_version]);

  const save = useMutation({
    mutationFn: async (): Promise<CaseRead> => {
      const body = content(draft);
      const meta = metadata(draft);
      if (!existing) {
        const { data } = await api.POST("/api/v1/projects/{project_id}/test-cases", {
          params: { path: { project_id: project.id } },
          body: { ...meta, content: body },
        });
        if (!data) throw new Error("empty response");
        return data.case;
      }
      let rv = existing.row_version;
      let latest = existing;
      const baseMeta = metadata(base);
      const metaChanges = Object.fromEntries(
        Object.entries(meta).filter(([k, v]) => !same(v, baseMeta[k as keyof typeof baseMeta])),
      );
      if (Object.keys(metaChanges).length) {
        const { data } = await api.PATCH("/api/v1/test-cases/{case_id}", {
          params: { path: { case_id: existing.id } },
          body: { ...metaChanges, row_version: rv },
        });
        if (data) {
          latest = data;
          rv = data.row_version;
        }
      }
      if (!same(body, content(base))) {
        const { data } = await api.PUT("/api/v1/test-cases/{case_id}/content", {
          params: { path: { case_id: existing.id } },
          body: { content: body, change_note: emptyToNull(draft.change_note), row_version: rv },
        });
        if (data) latest = data.case;
      }
      return latest;
    },
  });

  // Unsaved-changes guard (docs/07 §5.5). Read through a ref: navigation after a save happens
  // before the next render.
  const guard = useRef({ dirty, saved: false });
  useEffect(() => {
    guard.current.dirty = dirty;
  }, [dirty]);
  useBlocker({
    shouldBlockFn: () => {
      if (!guard.current.dirty || guard.current.saved) return false;
      return !window.confirm("You have unsaved changes. Leave without saving?");
    },
    enableBeforeUnload: () => guard.current.dirty && !guard.current.saved,
  });

  const submit = useCallback(
    (next: "detail" | "new") => {
      setTouched(true);
      if (hasErrors(validate(draftRef.current)) || save.isPending) return;
      save.mutate(undefined, {
        onSuccess: (saved) => {
          guard.current.saved = true;
          writeDraft(storageKey, null);
          invalidate(project.id, saved.id);
          toast(existing ? `Saved ${saved.key} · v${saved.latest_version_no}` : `Created ${saved.key}`);
          if (next === "new") {
            save.reset();
            const next = blank(initialFolderId, me.user.id, draftRef.current);
            setBase(next);
            setDraft(next);
            guard.current = { dirty: false, saved: false };
            setTouched(false);
          }
          onSaved(saved, next);
        },
      });
    },
    [save, storageKey, invalidate, project.id, toast, existing, initialFolderId, me.user.id, onSaved],
  );

  // Ctrl+S save, Ctrl+Shift+S save & new
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        submit(e.shiftKey ? "new" : "detail");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [submit]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setDraft((d) => ({ ...d, [k]: v }));
  };
  const showErr = touched ? errors : { steps: {} as Record<number, string> };
  const serverError =
    save.error instanceof ApiError && save.error.code !== "stale_row_version"
      ? save.error
      : save.error && !(save.error instanceof ApiError)
        ? save.error
        : null;
  const approval = project.settings.approval_required;
  const nextVersion = (existing?.latest_version_no ?? 0) + 1;
  const contentChanged = existing ? !same(content(draft), content(base)) : true;
  const addTag = (raw: string) => {
    const t = raw.trim().toLowerCase();
    if (t && !draft.tags.includes(t)) set("tags", [...draft.tags, t]);
    setTagInput("");
  };
  const fieldErrors = serverError instanceof ApiError ? serverError.errors : [];
  const pasteUpload = existing
    ? async (file: File) => {
        const a = await uploadAttachment("test_case", existing.id, file);
        invalidate(project.id, existing.id);
        return `![${a.file_name.replace(/[[\]]/g, "")}](${a.url})`;
      }
    : null;

  return (
    <div className="mx-auto flex max-w-[1280px] flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1">
          {existing ? (
            <p className="text-xs text-ink-secondary">
              <span className="font-mono">{existing.key}</span> · editing v{existing.latest_version_no}
            </p>
          ) : null}
          <h1 className="text-2xl font-semibold text-ink">{existing ? "Edit test case" : "New test case"}</h1>
        </div>
        {lastLocal ? (
          <span className="text-xs text-ink-muted" role="status">
            Draft saved locally {formatDateTime(lastLocal)}
          </span>
        ) : null}
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          variant="secondary"
          disabled={save.isPending}
          onClick={() => {
            submit("new");
          }}
          title="Ctrl+Shift+S"
        >
          Save &amp; new
        </Button>
        <Button
          disabled={save.isPending}
          onClick={() => {
            submit("detail");
          }}
          title="Ctrl+S"
        >
          {existing && contentChanged ? `Save v${nextVersion}` : "Save"}
          <kbd className="rounded bg-[rgb(255_255_255/0.2)] px-1 text-[10px]">Ctrl S</kbd>
        </Button>
      </div>

      {restored ? (
        <div
          role="status"
          className="flex items-center gap-3 rounded-control border border-[var(--status-progress-border)] bg-[var(--status-progress-bg)] px-3 py-2 text-sm text-[var(--status-progress-fg)]"
        >
          <span className="flex-1">You have an unsaved draft from {formatDateTime(restored.savedAt)}.</span>
          <Button
            size="sm"
            onClick={() => {
              setDraft(restored.draft);
              setRestored(null);
            }}
          >
            Restore draft
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              writeDraft(storageKey, null);
              setRestored(null);
            }}
          >
            Discard
          </Button>
        </div>
      ) : null}

      {existing && approval && contentChanged ? (
        <div
          role="status"
          className="flex items-center gap-2 rounded-control border border-[var(--status-progress-border)] bg-[var(--status-progress-bg)] px-3 py-2 text-sm text-[var(--status-progress-fg)]"
        >
          <Info aria-hidden="true" className="size-4" />
          <span>
            Saving creates <strong>v{nextVersion}</strong>.{" "}
            {existing.approved_version_no
              ? `Cycles keep using approved v${existing.approved_version_no} until v${nextVersion} is approved.`
              : "It needs approval before cycles can use it."}
          </span>
        </div>
      ) : null}

      {serverError ? (
        <div
          role="alert"
          className="rounded-control border border-[var(--status-fail-border)] bg-[var(--status-fail-bg)] px-3 py-2 text-sm text-[var(--status-fail-fg)]"
        >
          {errorMessage(serverError)}
          {fieldErrors.length ? (
            <ul className="mt-1 list-disc pl-5">
              {fieldErrors.map((e) => (
                <li key={`${e.field}-${e.code}`}>
                  {e.field}: {e.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <PasteUpload.Provider value={pasteUpload}>
          <section
            aria-label="Content"
            className="flex flex-col gap-4 rounded-card border border-border bg-surface p-5"
          >
            <Field label="Title" required error={showErr.title}>
              {(p) => (
                <Input
                  {...p}
                  ref={titleRef}
                  value={draft.title}
                  maxLength={255}
                  onChange={(e) => {
                    set("title", e.target.value);
                  }}
                />
              )}
            </Field>
            <fieldset className="flex items-center gap-4 text-sm">
              <legend className="mb-1 text-xs font-medium text-ink-secondary">Format</legend>
              {(["steps", "text"] as const).map((f) => (
                <label key={f} className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="format"
                    checked={draft.format === f}
                    onChange={() => {
                      const hasSteps = draft.steps.some((s) => s.action.trim() || s.expected_result.trim());
                      if (
                        f === "text" &&
                        hasSteps &&
                        !window.confirm("Switching to text discards the steps. Continue?")
                      )
                        return;
                      set("format", f);
                    }}
                  />
                  {f === "steps" ? "Steps" : "Text"}
                </label>
              ))}
            </fieldset>
            <p className="-mt-2 text-xs text-ink-muted">
              Text fields support Markdown{existing ? "; paste an image into any of them to attach it" : ""}.
            </p>
            <MdField
              label="Description"
              value={draft.description}
              onChange={(v) => {
                set("description", v);
              }}
            />
            <MdField
              label="Preconditions"
              value={draft.preconditions}
              onChange={(v) => {
                set("preconditions", v);
              }}
            />
            <MdField
              label="Test data"
              value={draft.test_data}
              onChange={(v) => {
                set("test_data", v);
              }}
              placeholder="Accounts, payloads, files…"
            />
            {draft.format === "steps" ? (
              <div>
                <div className="mb-2 flex flex-wrap items-baseline gap-3">
                  <span className="text-xs font-medium text-ink-secondary">Steps *</span>
                  <span className="text-xs text-ink-muted">
                    Enter new step · Tab next cell · Alt ↑↓ reorder · Ctrl D duplicate · Ctrl ⌫ delete · paste
                    rows from a spreadsheet
                  </span>
                  <span className="flex-1" />
                  <Checkbox
                    label="Data column"
                    checked={showData}
                    onChange={(e) => {
                      setShowData(e.target.checked);
                    }}
                  />
                </div>
                <StepGrid
                  steps={draft.steps}
                  onChange={(s) => {
                    set("steps", s);
                  }}
                  showData={showData}
                  errors={showErr.steps}
                  stepAttachments={
                    existing
                      ? {
                          byStep,
                          canUpload: true,
                          maxMb: project.settings.attachment_max_mb,
                          onChanged: () => {
                            invalidate(project.id, existing.id);
                          },
                        }
                      : null
                  }
                />
              </div>
            ) : (
              <MdField
                label="Procedure"
                required
                value={draft.text_body}
                onChange={(v) => {
                  set("text_body", v);
                }}
                error={showErr.text_body}
                rows={8}
              />
            )}
            <MdField
              label="Overall expected result"
              value={draft.expected_result}
              onChange={(v) => {
                set("expected_result", v);
              }}
            />
            <MdField
              label="Postconditions"
              value={draft.postconditions}
              onChange={(v) => {
                set("postconditions", v);
              }}
            />
            {existing ? (
              <Field label="Change note" hint="Shown in the version history">
                {(p) => (
                  <Input
                    {...p}
                    maxLength={500}
                    value={draft.change_note}
                    onChange={(e) => {
                      set("change_note", e.target.value);
                    }}
                  />
                )}
              </Field>
            ) : null}
          </section>
        </PasteUpload.Provider>

        <aside
          aria-label="Properties"
          className="flex flex-col gap-4 self-start rounded-card border border-border bg-surface p-5"
        >
          <h2 className="text-sm font-semibold text-ink">Properties</h2>
          <Field label="Folder" required>
            {(p) => (
              <Select
                {...p}
                value={draft.folder_id}
                onChange={(e) => {
                  set("folder_id", e.target.value);
                }}
              >
                {folders
                  .filter((f) => !f.archived || f.id === draft.folder_id)
                  .map((f) => (
                    <option key={f.id} value={f.id}>
                      {"  ".repeat(f.depth - 1)}
                      {f.name}
                    </option>
                  ))}
              </Select>
            )}
          </Field>
          <EnumField
            label="Type"
            required
            value={draft.type}
            options={CASE_TYPES}
            onChange={(v) => {
              set("type", v);
            }}
          />
          <EnumField
            label="Technique"
            value={draft.design_technique}
            options={TECHNIQUES}
            onChange={(v) => {
              set("design_technique", v);
            }}
            empty="None"
          />
          <EnumField
            label="Priority"
            required
            value={draft.priority}
            options={PRIORITY_LABELS}
            onChange={(v) => {
              set("priority", v);
            }}
          />
          <EnumField
            label="Owner"
            required
            value={draft.owner_id}
            options={Object.fromEntries(members.map((m) => [m.user.id, m.user.display_name]))}
            onChange={(v) => {
              set("owner_id", v);
            }}
          />
          <EnumField
            label="Reviewer"
            value={draft.reviewer_id}
            options={Object.fromEntries(reviewers.map((m) => [m.user.id, m.user.display_name]))}
            onChange={(v) => {
              set("reviewer_id", v);
            }}
            empty="None"
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="tag-input" className="text-xs font-medium text-ink-secondary">
              Tags
            </label>
            <div className="flex flex-wrap items-center gap-1 rounded-control border border-border px-2 py-1.5">
              {draft.tags.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 rounded-full bg-ground px-2 py-0.5 text-xs"
                >
                  {t}
                  <button
                    type="button"
                    aria-label={`Remove tag ${t}`}
                    onClick={() => {
                      set(
                        "tags",
                        draft.tags.filter((x) => x !== t),
                      );
                    }}
                  >
                    ×
                  </button>
                </span>
              ))}
              <input
                id="tag-input"
                list="tag-suggestions"
                value={tagInput}
                placeholder={draft.tags.length >= 20 ? "Max 20 tags" : "Add tag"}
                disabled={draft.tags.length >= 20}
                className="min-w-20 flex-1 bg-transparent text-sm outline-none"
                onChange={(e) => {
                  setTagInput(e.target.value);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault();
                    addTag(tagInput);
                  } else if (e.key === "Backspace" && !tagInput && draft.tags.length) {
                    set("tags", draft.tags.slice(0, -1));
                  }
                }}
                onBlur={() => {
                  if (tagInput) addTag(tagInput);
                }}
              />
              <datalist id="tag-suggestions">
                {tags
                  .filter((t) => !draft.tags.includes(t.name))
                  .map((t) => (
                    <option key={t.id} value={t.name} />
                  ))}
              </datalist>
            </div>
            <p className="text-xs text-ink-muted">
              Lowercase letters, digits and - _ . · new tags are created on save
            </p>
          </div>
          <EnumField
            label="Automation"
            required
            value={draft.automation_status}
            options={AUTOMATION}
            onChange={(v) => {
              set("automation_status", v);
            }}
          />
          <Field label="Automation keys" hint="One per line, unique in the project">
            {(p) => (
              <textarea
                {...p}
                rows={2}
                value={draft.automation_keys}
                onChange={(e) => {
                  set("automation_keys", e.target.value);
                }}
                className="w-full rounded-control border border-border bg-surface px-3 py-2 font-mono text-xs"
              />
            )}
          </Field>
          <Field label="Estimated minutes" error={showErr.estimate}>
            {(p) => (
              <Input
                {...p}
                inputMode="numeric"
                value={draft.estimated_minutes}
                onChange={(e) => {
                  set("estimated_minutes", e.target.value);
                }}
              />
            )}
          </Field>
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-ink-secondary">Attachments</span>
            {latest ? (
              <AttachmentList
                attachments={latest.attachments}
                entityType="test_case"
                entityId={latest.id}
                canUpload
                canRemove={() => true}
                maxMb={project.settings.attachment_max_mb}
                onChanged={() => {
                  invalidate(project.id, latest.id);
                }}
              />
            ) : (
              <p className="text-xs text-ink-muted">Attachments can be added after the case is created.</p>
            )}
          </div>
        </aside>
      </div>
      <ConflictDialog
        error={save.error}
        onClose={() => {
          save.reset();
        }}
        onReload={() => {
          save.reset();
          onReload();
        }}
      />
    </div>
  );
}

/** Uploads a pasted image as a case attachment and returns the Markdown that shows it (US-055). */
const PasteUpload = createContext<((file: File) => Promise<string>) | null>(null);

function MdField({
  label,
  value,
  onChange,
  required,
  error,
  placeholder,
  rows = 2,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  error?: string | undefined;
  placeholder?: string;
  rows?: number;
}) {
  const upload = useContext(PasteUpload);
  const toast = useToast();
  const latest = useRef(value);
  useEffect(() => {
    latest.current = value;
  }, [value]);
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const file = [...e.clipboardData.files].find((f) => f.type.startsWith("image/"));
    if (!upload || !file) return;
    e.preventDefault();
    const at = e.currentTarget.selectionStart;
    upload(file).then(
      (snippet) => {
        const v = latest.current;
        onChange(`${v.slice(0, at)}${snippet}${v.slice(at)}`);
      },
      (err: unknown) => {
        toast(errorMessage(err), "error");
      },
    );
  };
  return (
    <Field label={label} required={Boolean(required)} error={error}>
      {(p) => (
        <MarkdownEditor
          {...p}
          rows={rows}
          value={value}
          {...(placeholder ? { placeholder } : {})}
          onPaste={onPaste}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        />
      )}
    </Field>
  );
}

function EnumField({
  label,
  value,
  options,
  onChange,
  required,
  empty,
}: {
  label: string;
  value: string;
  options: Record<string, string>;
  onChange: (v: string) => void;
  required?: boolean;
  empty?: string;
}) {
  return (
    <Field label={label} required={Boolean(required)}>
      {(p) => (
        <Select
          {...p}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        >
          {empty !== undefined ? <option value="">{empty}</option> : null}
          {Object.entries(options).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}
