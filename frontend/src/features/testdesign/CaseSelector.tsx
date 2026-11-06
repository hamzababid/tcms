import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/api/client";

import { Skeleton, errorMessage } from "@/components/common/feedback";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";

import { useCases, useFolders, useTags } from "./api";

/** What to add: the union of picked cases, folders (with subfolders) and tags (docs/02 §6.2, §7.1). */
export interface CaseSelection {
  case_ids: string[];
  folder_ids: string[];
  tags: string[];
  /** A repository saved view (plans only, L25): the cases it matches when added. */
  saved_view_id?: string | null;
}

export const emptySelection: CaseSelection = { case_ids: [], folder_ids: [], tags: [] };

export const selectionSize = (s: CaseSelection) =>
  s.case_ids.length + s.folder_ids.length + s.tags.length + (s.saved_view_id ? 1 : 0);

export function selectionText(s: CaseSelection): string {
  const parts: string[] = [];
  const n = (k: number, one: string, many: string) => `${k} ${k === 1 ? one : many}`;
  if (s.folder_ids.length) parts.push(n(s.folder_ids.length, "folder", "folders"));
  if (s.tags.length) parts.push(n(s.tags.length, "tag", "tags"));
  if (s.case_ids.length) parts.push(n(s.case_ids.length, "case", "cases"));
  if (s.saved_view_id) parts.push("1 saved view");
  return parts.length ? parts.join(", ") : "Nothing selected";
}

/**
 * Pick cases from the repository by Folder / Tag / Search ("Add cases" dialog, docs/07 §5.7). Saved
 * views (plans only). Archived, deprecated and unapproved cases are skipped by the server, which
 * reports them back.
 */
export function CaseSelector({
  projectId,
  value,
  onChange,
  savedViews = false,
}: {
  projectId: string;
  value: CaseSelection;
  onChange: (s: CaseSelection) => void;
  savedViews?: boolean;
}) {
  const views = useQuery({
    queryKey: ["saved-views", projectId, "test_case"],
    enabled: savedViews,
    queryFn: async () =>
      (
        await api.GET("/api/v1/projects/{project_id}/saved-views", {
          params: { path: { project_id: projectId }, query: { entity_type: "test_case" } },
        })
      ).data ?? [],
  });
  const [tab, setTab] = useState("folder");
  const folders = useFolders(projectId, false);
  const tags = useTags(projectId);
  const toggle = (list: string[], id: string, on: boolean) =>
    on ? [...list, id] : list.filter((x) => x !== id);

  return (
    <div>
      <Tabs
        label="Choose cases by"
        value={tab}
        onValueChange={setTab}
        contentClassName="pt-3"
        items={[
          {
            value: "folder",
            label: "Folder",
            ...(value.folder_ids.length ? { count: value.folder_ids.length } : {}),
            content: folders.isPending ? (
              <Skeleton rows={4} />
            ) : (
              <ul className="max-h-64 overflow-y-auto rounded-control border border-border p-2 text-[13px]">
                {(folders.data ?? []).length === 0 ? (
                  <li className="p-2 text-ink-muted">No folders yet.</li>
                ) : (
                  (folders.data ?? []).map((f) => (
                    <li key={f.id} style={{ paddingLeft: `${(f.depth - 1) * 16}px` }}>
                      <label className="flex h-7 cursor-pointer items-center gap-2 rounded px-1.5 hover:bg-surface-muted">
                        <input
                          type="checkbox"
                          checked={value.folder_ids.includes(f.id)}
                          onChange={(e) => {
                            onChange({
                              ...value,
                              folder_ids: toggle(value.folder_ids, f.id, e.target.checked),
                            });
                          }}
                        />
                        <span className="min-w-0 flex-1 truncate">{f.name}</span>
                        <span className="tabular text-xs text-ink-muted">{f.total_count}</span>
                      </label>
                    </li>
                  ))
                )}
              </ul>
            ),
          },
          {
            value: "tag",
            label: "Tag",
            ...(value.tags.length ? { count: value.tags.length } : {}),
            content: (
              <div className="flex max-h-64 flex-wrap gap-2 overflow-y-auto">
                {(tags.data ?? []).length === 0 ? (
                  <p className="text-[13px] text-ink-muted">No tags yet.</p>
                ) : (
                  (tags.data ?? []).map((t) => (
                    <label
                      key={t.id}
                      className="flex cursor-pointer items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs has-[:checked]:border-accent-border has-[:checked]:bg-accent-tint has-[:checked]:text-accent-ink"
                    >
                      <input
                        type="checkbox"
                        checked={value.tags.includes(t.name)}
                        onChange={(e) => {
                          onChange({ ...value, tags: toggle(value.tags, t.name, e.target.checked) });
                        }}
                      />
                      {t.name}
                    </label>
                  ))
                )}
              </div>
            ),
          },
          ...(savedViews
            ? [
                {
                  value: "view",
                  label: "Saved view",
                  ...(value.saved_view_id ? { count: 1 } : {}),
                  content:
                    (views.data ?? []).length === 0 ? (
                      <p className="text-[13px] text-ink-muted">
                        No saved views yet. Save one from the repository list (Views ▾).
                      </p>
                    ) : (
                      <ul className="max-h-64 overflow-y-auto rounded-control border border-border p-2 text-[13px]">
                        {(views.data ?? []).map((v) => (
                          <li key={v.id}>
                            <label className="flex h-7 cursor-pointer items-center gap-2 rounded px-1.5 hover:bg-surface-muted">
                              <input
                                type="radio"
                                name="saved-view"
                                checked={value.saved_view_id === v.id}
                                onChange={() => {
                                  onChange({ ...value, saved_view_id: v.id });
                                }}
                              />
                              <span className="flex-1">{v.name}</span>
                              <span className="text-xs text-ink-muted">
                                {v.visibility === "project" ? "shared" : "private"}
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                    ),
                },
              ]
            : []),
          {
            value: "search",
            label: "Search",
            ...(value.case_ids.length ? { count: value.case_ids.length } : {}),
            content: (
              <CaseSearch
                projectId={projectId}
                picked={value.case_ids}
                onToggle={(id, on) => {
                  onChange({ ...value, case_ids: toggle(value.case_ids, id, on) });
                }}
              />
            ),
          },
        ]}
      />
      <p className="mt-3 text-[13px] text-ink-secondary" aria-live="polite">
        Selected: {selectionText(value)}
      </p>
    </div>
  );
}

function CaseSearch({
  projectId,
  picked,
  onToggle,
}: {
  projectId: string;
  picked: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => {
      setQ(text.trim());
    }, 300);
    return () => {
      window.clearTimeout(t);
    };
  }, [text]);
  const cases = useCases(projectId, { page: 1, page_size: 50, sort: "key", ...(q ? { q } : {}) });
  const items = cases.data?.items ?? [];
  return (
    <div className="grid gap-2">
      <Input
        type="search"
        aria-label="Search cases"
        placeholder="Key or title"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
        }}
      />
      {cases.isPending ? (
        <Skeleton rows={4} />
      ) : (
        <ul className="max-h-64 overflow-y-auto rounded-control border border-border p-1 text-[13px]">
          {items.length === 0 ? (
            <li className="p-2 text-ink-muted">No cases match.</li>
          ) : (
            items.map((c) => (
              <li key={c.id}>
                <label className="flex h-8 cursor-pointer items-center gap-2 rounded px-1.5 hover:bg-surface-muted">
                  <input
                    type="checkbox"
                    aria-label={`Select ${c.key}`}
                    checked={picked.includes(c.id)}
                    onChange={(e) => {
                      onToggle(c.id, e.target.checked);
                    }}
                  />
                  <span className="w-28 shrink-0 font-mono text-[12.5px]">{c.key}</span>
                  <span className="min-w-0 flex-1 truncate">{c.title}</span>
                  <PriorityIcon priority={c.priority} compact />
                  <StatusBadge kind="case" status={c.status} compact />
                </label>
              </li>
            ))
          )}
        </ul>
      )}
      {(cases.data?.total ?? 0) > items.length ? (
        <p className="text-xs text-ink-muted">
          Showing the first {items.length} of {cases.data?.total.toLocaleString()} matches. Refine the search,
          or use Folder or Tag.
        </p>
      ) : null}
    </div>
  );
}

