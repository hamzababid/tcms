/**
 * DataTable (docs/07 §4.1, §6.3; docs/design/Main.dc.html row anatomy). The one table used across
 * the app: sortable headers, a per-column filter row, results count, column visibility, page size
 * and pagination. Client mode filters/sorts/pages in the browser; server mode hands the state to
 * the caller, which queries the API.
 */
import * as M from "@radix-ui/react-dropdown-menu";
import * as P from "@radix-ui/react-popover";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type FilterFn,
  type PaginationState,
  type Row,
  type RowData,
  type SortingState,
  type VisibilityState,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Columns3,
  FilterX,
} from "lucide-react";
import { useEffect, useMemo, useState, type HTMLAttributes, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { MenuContent } from "@/components/ui/menu";
import { cn } from "@/lib/utils";

import { ErrorState } from "./feedback";

export interface FilterOption {
  value: string;
  label: string;
}

export type ColumnFilter =
  | { kind: "text"; placeholder?: string }
  | { kind: "select"; options: FilterOption[] }
  | { kind: "daterange" };

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- signature fixed by TanStack Table
  interface ColumnMeta<TData extends RowData, TValue> {
    filter?: ColumnFilter;
    /** Width utility for the column, e.g. "w-36". */
    width?: string;
    align?: "left" | "right" | "center";
    /** Extra classes for body cells. */
    cellClassName?: string;
    /** Label in the Columns menu (defaults to the header text). */
    label?: string;
    /** Column cannot be hidden from the Columns menu. */
    fixed?: boolean;
  }
}

/** Filter functions for client mode (by filter kind). */
const textFilter: FilterFn<unknown> = (row, id, value: string) =>
  String(row.getValue(id) ?? "")
    .toLowerCase()
    .includes(value.trim().toLowerCase());
const selectFilter: FilterFn<unknown> = (row, id, value: string) =>
  !value || String(row.getValue(id) ?? "") === value;
const dateRangeFilter: FilterFn<unknown> = (row, id, value: [string, string]) => {
  const raw = row.getValue(id);
  if (typeof raw !== "string" || !raw) return false;
  const day = raw.slice(0, 10);
  return (!value[0] || day >= value[0]) && (!value[1] || day <= value[1]);
};

export const PAGE_SIZES = [10, 25, 50, 100] as const;

export interface ServerState {
  total: number;
  pagination: PaginationState;
  onPaginationChange: (p: PaginationState) => void;
  sorting: SortingState;
  onSortingChange: (s: SortingState) => void;
  filters: ColumnFiltersState;
  onFiltersChange: (f: ColumnFiltersState) => void;
}

export interface DataTableProps<T> {
  /** Accessible name of the table. */
  label: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- column value types vary per column
  columns: ColumnDef<T, any>[];
  data: T[];
  getRowId?: (row: T) => string;
  server?: ServerState;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyText?: string;
  /** Shown when there is no data at all (not just no matches). */
  empty?: ReactNode;
  /** Left side of the toolbar (search, actions). */
  toolbar?: ReactNode;
  /** Rows between the toolbar and the table (e.g. a bulk action bar). */
  banner?: ReactNode;
  rowProps?: (row: T, index: number) => HTMLAttributes<HTMLTableRowElement> & { selected?: boolean };
  initialPageSize?: number;
  initialSorting?: SortingState;
  /** Fill the parent's height and scroll inside (repository layout). */
  fill?: boolean;
  /** Without the outer card frame (inside panels and full-bleed panes). */
  bare?: boolean;
  /** Hide the per-column filter row (only for tables that never need it). */
  hideFilters?: boolean;
  /** Text for the results count ("cases", "members"). */
  noun?: [singular: string, plural: string];
  /** Narrow containers (side panel): tighter padding and a one-line footer. */
  dense?: boolean;
  /** Column ids hidden until chosen in the Columns menu. */
  initialHidden?: string[];
}

