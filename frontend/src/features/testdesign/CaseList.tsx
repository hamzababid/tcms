import type { ColumnDef, ColumnFiltersState, PaginationState, SortingState } from "@tanstack/react-table";
import { useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";

import type { ProjectMember } from "@/api/queries";
import { DataTable, filterValue, rangeValue, sortParam } from "@/components/common/DataTable";
import { EmptyState } from "@/components/common/feedback";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Tag as TagPill } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/field";
import { formatDateTime } from "@/lib/format";

import { useCases, type CaseListItem, type CaseQuery, type Folder, type Tag } from "./api";
import { BulkBar, type Selection } from "./BulkBar";
import { DRAG_CASES } from "./FolderTree";
import { CASE_STATUS_LABELS, CASE_TYPES, PRIORITY_LABELS, label } from "./labels";

const options = (table: Record<string, string>) =>
  Object.entries(table).map(([value, l]) => ({ value, label: l }));

/** Column filters → `GET /test-cases` query (docs/06 §4.4 filters). */
export function caseParams(
  folderId: string | null,
  includeSubfolders: boolean,
  filters: ColumnFiltersState,
): Record<string, string> {
  const out: Record<string, string> = {};
  if (folderId) {
    out.folder_id = folderId;
    out.include_subfolders = String(includeSubfolders);
  }
  const q = filterValue(filters, "title");
  if (q) out.q = q;
  for (const [col, param] of [
    ["status", "status"],
    ["priority", "priority"],
    ["type", "type"],
    ["tags", "tag"],
    ["owner", "owner_id"],
  ] as const) {
    const v = filterValue(filters, col);
    if (v) out[param] = v;
  }
  const [from, to] = rangeValue(filters, "updated_at");
  if (from) out.updated_at__gte = `${from}T00:00:00Z`;
  if (to) out.updated_at__lte = `${to}T23:59:59Z`;
  return out;
}