/** Why a case was not added (docs/04 §5.2, BR-12/13). */
export const SKIP_REASONS: Record<string, string> = {
  archived: "archived",
  deprecated: "deprecated",
  no_eligible_version: "no approved version",
  already_in_plan: "already in the plan",
  already_in_cycle: "already in the cycle",
  not_found: "not found",
};

/** "Added 12 · Skipped 3" with the skipped keys and reasons (docs/07 §5.7–5.8). */
export function AddResult({
  added,
  skipped,
  noun = "cases",
}: {
  added: number;
  skipped: { key: string; reason: string }[];
  noun?: string;
}) {
  return (
    <div role="status" className="grid gap-2 text-[13px]">
      <p className="font-medium text-ink">
        Added {added.toLocaleString()} {added === 1 ? noun.replace(/s$/, "") : noun}
        {skipped.length ? ` · skipped ${skipped.length.toLocaleString()}` : ""}
      </p>
      {skipped.length ? (
        <details open={skipped.length <= 10}>
          <summary className="cursor-pointer text-ink-secondary">Skipped cases</summary>
          <ul className="mt-1.5 max-h-48 overflow-y-auto rounded-control border border-border p-2">
            {skipped.map((s) => (
              <li key={`${s.key}-${s.reason}`} className="flex gap-3 py-0.5">
                <span className="w-32 shrink-0 font-mono text-[12.5px]">{s.key}</span>
                <span className="text-ink-secondary">{SKIP_REASONS[s.reason] ?? s.reason}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

interface AddOutcome {
  added: number;
  skipped: { key: string; reason: string }[];
}

/** "Add cases" (docs/07 §5.7–5.8): Folder / Tag / Search, then what was added and skipped. */
export function AddCasesDialog({
  title,
  projectId,
  pending,
  error,
  onAdd,
  onClose,
  noun = "cases",
  savedViews = false,
}: {
  title: string;
  projectId: string;
  pending: boolean;
  error: unknown;
  onAdd: (s: CaseSelection) => Promise<AddOutcome>;
  onClose: () => void;
  noun?: string;
  savedViews?: boolean;
}) {
  const [selection, setSelection] = useState<CaseSelection>(emptySelection);
  const [result, setResult] = useState<AddOutcome | null>(null);
  return (
    <Dialog
      open
      wide
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={title}
      footer={
        result ? (
          <Button onClick={onClose}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              disabled={pending || selectionSize(selection) === 0}
              onClick={() => {
                onAdd(selection).then(setResult, () => undefined);
              }}
            >
              Add
            </Button>
          </>
        )
      }
    >
      {result ? (
        <AddResult added={result.added} skipped={result.skipped} noun={noun} />
      ) : (
        <>
          <CaseSelector
            projectId={projectId}
            value={selection}
            onChange={setSelection}
            savedViews={savedViews}
          />
          {error ? (
            <p role="alert" className="mt-3 text-[13px] text-danger">
              {errorMessage(error)}
            </p>
          ) : null}
        </>
      )}
    </Dialog>
  );
}