function FilterCell({
  filter,
  value,
  onChange,
  label,
}: {
  filter: ColumnFilter;
  value: unknown;
  onChange: (v: unknown) => void;
  label: string;
}) {
  // Remounted (key) when filters are cleared, so the local text starts from the column value.
  const [text, setText] = useState(typeof value === "string" ? value : "");
  const current = typeof value === "string" ? value : "";
  useEffect(() => {
    if (filter.kind !== "text" || text === current) return;
    const t = window.setTimeout(() => {
      onChange(text || undefined);
    }, 300);
    return () => {
      window.clearTimeout(t);
    };
  }, [filter.kind, text, current, onChange]);

  const box =
    "h-7 w-full min-w-0 rounded-[5px] border border-border bg-surface px-2 text-[12.5px] font-normal text-ink placeholder:text-ink-faint hover:border-border-control focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-tint";
  if (filter.kind === "text") {
    return (
      <input
        type="search"
        aria-label={`Filter ${label}`}
        placeholder={filter.placeholder ?? "Filter…"}
        className={box}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
        }}
      />
    );
  }
  if (filter.kind === "select") {
    return (
      <Select
        aria-label={`Filter ${label}`}
        className={cn(box, "pr-6", current && "border-accent-border bg-accent-tint text-accent-ink")}
        value={current}
        onChange={(e) => {
          onChange(e.target.value || undefined);
        }}
      >
        <option value="">All</option>
        {filter.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </Select>
    );
  }
  return <DateRangeFilter label={label} value={value} onChange={onChange} className={box} />;
}

const shortDate = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const short = (iso: string) => shortDate.format(new Date(`${iso}T00:00:00`));

