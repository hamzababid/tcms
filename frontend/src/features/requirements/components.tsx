import { Link } from "@tanstack/react-router";
import { ExternalLink, FileText, Plus, X } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/client";
import type { Project } from "@/api/queries";
import { errorMessage, useToast } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/field";
import { safeUrl } from "@/features/bugs/api";
import { AddCasesDialog } from "@/features/testdesign/CaseSelector";
import { formatDateTime } from "@/lib/format";

import {
  addPlanRequirements,
  addRequirements,
  linkCaseToRequirements,
  linkCases,
  patchRequirement,
  removePlanRequirement,
  setRequirementArchived,
  unlinkCase,
  useCaseRequirements,
  useInvalidateRequirements,
  useRequirement,
  useRequirements,
  type RequirementRef,
  type TraceCase,
} from "./api";

/** Where requirement links point (docs/02 §4.2; ADR-024 Q2 = a): the requirement address, else the bug one. */
export function requirementTemplate(project: Project): string | null {
  return project.settings.requirement_url_template || project.settings.bug_url_template || null;
}

/** A requirement reference: the reference (opens the team's tool) and its title. */
export function RefLink({
  r,
  title = true,
}: {
  r: Pick<RequirementRef, "reference" | "url" | "title">;
  title?: boolean;
}) {
  const href = safeUrl(r.url);
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <FileText aria-hidden="true" className="size-3.5 shrink-0 text-ink-muted" />
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 font-mono text-[12.5px] font-medium text-link hover:underline"
          title={`Open ${r.reference}`}
          onClick={(e) => {
            e.stopPropagation();
          }}
        >
          {r.reference}
          <ExternalLink aria-hidden="true" className="size-3" />
        </a>
      ) : (
        <span className="font-mono text-[12.5px] font-medium">{r.reference}</span>
      )}
      {title && r.title ? (
        <span className="truncate text-ink-secondary" title={r.title}>
          {r.title}
        </span>
      ) : null}
    </span>
  );
}

