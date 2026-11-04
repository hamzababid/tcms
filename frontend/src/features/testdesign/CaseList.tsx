import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";

import type { ProjectMember } from "@/api/queries";
import { EmptyState, ErrorState, Skeleton } from "@/components/common/feedback";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, Select } from "@/components/ui/field";
import { cn } from "@/lib/utils";

import { useCases, type CaseListItem, type CaseQuery, type Folder, type Tag } from "./api";
import { BulkBar, type Selection } from "./BulkBar";
import { DRAG_CASES } from "./FolderTree";
import { CASE_STATUS_LABELS, CASE_TYPES, PRIORITY_LABELS } from "./labels";

export interface ListFilters {
  q: string;
  status: string;
  priority: string;
  type: string;
  tag: string;
  owner_id: string;
  include_subfolders: boolean;
  sort: string;
  page: number;
}

export const DEFAULT_FILTERS: ListFilters = {
  q: "",
  status: "",
  priority: "",
  type: "",
  tag: "",
  owner_id: "",
  include_subfolders: true,
  sort: "key",
  page: 1,
};

const PAGE_SIZE = 50;

/** The filter as sent to the API (and to bulk "select all matching"). */
export function toParams(folderId: string | null, f: ListFilters): Record<string, string> {
  const out: Record<string, string> = {};
  if (folderId) {
    out.folder_id = folderId;
    out.include_subfolders = String(f.include_subfolders);
  }
  for (const k of ["q", "status", "priority", "type", "tag", "owner_id"] as const) {
    if (f[k]) out[k] = f[k];
  }
  return out;
}

const SORTABLE: Record<string, string> = {
  key: "Key",
  title: "Title",
  priority: "Priority",
  status: "Status",
};