export function CaseList({
  projectId,
  folderId,
  folderName,
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
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([{ id: "key", desc: false }]);
  // The page belongs to one folder: opening another folder starts on page 1.
  const [page, setPage] = useState<{ folder: string | null; p: PaginationState }>({
    folder: folderId,
    p: { pageIndex: 0, pageSize: 50 },
  });
  const pagination = page.folder === folderId ? page.p : { ...page.p, pageIndex: 0 };
  const setPagination = (p: PaginationState) => {
    setPage({ folder: folderId, p });
  };

  const params = caseParams(folderId, includeSubfolders, filters);
  const query = {
    ...params,
    ...(folderId ? { include_subfolders: includeSubfolders } : {}),
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
    sort: sortParam(sorting) ?? "key",
  } as CaseQuery;
  const cases = useCases(projectId, query);
  const items = useMemo(() => cases.data?.items ?? [], [cases.data]);
  const total = cases.data?.total ?? 0;
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
  const selection: Selection = allMatching
    ? { ids: [], filter: params, count: total }
    : { ids: [...checked], filter: null, count: checked.size };
  const toggleRow = (id: string) => {
    setChecked((c) => {
      const next = new Set(c);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const allOnPage = items.length > 0 && items.every((c) => checked.has(c.id));

  const bodyRef = useRef<HTMLElement>(null);
  const focusRow = (i: number) => {
    const rows = bodyRef.current?.querySelectorAll<HTMLElement>("tbody tr[data-case]");
    rows?.[Math.max(0, Math.min(i, (rows.length || 1) - 1))]?.focus();
  };
  const onKey = (e: KeyboardEvent<HTMLTableRowElement>, i: number, c: CaseListItem) => {
    // docs/07 §4.1: J/K move, X select, Enter open, Esc close (handled by the panel)
    if (e.target !== e.currentTarget) return;
    if (e.key === "j" || e.key === "ArrowDown") focusRow(i + 1);
    else if (e.key === "k" || e.key === "ArrowUp") focusRow(i - 1);
    else if (e.key === "x") toggleRow(c.id);
    else if (e.key === "Enter") onOpen(c);
    else return;
    e.preventDefault();
  };
  const onRowClick = (e: MouseEvent, c: CaseListItem) => {
    if ((e.target as HTMLElement).closest("input,button,a")) return;
    if (e.ctrlKey || e.metaKey) onOpenFullPage(c);
    else onOpen(c);
  };

  const columns: ColumnDef<CaseListItem>[] = [
    {
      id: "select",
      header: () => (
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
      ),
      enableSorting: false,
      cell: (c) => (
        <input
          type="checkbox"
          aria-label={`Select ${c.row.original.key}`}
          checked={allMatching || checked.has(c.row.original.id)}
          onChange={() => {
            toggleRow(c.row.original.id);
          }}
        />
      ),
      meta: { width: "w-10", fixed: true, label: "Select" },
    },
    {
      id: "key",
      accessorKey: "key",
      header: "Key",
      cell: (c) => (
        <span className="whitespace-nowrap font-mono text-[12.5px] font-medium">{c.row.original.key}</span>
      ),
      meta: { width: "w-28", fixed: true },
    },
    {
      id: "title",
      accessorKey: "title",
      header: "Title",
      cell: (c) => (
        <span className="block truncate" title={c.row.original.title}>
          {c.row.original.title}
        </span>
      ),
      meta: {
        filter: { kind: "text", placeholder: "Key or text" },
        fixed: true,
        cellClassName: "max-w-0 min-w-[200px]",
      },
    },
    {
      id: "priority",
      accessorKey: "priority",
      header: "Priority",
      cell: (c) => <PriorityIcon priority={c.row.original.priority} compact={compact} />,
      meta: {
        filter: { kind: "select", options: options(PRIORITY_LABELS) },
        width: compact ? "w-24" : "w-32",
      },
    },
    {
      id: "status",
      accessorKey: "status",
      header: "Status",
      cell: (c) => <StatusBadge kind="case" status={c.row.original.status} compact={compact} />,
      meta: {
        filter: { kind: "select", options: options(CASE_STATUS_LABELS) },
        width: compact ? "w-24" : "w-36",
      },
    },
    ...(compact
      ? []
      : ([
          {
            id: "type",
            accessorKey: "type",
            header: "Type",
            enableSorting: false,
            cell: (c) => (
              <span className="whitespace-nowrap text-ink-secondary">
                {label(CASE_TYPES, c.row.original.type)}
              </span>
            ),
            meta: { filter: { kind: "select", options: options(CASE_TYPES) }, width: "w-36" },
          },
          {
            id: "tags",
            accessorFn: (r) => r.tags.join(", "),
            header: "Tags",
            enableSorting: false,
            cell: (c) => {
              const all = c.row.original.tags;
              return (
                <span className="flex items-center gap-1 whitespace-nowrap" title={all.join(", ")}>
                  {all.slice(0, 2).map((t) => (
                    <TagPill key={t}>{t}</TagPill>
                  ))}
                  {all.length > 2 ? <span className="text-xs text-ink-muted">+{all.length - 2}</span> : null}
                </span>
              );
            },
            meta: {
              filter: { kind: "select", options: tags.map((t) => ({ value: t.name, label: t.name })) },
              width: "w-48",
            },
          },
          {
            id: "version",
            accessorKey: "latest_version_no",
            header: "Ver",
            enableSorting: false,
            cell: (c) => <span className="text-ink-secondary">v{c.row.original.latest_version_no}</span>,
            meta: { width: "w-16" },
          },
          {
            id: "owner",
            accessorFn: (r) => r.owner?.display_name ?? "",
            header: "Owner",
            enableSorting: false,
            cell: (c) => (
              <span className="whitespace-nowrap">{c.row.original.owner?.display_name ?? "—"}</span>
            ),
            meta: {
              filter: {
                kind: "select",
                options: members.map((m) => ({ value: m.user.id, label: m.user.display_name })),
              },
              width: "w-40",
            },
          },
          {
            id: "updated_at",
            accessorKey: "updated_at",
            header: "Updated",
            cell: (c) => (
              <span className="whitespace-nowrap text-ink-secondary">
                {formatDateTime(c.row.original.updated_at)}
              </span>
            ),
            meta: { filter: { kind: "daterange" }, width: "w-44" },
          },
        ] satisfies ColumnDef<CaseListItem>[])),
  ];

  const hasFilters = filters.length > 0;
  return (
    <section ref={bodyRef} aria-label="Test cases" className="flex min-h-0 min-w-0 flex-1 flex-col">
      <DataTable
        label="Test cases"
        columns={columns}
        data={items}
        getRowId={(c) => c.id}
        loading={cases.isPending}
        error={cases.error}
        onRetry={() => void cases.refetch()}
        fill
        bare
        noun={["case", "cases"]}
        initialPageSize={50}
        initialHidden={["type", "tags", "version"]}
        emptyText="No cases match these filters."
        {...(hasFilters
          ? {}
          : {
              empty: (
                <EmptyState
                  text={folderName ? `No cases in ${folderName} yet.` : "No cases yet."}
                  {...(onNewCase ? { action: <Button onClick={onNewCase}>Create a case (C)</Button> } : {})}
                />
              ),
            })}
        toolbar={
          <>
            <span className="truncate text-[13px] font-medium text-ink">{folderName ?? "All cases"}</span>
            {folderId ? (
              <Checkbox
                label="Include subfolders"
                checked={includeSubfolders}
                onChange={(e) => {
                  setIncludeSubfolders(e.target.checked);
                }}
              />
            ) : null}
          </>
        }
        banner={
          selection.count > 0 ? (
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
          ) : undefined
        }
        rowProps={(c, i) => ({
          ...({ "data-case": c.key } as object),
          tabIndex: 0,
          selected: c.key === selectedKey,
          "aria-selected": c.key === selectedKey,
          className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
          draggable: canEdit,
          onDragStart: (e) => {
            const ids = checked.has(c.id) ? [...checked] : [c.id];
            e.dataTransfer.setData(DRAG_CASES, JSON.stringify(ids));
            e.dataTransfer.effectAllowed = "move";
          },
          onClick: (e) => {
            onRowClick(e, c);
          },
          onAuxClick: (e) => {
            if (e.button === 1) onOpenFullPage(c);
          },
          onKeyDown: (e) => {
            onKey(e, i, c);
          },
        })}
        server={{
          total,
          pagination,
          onPaginationChange: setPagination,
          sorting,
          onSortingChange: setSorting,
          filters,
          onFiltersChange: setFilters,
        }}
      />
    </section>
  );
}
