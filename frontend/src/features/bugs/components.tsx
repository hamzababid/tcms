import { Bug, Copy, ExternalLink, MoreHorizontal, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import type { Project } from "@/api/queries";
import { ConfirmDialog } from "@/components/common/dialogs";
import { errorMessage, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/field";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { cn } from "@/lib/utils";

import {
  distinctReferences,
  linkBugToCase,
  linkBugToResult,
  removeBugLink,
  requestRetest,
  safeUrl,
  updateBugLink,
  useCaseBugLinks,
  useCycleBugLinks,
  useInvalidateBugs,
  type BugLink,
  type RetestResponse,
} from "./api";

export interface Tracker {
  name: string;
  template: string | null;
}

export function trackerOf(project: Project): Tracker {
  const s = project.settings;
  return { name: s.bug_tracker_name || "tracker", template: s.bug_url_template ?? null };
}

/** The URL the template would build (shown as the URL placeholder; AC-BUG-02). */
export function templateUrl(t: Tracker, reference: string): string | null {
  const ref = reference.trim();
  if (!t.template || !ref) return null;
  return t.template.replace("{ref}", encodeURIComponent(ref));
}

export type LinkTarget =
  | { kind: "result"; resultId: string; stepId: string | null; label: string; cycleId?: string }
  | { kind: "case"; caseId: string; label: string };

/** Link a bug from the team's tracker (docs/02 §8.2): reference, optional URL and title. */
export function LinkBugDialog({
  target,
  tracker,
  onClose,
  onLinked,
}: {
  target: LinkTarget | null;
  tracker: Tracker;
  onClose: () => void;
  onLinked?: (link: BugLink) => void;
}) {
  const toast = useToast();
  const invalidate = useInvalidateBugs();
  const [reference, setReference] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const recent = useCycleBugLinks(target?.kind === "result" ? target.cycleId : undefined, true);
  const reset = () => {
    setReference("");
    setUrl("");
    setTitle("");
    setError(null);
  };
  const fieldError = (name: string) =>
    error instanceof ApiError ? error.errors.find((x) => x.field === name)?.message : undefined;
  const submit = async () => {
    if (!target || !reference.trim()) return;
    setPending(true);
    setError(null);
    try {
      const body = { reference: reference.trim(), url: url.trim() || null, title: title.trim() || null };
      const link =
        target.kind === "result"
          ? await linkBugToResult(target.resultId, { ...body, step_id: target.stepId })
          : await linkBugToCase(target.caseId, body);
      invalidate();
      toast(`Linked ${link.reference}`);
      reset();
      onClose();
      onLinked?.(link);
    } catch (e) {
      setError(e);
    } finally {
      setPending(false);
    }
  };
  const suggestions = distinctReferences(recent.data ?? []).filter(
    (l) => !reference || l.reference.toUpperCase().includes(reference.trim().toUpperCase()),
  );
  const generic = error instanceof ApiError && error.errors.length === 0 ? errorMessage(error) : null;
  return (
    <Dialog
      open={target !== null}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
      title="Link bug"
      description={target ? `To ${target.label}. The bug itself stays in ${tracker.name}.` : undefined}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button type="submit" form="link-bug" disabled={pending || !reference.trim()}>
            Link bug
          </Button>
        </>
      }
    >
      <form
        id="link-bug"
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field
          label="Bug reference"
          required
          hint="As your tracker writes it, e.g. SPK-431 or #1287"
          error={fieldError("reference")}
        >
          {(p) => (
            <Input
              {...p}
              autoComplete="off"
              value={reference}
              onChange={(e) => {
                setReference(e.target.value);
              }}
            />
          )}
        </Field>
        {suggestions.length ? (
          <div className="flex flex-wrap items-center gap-1.5 text-xs" aria-label="Recent bugs in this cycle">
            <span className="text-ink-secondary">Recent:</span>
            {suggestions.slice(0, 6).map((l) => (
              <button
                key={l.id}
                type="button"
                className="rounded-full border border-border px-2 py-0.5 font-mono hover:bg-surface-muted"
                onClick={() => {
                  setReference(l.reference);
                  if (l.title) setTitle(l.title);
                  if (l.url) setUrl(l.url);
                }}
              >
                {l.reference}
              </button>
            ))}
          </div>
        ) : null}
        <Field
          label="Link"
          hint={
            tracker.template ? "Leave empty to use the project's tracker address" : "Optional, http(s) only"
          }
          error={fieldError("url")}
        >
          {(p) => (
            <Input
              {...p}
              type="url"
              inputMode="url"
              value={url}
              placeholder={templateUrl(tracker, reference) ?? "https://"}
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
        {generic ? (
          <p role="alert" className="text-[13px] text-danger">
            {generic}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}

/** A bug reference: opens the tracker; the menu copies, edits, removes or asks for a retest. */
export function BugChip({
  link,
  project,
  tracker,
  canRetest = false,
  compact = false,
}: {
  link: BugLink;
  project: Project;
  tracker: Tracker;
  canRetest?: boolean;
  compact?: boolean;
}) {
  const toast = useToast();
  const invalidate = useInvalidateBugs();
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [retest, setRetest] = useState(false);
  const href = safeUrl(link.url);
  const label = (
    <>
      <Bug aria-hidden="true" className="size-3" />
      <span className="font-mono">{link.reference}</span>
      {!compact && link.title ? (
        <span className="max-w-48 truncate text-ink-secondary">{link.title}</span>
      ) : null}
    </>
  );
  const chip =
    "inline-flex items-center gap-1 rounded-full border border-[var(--status-fail-bar)] bg-[var(--status-fail-bg)] px-2 py-0.5 text-xs text-[var(--status-fail-fg)]";
  const showMenu = link.can_edit || canRetest;
  return (
    <span className="inline-flex items-center">
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(chip, "hover:underline", showMenu && "rounded-r-none")}
          title={`Open ${link.reference} in ${tracker.name}${link.title ? ` – ${link.title}` : ""}`}
        >
          {label}
        </a>
      ) : (
        <span className={cn(chip, showMenu && "rounded-r-none")} title={link.title ?? link.reference}>
          {label}
        </span>
      )}
      {showMenu ? (
        <Menu>
          <MenuTrigger asChild>
            <button
              type="button"
              aria-label={`Actions for ${link.reference}`}
              className="inline-flex h-[22px] items-center rounded-r-full border border-l-0 border-[var(--status-fail-bar)] bg-[var(--status-fail-bg)] px-1 text-[var(--status-fail-fg)] hover:bg-surface"
            >
              <MoreHorizontal aria-hidden="true" className="size-3" />
            </button>
          </MenuTrigger>
          <MenuContent align="start">
            {href ? (
              <MenuItem asChild>
                <a href={href} target="_blank" rel="noopener noreferrer">
                  <ExternalLink aria-hidden="true" className="size-3.5" /> Open in {tracker.name}
                </a>
              </MenuItem>
            ) : null}
            <MenuItem
              onSelect={() => {
                void navigator.clipboard.writeText(link.reference).then(() => {
                  toast(`Copied ${link.reference}`);
                });
              }}
            >
              <Copy aria-hidden="true" className="size-3.5" /> Copy reference
            </MenuItem>
            {canRetest ? (
              <MenuItem
                onSelect={() => {
                  setRetest(true);
                }}
              >
                <RotateCcw aria-hidden="true" className="size-3.5" /> Ready for retest…
              </MenuItem>
            ) : null}
            {link.can_edit ? (
              <>
                <MenuSeparator />
                <MenuItem
                  onSelect={() => {
                    setEditing(true);
                  }}
                >
                  Edit link…
                </MenuItem>
                <MenuItem
                  danger
                  onSelect={() => {
                    setRemoving(true);
                  }}
                >
                  Remove link…
                </MenuItem>
              </>
            ) : null}
          </MenuContent>
        </Menu>
      ) : null}
      {editing ? (
        <EditLinkDialog
          link={link}
          onClose={() => {
            setEditing(false);
          }}
        />
      ) : null}
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={`Remove the link to ${link.reference}?`}
        description={`The bug stays in ${tracker.name}; only this link is removed.`}
        confirmLabel="Remove link"
        destructive
        onConfirm={() => {
          removeBugLink(link.id)
            .then(() => {
              setRemoving(false);
              invalidate();
              toast(`Removed the link to ${link.reference}`);
            })
            .catch((e: unknown) => {
              toast(errorMessage(e), "error");
            });
        }}
      />
      <RetestDialog
        project={project}
        reference={retest ? link.reference : null}
        onClose={() => {
          setRetest(false);
        }}
      />
    </span>
  );
}

function EditLinkDialog({ link, onClose }: { link: BugLink; onClose: () => void }) {
  const toast = useToast();
  const invalidate = useInvalidateBugs();
  const [url, setUrl] = useState(link.url ?? "");
  const [title, setTitle] = useState(link.title ?? "");
  const [error, setError] = useState<unknown>(null);
  const fieldError = (name: string) =>
    error instanceof ApiError ? error.errors.find((x) => x.field === name)?.message : undefined;
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={`Edit link to ${link.reference}`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="edit-bug-link">
            Save
          </Button>
        </>
      }
    >
      <form
        id="edit-bug-link"
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          updateBugLink(link.id, { url: url.trim() || null, title: title.trim() || null })
            .then(() => {
              invalidate();
              toast("Link saved");
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

/** BR-21: confirm with the number of runs that will be flagged, then flag them. */
export function RetestDialog({
  project,
  reference,
  onClose,
}: {
  project: Project;
  reference: string | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const invalidate = useInvalidateBugs();
  const [preview, setPreview] = useState<{ ref: string; data: RetestResponse } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!reference) return;
    let live = true;
    requestRetest(project.id, reference, true)
      .then((data) => {
        if (live) setPreview({ ref: reference, data });
      })
      .catch((e: unknown) => {
        if (live) setError(e);
      });
    return () => {
      live = false;
    };
  }, [project.id, reference]);
  const p = preview?.ref === reference ? preview.data : null;
  return (
    <ConfirmDialog
      open={reference !== null}
      onOpenChange={(o) => {
        if (!o) {
          setPreview(null);
          setError(null);
          onClose();
        }
      }}
      title={`${reference ?? ""} ready for retest?`}
      description={
        p
          ? p.flagged === 0
            ? `None of the ${p.linked_runs} linked runs can be flagged (closed cycles or replaced runs).`
            : `${p.flagged} of ${p.linked_runs} linked ${p.linked_runs === 1 ? "run" : "runs"} will be flagged ⟳ for retest.`
          : "Counting the linked runs…"
      }
      confirmLabel="Flag for retest"
      pending={pending || !p || p.flagged === 0}
      error={error}
      onConfirm={() => {
        if (!reference) return;
        setPending(true);
        requestRetest(project.id, reference, false)
          .then((r) => {
            invalidate({ runs: true });
            toast(`${r.flagged} ${r.flagged === 1 ? "run" : "runs"} flagged for retest`);
            setPreview(null);
            onClose();
          })
          .catch(setError)
          .finally(() => {
            setPending(false);
          });
      }}
    />
  );
}

/** Chips for several links (distinct references). */
export function BugChips({
  links,
  project,
  tracker,
  canRetest = false,
  compact = false,
  className,
}: {
  links: BugLink[];
  project: Project;
  tracker: Tracker;
  canRetest?: boolean;
  compact?: boolean;
  className?: string;
}) {
  if (!links.length) return null;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {links.map((l) => (
        <BugChip
          key={l.id}
          link={l}
          project={project}
          tracker={tracker}
          canRetest={canRetest}
          compact={compact}
        />
      ))}
    </span>
  );
}

/** Case page "Bugs" tab (docs/02 §8.2): direct links and links through the case's runs. */
export function CaseBugs({
  project,
  caseId,
  caseKey,
  canLink,
  canRetest,
}: {
  project: Project;
  caseId: string;
  caseKey: string;
  canLink: boolean;
  canRetest: boolean;
}) {
  const links = useCaseBugLinks(caseId);
  const tracker = trackerOf(project);
  const [target, setTarget] = useState<LinkTarget | null>(null);
  const rows = links.data ?? [];
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <p className="flex-1 text-[13px] text-ink-secondary">
          Bugs found with this case. They are worked in {tracker.name}; Assay keeps the links.
        </p>
        {canLink ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setTarget({ kind: "case", caseId, label: caseKey });
            }}
          >
            <Bug aria-hidden="true" className="size-4" /> Link bug
          </Button>
        ) : null}
      </div>
      {links.isPending ? (
        <p className="text-[13px] text-ink-secondary">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-card border border-dashed border-border px-4 py-6 text-center text-[13px] text-ink-secondary">
          No bugs are linked to this case.
        </p>
      ) : (
        <table className="w-full text-left text-[13px]">
          <thead className="text-xs text-ink-secondary">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Bug</th>
              <th className="py-1.5 pr-3 font-medium">Where</th>
              <th className="py-1.5 pr-3 font-medium">Linked</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.id} className="border-t border-border">
                <td className="py-2 pr-3">
                  <BugChip link={l} project={project} tracker={tracker} canRetest={canRetest} />
                </td>
                <td className="py-2 pr-3">{whereText(l)}</td>
                <td className="py-2 pr-3 text-ink-secondary">
                  {l.created_by?.display_name ?? "—"} · {new Date(l.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <LinkBugDialog
        target={target}
        tracker={tracker}
        onClose={() => {
          setTarget(null);
        }}
      />
    </div>
  );
}

/** "SPARK-CY-4 · attempt 2 (failed) · step 3", or "On the case". */
export function whereText(l: BugLink): string {
  if (!l.cycle) return "On the case";
  const parts = [l.cycle.key];
  if (l.attempt_no)
    parts.push(
      `attempt ${String(l.attempt_no)}${l.attempt_status ? ` (${l.attempt_status.replace("_", " ")})` : ""}`,
    );
  if (l.step_position) parts.push(`step ${String(l.step_position)}`);
  return parts.join(" · ");
}