export function CaseList({
  projectId,
  folderId,
  folderName,
  filters,
  onFilters,
  selectedKey,
  onOpen,
  onOpenFullPage,
  perms,
  canEdit,
  folders,
  tags,
  members,
  onNewCase,
}: {
  projectId: string;
  folderId: string | null;
  folderName: string | null;
  filters: ListFilters;
  onFilters: (f: ListFilters) => void;
  selectedKey: string | null;
  onOpen: (c: CaseListItem) => void;
  onOpenFullPage: (c: CaseListItem) => void;
  perms: Set<string>;
  canEdit: boolean;
  folders: Folder[];
  tags: Tag[];
  members: ProjectMember[];
  onNewCase: (() => void) | null;
}) {
  const params = toParams(folderId, filters);
  const query: CaseQuery = {
    ...params,
    include_subfolders: filters.include_subfolders,
    page: filters.page,
    page_size: PAGE_SIZE,
    sort: filters.sort,
  };
  if (!folderId) delete query.include_subfolders;
  const cases = useCases(projectId, query);
  // With the side panel open the list keeps key, title and icon-only priority/status (docs/07 §9).
  const compact = selectedKey !== null;
  // Selection belongs to one filter: a new filter starts with nothing selected.
  const paramsKey = JSON.stringify(params);
  const [sel, setSel] = useState<{ key: string; ids: Set<string>; all: boolean }>({
    key: paramsKey,
    ids: new Set(),
    all: false,
  });
  const current = sel.key === paramsKey ? sel : { key: paramsKey, ids: new Set<string>(), all: false };
  const checked = current.ids;
  const allMatching = current.all;
  const setChecked = (fn: (c: Set<string>) => Set<string>) => {
    setSel({ key: paramsKey, ids: fn(checked), all: false });
  };
  const setAllMatching = (all: boolean) => {
    setSel({ key: paramsKey, ids: all ? checked : new Set(), all });
  };
  const [focus, setFocus] = useState(0);
  const [search, setSearch] = useState(filters.q);
  const tableRef = useRef<HTMLTableSectionElement>(null);

  // Debounced search box → filter
  useEffect(() => {
    if (search === filters.q) return;
    const t = window.setTimeout(() => {
      onFilters({ ...filters, q: search, page: 1 });
    }, 300);
    return () => {
      window.clearTimeout(t);
    };
  }, [search, filters, onFilters]);

  const items = useMemo(() => cases.data?.items ?? [], [cases.data]);
  const total = cases.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const selection: Selection = allMatching
    ? { ids: [], filter: params, count: total }
    : { ids: [...checked], filter: null, count: checked.size };

  const set = (patch: Partial<ListFilters>) => {
    onFilters({ ...filters, ...patch, page: patch.page ?? 1 });
  };
  const toggleRow = (id: string) => {
    setChecked((c) => {
      const next = new Set(c);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const allOnPage = items.length > 0 && items.every((c) => checked.has(c.id));

  const focusRow = (i: number) => {
    const n = Math.max(0, Math.min(i, items.length - 1));
    setFocus(n);
    tableRef.current?.querySelectorAll<HTMLElement>("tr")[n]?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, i: number, c: CaseListItem) => {
    // docs/07 §4.1: J/K move, X select, Enter open, Esc close (handled by the panel)
    if (e.key === "j" || e.key === "ArrowDown") focusRow(i + 1);
    else if (e.key === "k" || e.key === "ArrowUp") focusRow(i - 1);
    else if (e.key === "x") toggleRow(c.id);
    else if (e.key === "Enter") onOpen(c);
    else return;
    e.preventDefault();
  };
  const onRowClick = (e: MouseEvent, c: CaseListItem) => {
    if (e.ctrlKey || e.metaKey) onOpenFullPage(c);
    else onOpen(c);
  };

  return (
    <section
      aria-label="Test cases"
      className="flex min-h-0 min-w-0 flex-1 flex-col rounded-card border border-border bg-surface"
    >
      <div
        className={cn(
          "flex items-center gap-2 border-b border-border px-3 py-2",
          compact ? "flex-nowrap overflow-x-auto" : "flex-wrap",
        )}
      >
        <FilterSelect
          label="Status"
          value={filters.status}
          options={CASE_STATUS_LABELS}
          onChange={(v) => {
            set({ status: v });
          }}
        />
        <FilterSelect
          label="Priority"
          value={filters.priority}
          options={PRIORITY_LABELS}
          onChange={(v) => {
            set({ priority: v });
          }}
        />
        <FilterSelect
          label="Type"
          value={filters.type}
          options={CASE_TYPES}
          onChange={(v) => {
            set({ type: v });
          }}
        />
        <FilterSelect
          label="Tag"
          value={filters.tag}
          options={Object.fromEntries(tags.map((t) => [t.name, t.name]))}
          onChange={(v) => {
            set({ tag: v });
          }}
        />
        <FilterSelect
          label="Owner"
          value={filters.owner_id}
          options={Object.fromEntries(members.map((m) => [m.user.id, m.user.display_name]))}
          onChange={(v) => {
            set({ owner_id: v });
          }}
        />
        {folderId ? (
          <Checkbox
            label="Include subfolders"
            checked={filters.include_subfolders}
            onChange={(e) => {
              set({ include_subfolders: e.target.checked });
            }}
          />
        ) : null}
        <Input
          type="search"
          aria-label="Search cases"
          placeholder="Search by key or text"
          className="h-8 min-w-48 flex-1"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
          }}
        />
      </div>
      {selection.count > 0 ? (
        <BulkBar
          projectId={projectId}
          selection={selection}
          total={total}
          perms={perms}
          folders={folders}
          tags={tags}
          members={members}
          onSelectAll={() => {
            setAllMatching(true);
          }}
          onClear={() => {
            setAllMatching(false);
          }}
        />
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto">
        {cases.isPending ? (
          <div className="p-3">
            <Skeleton rows={8} />
          </div>
        ) : cases.isError ? (
          <div className="p-3">
            <ErrorState error={cases.error} onRetry={() => void cases.refetch()} />
          </div>
        ) : items.length === 0 ? (
          <div className="p-6">
            <EmptyState
              text={
                Object.keys(params).some((k) => k !== "folder_id" && k !== "include_subfolders")
                  ? "No cases match these filters."
                  : "No cases yet."
              }
              {...(onNewCase ? { action: <Button onClick={onNewCase}>Create a case (C)</Button> } : {})}
            />
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-ground">
              <tr className="h-9 text-left text-xs font-medium text-ink-secondary">
                <th scope="col" className="w-10 px-3">
                  <input
                    type="checkbox"
                    aria-label="Select page"
                    checked={allOnPage}
                    onChange={(e) => {
                      setChecked((c) => {
                        const next = new Set(c);
                        for (const it of items) {
                          if (e.target.checked) next.add(it.id);
                          else next.delete(it.id);
                        }
                        return next;
                      });
                    }}
                  />
                </th>
                {(["key", "title", "priority", "status"] as const).map((k) => {
                  const active = filters.sort.replace("-", "") === k;
                  const desc = filters.sort.startsWith("-");
                  return (
                    <th
                      key={k}
                      scope="col"
                      aria-sort={active ? (desc ? "descending" : "ascending") : "none"}
                      className={cn(
                        "px-2",
                        k === "key" && "w-32",
                        k === "priority" && (compact ? "w-10" : "w-24"),
                        k === "status" && (compact ? "w-10" : "w-32"),
                      )}
                    >
                      <button
                        type="button"
                        className="hover:text-ink"
                        onClick={() => {
                          set({ sort: active && !desc ? `-${k}` : k });
                        }}
                      >
                        {compact && (k === "priority" || k === "status") ? (
                          <span className="sr-only">{SORTABLE[k]}</span>
                        ) : (
                          SORTABLE[k]
                        )}
                        {active ? (desc ? " ↓" : " ↑") : ""}
                      </button>
                    </th>
                  );
                })}
                {compact ? null : (
                  <>
                    <th scope="col" className="w-14 px-2">
                      Ver
                    </th>
                    <th scope="col" className="w-36 px-2">
                      Owner
                    </th>
                  </>
                )}
              </tr>
            </thead>
            <tbody ref={tableRef}>
              {items.map((c, i) => (
                <tr
                  key={c.id}
                  tabIndex={i === focus ? 0 : -1}
                  aria-selected={c.key === selectedKey}
                  draggable={canEdit}
                  onDragStart={(e) => {
                    const ids = checked.has(c.id) ? [...checked] : [c.id];
                    e.dataTransfer.setData(DRAG_CASES, JSON.stringify(ids));
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={(e) => {
                    onRowClick(e, c);
                  }}
                  onAuxClick={(e) => {
                    if (e.button === 1) onOpenFullPage(c);
                  }}
                  onKeyDown={(e) => {
                    onKey(e, i, c);
                  }}
                  onFocus={() => {
                    setFocus(i);
                  }}
                  className={cn(
                    "h-10 cursor-pointer border-t border-border hover:bg-ground focus:bg-accent-tint focus:outline-none",
                    c.key === selectedKey && "bg-accent-tint",
                  )}
                >
                  <td
                    className="px-3"
                    onClick={(e) => {
                      e.stopPropagation();
                    }}
                  >
                    <input
                      type="checkbox"
                      aria-label={`Select ${c.key}`}
                      checked={allMatching || checked.has(c.id)}
                      onChange={() => {
                        toggleRow(c.id);
                      }}
                    />
                  </td>
                  <td className="whitespace-nowrap px-2 font-mono text-xs text-ink-secondary">{c.key}</td>
                  <td className="max-w-0 truncate px-2 text-ink" title={c.title}>
                    {c.title}
                    {c.tags.length ? (
                      <span className="ml-2 text-xs text-ink-muted">{c.tags.join(" · ")}</span>
                    ) : null}
                  </td>
                  <td className="px-2">
                    <PriorityIcon priority={c.priority} compact={compact} />
                  </td>
                  <td className="px-2">
                    <StatusBadge kind="case" status={c.status} compact={compact} />
                  </td>
                  {compact ? null : (
                    <>
                      <td className="px-2 text-xs text-ink-secondary">v{c.latest_version_no}</td>
                      <td className="truncate px-2 text-xs text-ink-secondary">
                        {c.owner?.display_name ?? "—"}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-ink-secondary">
        <span>
          {total.toLocaleString()} {total === 1 ? "case" : "cases"}
          {folderName ? ` in ${folderName}${filters.include_subfolders ? " (incl. subfolders)" : ""}` : ""}
        </span>
        {pages > 1 ? (
          <span className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={filters.page <= 1}
              onClick={() => {
                set({ page: filters.page - 1 });
              }}
            >
              Previous
            </Button>
            Page {filters.page} of {pages}
            <Button
              variant="ghost"
              size="sm"
              disabled={filters.page >= pages}
              onClick={() => {
                set({ page: filters.page + 1 });
              }}
            >
              Next
            </Button>
          </span>
        ) : (
          <span>Page 1 of 1</span>
        )}
      </div>
    </section>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Record<string, string>;
  onChange: (v: string) => void;
}) {
  return (
    <Select
      aria-label={`Filter by ${label.toLowerCase()}`}
      className={cn("h-8 w-auto text-xs", value && "border-accent text-accent")}
      value={value}
      onChange={(e) => {
        onChange(e.target.value);
      }}
    >
      <option value="">{label}: any</option>
      {Object.entries(options).map(([v, l]) => (
        <option key={v} value={v}>
          {label}: {l}
        </option>
      ))}
    </Select>
  );
}