/** Compact date-range filter: one button, From/To in a popover. */
function DateRangeFilter({
  label,
  value,
  onChange,
  className,
}: {
  label: string;
  value: unknown;
  onChange: (v: unknown) => void;
  className: string;
}) {
  const range = Array.isArray(value) ? (value as [string, string]) : ["", ""];
  const [from, to] = [range[0] ?? "", range[1] ?? ""];
  const set = (i: 0 | 1, v: string) => {
    const next: [string, string] = [from, to];
    next[i] = v;
    onChange(next[0] || next[1] ? next : undefined);
  };
  const text =
    from && to
      ? `${short(from)} – ${short(to)}`
      : from
        ? `From ${short(from)}`
        : to
          ? `Until ${short(to)}`
          : "Any date";
  const active = Boolean(from || to);
  return (
    <P.Root>
      <P.Trigger
        className={cn(
          className,
          "flex items-center gap-1.5 text-left",
          active ? "border-accent-border bg-accent-tint text-accent-ink" : "text-ink-secondary",
        )}
      >
        <CalendarDays aria-hidden="true" className="size-3.5 shrink-0" />
        <span className="sr-only">Filter {label}: </span>
        <span className="truncate">{text}</span>
      </P.Trigger>
      <P.Portal>
        <P.Content
          align="start"
          sideOffset={4}
          className="z-50 w-64 rounded-card border border-border bg-surface p-3 text-[13px] shadow-[var(--shadow-popover)]"
        >
          <div className="grid gap-3">
            <label className="flex flex-col gap-1 font-medium text-ink">
              From
              <input
                type="date"
                className="h-8 rounded-control border border-border-control px-2 font-normal"
                value={from}
                onChange={(e) => {
                  set(0, e.target.value);
                }}
              />
            </label>
            <label className="flex flex-col gap-1 font-medium text-ink">
              To
              <input
                type="date"
                className="h-8 rounded-control border border-border-control px-2 font-normal"
                value={to}
                onChange={(e) => {
                  set(1, e.target.value);
                }}
              />
            </label>
            <div className="flex justify-between">
              <Button
                variant="ghost"
                size="xs"
                disabled={!active}
                onClick={() => {
                  onChange(undefined);
                }}
              >
                Clear
              </Button>
              <P.Close asChild>
                <Button size="xs">Done</Button>
              </P.Close>
            </div>
          </div>
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}

function headerText<T>(col: ColumnDef<T>): string {
  if (col.meta?.label) return col.meta.label;
  return typeof col.header === "string" ? col.header : (col.id ?? "");
}

export function DataTable<T>({
  label,
  columns,
  data,
  getRowId,
  server,
  loading = false,
  error,
  onRetry,
  emptyText = "No rows match these filters.",
  empty,
  toolbar,
  banner,
  rowProps,
  initialPageSize = 25,
  initialSorting = [],
  fill = false,
  bare = false,
  hideFilters = false,
  noun = ["row", "rows"],
  dense = false,
  initialHidden = [],
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: initialPageSize });
  const [visibility, setVisibility] = useState<VisibilityState>(() =>
    Object.fromEntries(initialHidden.map((id) => [id, false])),
  );

  // Client-mode filter function per column, from its filter kind.
  const cols = useMemo(
    () =>
      columns.map((c) => {
        const kind = c.meta?.filter?.kind;
        if (!kind || c.filterFn) return c;
        const fn = kind === "select" ? selectFilter : kind === "daterange" ? dateRangeFilter : textFilter;
        return { ...c, filterFn: fn as FilterFn<T> };
      }),
    [columns],
  );
  const [clears, setClears] = useState(0);

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table returns non-memoizable functions by design
  const table = useReactTable<T>({
    data,
    columns: cols,
    ...(getRowId ? { getRowId: (r: T) => getRowId(r) } : {}),
    state: {
      sorting: server ? server.sorting : sorting,
      columnFilters: server ? server.filters : filters,
      pagination: server ? server.pagination : pagination,
      columnVisibility: visibility,
    },
    onSortingChange: (u) => {
      const next = typeof u === "function" ? u(server ? server.sorting : sorting) : u;
      if (server) server.onSortingChange(next);
      else setSorting(next);
    },
    onColumnFiltersChange: (u) => {
      const next = typeof u === "function" ? u(server ? server.filters : filters) : u;
      if (server) {
        server.onFiltersChange(next);
        server.onPaginationChange({ ...server.pagination, pageIndex: 0 });
      } else {
        setFilters(next);
        setPagination((p) => ({ ...p, pageIndex: 0 }));
      }
    },
    onPaginationChange: (u) => {
      const next = typeof u === "function" ? u(server ? server.pagination : pagination) : u;
      if (server) server.onPaginationChange(next);
      else setPagination(next);
    },
    onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(),
    ...(server
      ? { manualPagination: true, manualSorting: true, manualFiltering: true, rowCount: server.total }
      : {
          getFilteredRowModel: getFilteredRowModel(),
          getSortedRowModel: getSortedRowModel(),
          getPaginationRowModel: getPaginationRowModel(),
        }),
  });

  const state = table.getState();
  const total = server ? server.total : table.getFilteredRowModel().rows.length;
  const { pageIndex, pageSize } = state.pagination;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min(total, (pageIndex + 1) * pageSize);
  const rows: Row<T>[] = table.getRowModel().rows;
  const hasFilters = state.columnFilters.length > 0;
  const anyFilter = !hideFilters && table.getVisibleLeafColumns().some((c) => c.columnDef.meta?.filter);
  const hideable = table.getAllLeafColumns().filter((c) => !c.columnDef.meta?.fixed && c.getCanHide());
  const nothingAtAll = !loading && !hasFilters && total === 0 && empty;
  const colCount = table.getVisibleLeafColumns().length;
  const [one, many] = noun;

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col bg-surface",
        !bare && "rounded-card border border-border",
        fill && "min-h-0 flex-1",
      )}
    >
      <div
        className={cn(
          "flex flex-wrap items-center gap-2 border-b border-border py-2.5",
          dense ? "px-3" : "px-4",
          !bare && "rounded-t-card",
        )}
      >
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{toolbar}</div>
        <span className="tabular text-[12.5px] text-ink-secondary" aria-live="polite">
          {total.toLocaleString()} {total === 1 ? one : many}
        </span>
        {hasFilters ? (
          <Button
            variant="ghost"
            size="xs"
            onClick={() => {
              table.resetColumnFilters();
              setClears((n) => n + 1);
            }}
          >
            <FilterX aria-hidden="true" className="size-3.5" />
            Clear filters
          </Button>
        ) : null}
        {hideable.length > 1 ? (
          <M.Root>
            <M.Trigger asChild>
              <Button variant="secondary" size="xs">
                <Columns3 aria-hidden="true" className="size-3.5" />
                Columns
              </Button>
            </M.Trigger>
            <MenuContent align="end" className="min-w-44">
              {hideable.map((c) => (
                <M.CheckboxItem
                  key={c.id}
                  checked={c.getIsVisible()}
                  onCheckedChange={(v) => {
                    c.toggleVisibility(v);
                  }}
                  onSelect={(e) => {
                    e.preventDefault();
                  }}
                  className="flex h-8 cursor-pointer select-none items-center gap-2 rounded-[5px] px-2.5 outline-none data-[highlighted]:bg-surface-muted"
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "flex size-3.5 items-center justify-center rounded-[3px] border text-[10px] leading-none",
                      c.getIsVisible() ? "border-accent bg-accent text-white" : "border-border-control",
                    )}
                  >
                    {c.getIsVisible() ? "✓" : ""}
                  </span>
                  {headerText(c.columnDef)}
                </M.CheckboxItem>
              ))}
            </MenuContent>
          </M.Root>
        ) : null}
      </div>
      {banner}
      {error ? (
        <div className="p-4">
          <ErrorState error={error} {...(onRetry ? { onRetry } : {})} />
        </div>
      ) : nothingAtAll ? (
        <div className="p-6">{empty}</div>
      ) : (
        <div className={cn("min-w-0 overflow-auto", fill && "min-h-0 flex-1")}>
          <table aria-label={label} className="w-full border-collapse text-[13px]" aria-busy={loading}>
            <thead className="sticky top-0 z-10 bg-ground">
              <tr className="shadow-[inset_0_-1px_0_var(--border)]">
                {table.getHeaderGroups()[0]?.headers.map((h) => {
                  const meta = h.column.columnDef.meta;
                  const sort = h.column.getIsSorted();
                  const canSort = h.column.getCanSort();
                  return (
                    <th
                      key={h.id}
                      scope="col"
                      aria-sort={
                        sort === "asc"
                          ? "ascending"
                          : sort === "desc"
                            ? "descending"
                            : canSort
                              ? "none"
                              : undefined
                      }
                      className={cn(
                        "h-9 whitespace-nowrap px-3 text-left font-medium text-ink-secondary first:pl-4 last:pr-4",
                        meta?.width,
                        meta?.align === "right" && "text-right",
                        meta?.align === "center" && "text-center",
                      )}
                    >
                      {h.isPlaceholder ? null : canSort ? (
                        <button
                          type="button"
                          onClick={h.column.getToggleSortingHandler()}
                          className="group inline-flex items-center gap-1 rounded hover:text-ink"
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          {sort === "asc" ? (
                            <ArrowUp aria-hidden="true" className="size-3.5 text-ink" />
                          ) : sort === "desc" ? (
                            <ArrowDown aria-hidden="true" className="size-3.5 text-ink" />
                          ) : (
                            <ArrowUpDown
                              aria-hidden="true"
                              className="size-3.5 opacity-0 group-hover:opacity-60"
                            />
                          )}
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
              {anyFilter ? (
                <tr className="bg-surface shadow-[inset_0_-1px_0_var(--border)]">
                  {table.getHeaderGroups()[0]?.headers.map((h) => {
                    const filter = h.column.columnDef.meta?.filter;
                    return (
                      <th key={h.id} scope="col" className="px-3 py-1.5 font-normal first:pl-4 last:pr-4">
                        {filter ? (
                          <FilterCell
                            key={`${h.id}-${clears}`}
                            filter={filter}
                            label={headerText(h.column.columnDef)}
                            value={h.column.getFilterValue()}
                            onChange={(v) => {
                              h.column.setFilterValue(v);
                            }}
                          />
                        ) : null}
                      </th>
                    );
                  })}
                </tr>
              ) : null}
            </thead>
            <tbody>
              {loading && rows.length === 0 ? (
                Array.from({ length: 6 }, (_, i) => (
                  <tr key={i} className="border-t border-rule first:border-t-0">
                    <td colSpan={colCount} className="px-4 py-2.5">
                      <div className="h-4 animate-pulse rounded bg-surface-muted" />
                    </td>
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={colCount} className="px-4 py-10 text-center text-[13px] text-ink-secondary">
                    {emptyText}
                  </td>
                </tr>
              ) : (
                rows.map((r, i) => {
                  const { selected, className, ...extra } = rowProps?.(r.original, i) ?? {};
                  return (
                    <tr
                      key={r.id}
                      className={cn(
                        "h-10 border-t border-rule first:border-t-0 hover:bg-ground",
                        selected &&
                          "bg-accent-tint shadow-[inset_3px_0_0_var(--accent)] hover:bg-accent-tint",
                        className,
                      )}
                      {...extra}
                    >
                      {r.getVisibleCells().map((c) => {
                        const meta = c.column.columnDef.meta;
                        return (
                          <td
                            key={c.id}
                            className={cn(
                              "px-3 py-1.5 align-middle text-ink first:pl-4 last:pr-4",
                              meta?.align === "right" && "text-right",
                              meta?.align === "center" && "text-center",
                              meta?.cellClassName,
                            )}
                          >
                            {flexRender(c.column.columnDef.cell, c.getContext())}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
      <div
        className={cn(
          "tabular flex flex-wrap items-center justify-between gap-3 border-t border-border py-2 text-[12.5px] text-ink-secondary",
          dense ? "px-3" : "px-4",
          !bare && "rounded-b-card",
        )}
      >
        <span className="whitespace-nowrap">
          {total === 0
            ? `No ${many}`
            : `${dense ? "" : "Showing "}${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()}`}
        </span>
        <div className={cn("flex items-center", dense ? "gap-2" : "gap-4")}>
          <label className="flex items-center gap-2">
            <span className={dense ? "sr-only" : ""}>Rows per page</span>
            <Select
              aria-label="Rows per page"
              className="h-7 w-[72px] pl-2 pr-6 text-[12.5px]"
              value={String(pageSize)}
              onChange={(e) => {
                table.setPagination({ pageIndex: 0, pageSize: Number(e.target.value) });
              }}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </label>
          <nav aria-label={`${label} pages`} className="flex items-center gap-1">
            <PageButton
              label="First page"
              disabled={pageIndex === 0}
              onClick={() => {
                table.setPageIndex(0);
              }}
            >
              <ChevronsLeft className="size-3.5" />
            </PageButton>
            <PageButton
              label="Previous page"
              disabled={pageIndex === 0}
              onClick={() => {
                table.setPageIndex(pageIndex - 1);
              }}
            >
              <ChevronLeft className="size-3.5" />
            </PageButton>
            <span className="whitespace-nowrap px-2">
              {dense
                ? `${Math.min(pageIndex + 1, pageCount)} / ${pageCount}`
                : `Page ${Math.min(pageIndex + 1, pageCount)} of ${pageCount}`}
            </span>
            <PageButton
              label="Next page"
              disabled={pageIndex + 1 >= pageCount}
              onClick={() => {
                table.setPageIndex(pageIndex + 1);
              }}
            >
              <ChevronRight className="size-3.5" />
            </PageButton>
            <PageButton
              label="Last page"
              disabled={pageIndex + 1 >= pageCount}
              onClick={() => {
                table.setPageIndex(pageCount - 1);
              }}
            >
              <ChevronsRight className="size-3.5" />
            </PageButton>
          </nav>
        </div>
      </div>
    </div>
  );
}

function PageButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Button
      variant="secondary"
      size="icon"
      className="size-7"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

/** Helpers to read server-mode state into API query parameters. */
export function filterValue(filters: ColumnFiltersState, id: string): string | undefined {
  const v = filters.find((f) => f.id === id)?.value;
  return typeof v === "string" && v ? v : undefined;
}

export function rangeValue(
  filters: ColumnFiltersState,
  id: string,
): [string | undefined, string | undefined] {
  const v = filters.find((f) => f.id === id)?.value;
  if (!Array.isArray(v)) return [undefined, undefined];
  const [a, b] = v as [string, string];
  return [a || undefined, b || undefined];
}

export function sortParam(sorting: SortingState, map: Record<string, string> = {}): string | undefined {
  const s = sorting[0];
  if (!s) return undefined;
  const field = map[s.id] ?? s.id;
  return s.desc ? `-${field}` : field;
}