/** "Paste many" (R-120): `SPK-120, SPK-121` or one per line; a single one may get a link and title. */
export function AddRequirementsDialog({ project, onClose }: { project: Project; onClose: () => void }) {
  const toast = useToast();
  const invalidate = useInvalidateRequirements();
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const many = text.split(/[\s,;]+/).filter(Boolean).length > 1;
  const fieldError = (name: string) =>
    error instanceof ApiError ? error.errors.find((x) => x.field.startsWith(name))?.message : undefined;
  const template = requirementTemplate(project);
  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      const out = await addRequirements(project.id, text, many ? undefined : url, many ? undefined : title);
      invalidate();
      const reused = out.references.length - out.created;
      toast(`Added ${out.created}${reused ? ` · ${reused} already there` : ""}`);
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  };
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="Add requirements"
      description="References to requirements or stories in your team's tool. Assay links them to test cases."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="add-requirements" disabled={pending || !text.trim()}>
            Add
          </Button>
        </>
      }
    >
      <form
        id="add-requirements"
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field
          label="References"
          required
          hint="One or many, separated by commas, spaces or new lines (e.g. SPK-120, SPK-121)"
          error={fieldError("references")}
        >
          {(p) => (
            <Textarea
              {...p}
              rows={3}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
              }}
            />
          )}
        </Field>
        {!many ? (
          <>
            <Field
              label="Link"
              hint={
                template ? "Leave empty to use the project's requirement address" : "Optional, http(s) only"
              }
              error={fieldError("url")}
            >
              {(p) => (
                <Input
                  {...p}
                  type="url"
                  value={url}
                  placeholder={
                    template && text.trim()
                      ? template.replace("{ref}", encodeURIComponent(text.trim()))
                      : "https://"
                  }
                  onChange={(e) => {
                    setUrl(e.target.value);
                  }}
                />
              )}
            </Field>
            <Field label="Title" hint="Optional short summary" error={fieldError("title")}>
              {(p) => (
                <Input
                  {...p}
                  value={title}
                  maxLength={255}
                  onChange={(e) => {
                    setTitle(e.target.value);
                  }}
                />
              )}
            </Field>
          </>
        ) : null}
        {error instanceof ApiError && error.errors.length === 0 ? (
          <p role="alert" className="text-[13px] text-danger">
            {errorMessage(error)}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

/** A case's latest result in a matrix or detail row. */
export function LatestMark({ c, project }: { c: TraceCase; project: Project }) {
  const status = c.latest?.status ?? "not_run";
  return (
    <Link
      to="/p/$projectKey/cases/$caseKey"
      params={{ projectKey: project.key, caseKey: c.key }}
      className="inline-flex items-center gap-1 hover:underline"
      title={
        c.latest
          ? `${c.key}: ${status.replace("_", " ")} in ${c.latest.cycle_key} · ${formatDateTime(c.latest.finished_at)}`
          : `${c.key}: no result in the release`
      }
    >
      <span className="font-mono text-[12px]">{c.key.split("-").slice(-2).join("-")}</span>
      <StatusBadge kind="execution" status={status} compact />
    </Link>
  );
}

/** One reference: its cases with their latest result, plans, edit, archive and Link cases (R-120/121). */
export function RequirementDialog({
  project,
  refId,
  releaseId,
  canManage,
  canLink,
  onClose,
}: {
  project: Project;
  refId: string | null;
  releaseId: string | null;
  canManage: boolean;
  canLink: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const invalidate = useInvalidateRequirements();
  const detail = useRequirement(refId, releaseId);
  const [picking, setPicking] = useState(false);
  const [editing, setEditing] = useState(false);
  const d = detail.data;
  const run = (p: Promise<unknown>, message: string) => {
    p.then(() => {
      invalidate();
      toast(message);
    }).catch((e: unknown) => {
      toast(errorMessage(e), "error");
    });
  };
  return (
    <Dialog
      open={refId !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={d?.reference ?? "Requirement"}
      description={d?.title ?? undefined}
      wide
      footer={
        d ? (
          <>
            {canManage ? (
              <Button
                variant="secondary"
                onClick={() => {
                  run(setRequirementArchived(d.id, !d.archived), d.archived ? "Restored" : "Archived");
                }}
              >
                {d.archived ? "Restore" : "Archive"}
              </Button>
            ) : null}
            {canManage ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setEditing(true);
                }}
              >
                Edit
              </Button>
            ) : null}
            {canLink ? (
              <Button
                onClick={() => {
                  setPicking(true);
                }}
              >
                <Plus aria-hidden="true" className="size-4" /> Link cases
              </Button>
            ) : null}
          </>
        ) : undefined
      }
    >
      {d ? (
        <div className="grid gap-4 text-[13px]">
          <p className="flex flex-wrap items-center gap-2">
            <RefLink r={d} title={false} />
            {d.status ? <StatusBadge kind="requirement" status={d.status} /> : null}
            {d.archived ? <span className="text-ink-muted">Archived</span> : null}
          </p>
          <section aria-label="Linked cases">
            <h3 className="mb-1.5 font-semibold text-ink">Cases ({d.cases.length})</h3>
            {d.cases.length === 0 ? (
              <p className="text-ink-secondary">No case covers this requirement yet.</p>
            ) : (
              <ul className="grid gap-1">
                {d.cases.map((c) => (
                  <li key={c.id} className="flex items-center gap-2">
                    <Link
                      to="/p/$projectKey/cases/$caseKey"
                      params={{ projectKey: project.key, caseKey: c.key }}
                      className="font-mono text-link hover:underline"
                    >
                      {c.key}
                    </Link>
                    <span className="min-w-0 flex-1 truncate">{c.title}</span>
                    <StatusBadge kind="execution" status={c.latest?.status ?? "not_run"} />
                    <span className="w-40 text-ink-secondary">
                      {c.latest
                        ? `${c.latest.cycle_key} · ${formatDateTime(c.latest.finished_at)}`
                        : "No result"}
                    </span>
                    {canLink ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Unlink ${c.key}`}
                        onClick={() => {
                          run(unlinkCase(d.id, c.id), `Unlinked ${c.key}`);
                        }}
                      >
                        <X aria-hidden="true" className="size-3.5" />
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-label="Plans">
            <h3 className="mb-1.5 font-semibold text-ink">Plans</h3>
            {d.plans.length === 0 ? (
              <p className="text-ink-secondary">Not listed on a plan.</p>
            ) : (
              <p className="flex flex-wrap gap-2">
                {d.plans.map((p) => (
                  <Link
                    key={p.id}
                    to="/p/$projectKey/plans/$planKey"
                    params={{ projectKey: project.key, planKey: p.key }}
                    className="text-link hover:underline"
                  >
                    {p.key} · {p.name}
                  </Link>
                ))}
              </p>
            )}
          </section>
        </div>
      ) : (
        <p className="text-[13px] text-ink-secondary">Loading…</p>
      )}
      {picking && d ? (
        <AddCasesDialog
          title={`Link cases to ${d.reference}`}
          projectId={project.id}
          pending={false}
          error={null}
          noun="cases"
          onAdd={async (sel) => {
            const r = await linkCases(d.id, sel);
            invalidate();
            return { added: r.count, skipped: [] };
          }}
          onClose={() => {
            setPicking(false);
          }}
        />
      ) : null}
      {editing && d ? (
        <EditRequirementDialog
          r={d}
          onClose={() => {
            setEditing(false);
          }}
        />
      ) : null}
    </Dialog>
  );
}

function EditRequirementDialog({ r, onClose }: { r: RequirementRef; onClose: () => void }) {
  const invalidate = useInvalidateRequirements();
  const [url, setUrl] = useState(r.url ?? "");
  const [title, setTitle] = useState(r.title ?? "");
  const [error, setError] = useState<unknown>(null);
  const fieldError = (name: string) =>
    error instanceof ApiError ? error.errors.find((x) => x.field === name)?.message : undefined;
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={`Edit ${r.reference}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="edit-requirement">
            Save
          </Button>
        </>
      }
    >
      <form
        id="edit-requirement"
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          patchRequirement(r.id, { url: url.trim() || null, title: title.trim() || null })
            .then(() => {
              invalidate();
              onClose();
            })
            .catch(setError);
        }}
      >
        <Field label="Link" error={fieldError("url")}>
          {(p) => (
            <Input
              {...p}
              type="url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Title" error={fieldError("title")}>
          {(p) => (
            <Input
              {...p}
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
              }}
            />
          )}
        </Field>
      </form>
    </Dialog>
  );
}

/** Link references by text (case page and repository bulk): unknown ones are registered (D12). */
export function LinkRequirementsDialog({
  label,
  onSubmit,
  onClose,
}: {
  label: string;
  onSubmit: (references: string) => Promise<{ count: number; created: number }>;
  onClose: () => void;
}) {
  const toast = useToast();
  const invalidate = useInvalidateRequirements();
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="Link requirements"
      description={label}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="link-requirements" disabled={pending || !text.trim()}>
            Link
          </Button>
        </>
      }
    >
      <form
        id="link-requirements"
        onSubmit={(e) => {
          e.preventDefault();
          setPending(true);
          onSubmit(text)
            .then((r) => {
              invalidate();
              toast(
                `${r.count} ${r.count === 1 ? "link" : "links"} added${r.created ? ` · ${r.created} new` : ""}`,
              );
              onClose();
            })
            .catch(setError)
            .finally(() => {
              setPending(false);
            });
        }}
      >
        <Field
          label="Requirement references"
          required
          hint="e.g. SPK-120, SPK-121 — new references are added to the project"
          error={error instanceof ApiError ? (error.errors[0]?.message ?? errorMessage(error)) : undefined}
        >
          {(p) => (
            <Input
              {...p}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
              }}
            />
          )}
        </Field>
      </form>
    </Dialog>
  );
}

/** Case page "Requirements" tab (R-121). */
export function CaseRequirements({
  caseId,
  caseKey,
  canLink,
}: {
  caseId: string;
  caseKey: string;
  canLink: boolean;
}) {
  const refs = useCaseRequirements(caseId);
  const toast = useToast();
  const invalidate = useInvalidateRequirements();
  const [adding, setAdding] = useState(false);
  const rows = refs.data ?? [];
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <p className="flex-1 text-[13px] text-ink-secondary">
          Requirements this case verifies (kept in your team's tool).
        </p>
        {canLink ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setAdding(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" /> Link requirement
          </Button>
        ) : null}
      </div>
      {refs.isPending ? (
        <p className="text-[13px] text-ink-secondary">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-card border border-dashed border-border px-4 py-6 text-center text-[13px] text-ink-secondary">
          No requirements are linked to this case.
        </p>
      ) : (
        <ul className="grid gap-1.5 text-[13px]">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center gap-2">
              <span className="min-w-0 flex-1">
                <RefLink r={r} />
              </span>
              {r.status ? <StatusBadge kind="requirement" status={r.status} /> : null}
              {canLink ? (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Unlink ${r.reference}`}
                  onClick={() => {
                    unlinkCase(r.id, caseId)
                      .then(() => {
                        invalidate();
                        toast(`Unlinked ${r.reference}`);
                      })
                      .catch((e: unknown) => {
                        toast(errorMessage(e), "error");
                      });
                  }}
                >
                  <X aria-hidden="true" className="size-3.5" />
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {adding ? (
        <LinkRequirementsDialog
          label={`To ${caseKey}`}
          onSubmit={(text) => linkCaseToRequirements(caseId, text)}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}
    </div>
  );
}

/** Plan "Requirements" tab (R-122, L25): references the plan must cover and their status in its release. */
export function PlanRequirements({
  project,
  planId,
  releaseId,
  canManage,
  canLink,
}: {
  project: Project;
  planId: string;
  releaseId: string | null;
  canManage: boolean;
  canLink: boolean;
}) {
  const toast = useToast();
  const invalidate = useInvalidateRequirements();
  const refs = useRequirements(project.id, {
    plan_id: planId,
    ...(releaseId ? { release_id: releaseId } : {}),
    page: 1,
    page_size: 200,
  });
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const rows = refs.data?.items ?? [];
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <p className="flex-1 text-[13px] text-ink-secondary">
          Requirements this plan must cover. Ones with no case show as Not covered
          {releaseId ? " in its release" : ""}.
        </p>
        {canManage ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setAdding(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" /> Add requirements
          </Button>
        ) : null}
      </div>
      {refs.isPending ? (
        <p className="text-[13px] text-ink-secondary">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-card border border-dashed border-border px-4 py-6 text-center text-[13px] text-ink-secondary">
          No requirements on this plan yet.
        </p>
      ) : (
        <table aria-label="Plan requirements" className="w-full text-left text-[13px]">
          <thead className="text-xs text-ink-secondary">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Requirement</th>
              <th className="w-20 py-1.5 pr-3 text-right font-medium">Cases</th>
              <th className="w-40 py-1.5 pr-3 font-medium">Status</th>
              <th className="w-24 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-border">
                <td className="py-2 pr-3">
                  <button
                    type="button"
                    className="min-w-0 text-left hover:underline"
                    onClick={() => {
                      setOpen(r.id);
                    }}
                  >
                    <RefLink r={r} />
                  </button>
                </td>
                <td className="tabular py-2 pr-3 text-right">{r.case_count}</td>
                <td className="py-2 pr-3">
                  {r.status ? <StatusBadge kind="requirement" status={r.status} /> : null}
                </td>
                <td className="py-2 text-right">
                  {canManage ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${r.reference} from the plan`}
                      onClick={() => {
                        removePlanRequirement(planId, r.id)
                          .then(() => {
                            invalidate();
                            toast(`Removed ${r.reference}`);
                          })
                          .catch((e: unknown) => {
                            toast(errorMessage(e), "error");
                          });
                      }}
                    >
                      <X aria-hidden="true" className="size-3.5" />
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {adding ? (
        <LinkRequirementsDialog
          label="References the plan must cover (new ones are added to the project)"
          onSubmit={async (text) => ({ count: (await addPlanRequirements(planId, text)).count, created: 0 })}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}
      <RequirementDialog
        project={project}
        refId={open}
        releaseId={releaseId}
        canManage={false}
        canLink={canLink}
        onClose={() => {
          setOpen(null);
        }}
      />
    </div>
  );
}
