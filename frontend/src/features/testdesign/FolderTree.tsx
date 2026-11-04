import * as Menu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, ChevronRight, Folder as FolderIcon, MoreHorizontal, Search } from "lucide-react";
import { useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";
import { MenuContent, MenuItem, MenuShortcut } from "@/components/ui/menu";

import type { Folder } from "./api";

export const DRAG_FOLDER = "application/x-assay-folder";
export const DRAG_CASES = "application/x-assay-cases";

export interface TreeNode {
  folder: Folder;
  children: TreeNode[];
}

export function buildTree(folders: Folder[]): TreeNode[] {
  const nodes = new Map(folders.map((f) => [f.id, { folder: f, children: [] as TreeNode[] }]));
  const roots: TreeNode[] = [];
  for (const n of nodes.values()) {
    const parent = n.folder.parent_id ? nodes.get(n.folder.parent_id) : undefined;
    (parent ? parent.children : roots).push(n);
  }
  const sort = (list: TreeNode[]) => {
    list.sort((a, b) => a.folder.position - b.folder.position || a.folder.name.localeCompare(b.folder.name));
    list.forEach((n) => {
      sort(n.children);
    });
  };
  sort(roots);
  return roots;
}

/** IDs of a folder and all its descendants (a folder cannot be dropped into these). */
export function subtreeIds(folders: Folder[], id: string): Set<string> {
  const out = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const f of folders) {
      if (f.parent_id && out.has(f.parent_id) && !out.has(f.id)) {
        out.add(f.id);
        grew = true;
      }
    }
  }
  return out;
}

export interface FolderActions {
  onNewSubfolder: (parent: Folder) => void;
  onRename: (folder: Folder) => void;
  onToggleArchive: (folder: Folder) => void;
  onDelete: (folder: Folder) => void;
  onMoveFolder: (folder: Folder, parentId: string | null, position?: number) => void;
  onDropCases: (caseIds: string[], folder: Folder) => void;
}

interface Row {
  node: TreeNode;
  depth: number;
}

export function FolderTree({
  folders,
  selectedId,
  onSelect,
  canManage,
  canMoveCases,
  actions,
}: {
  folders: Folder[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  canManage: boolean;
  canMoveCases: boolean;
  actions: FolderActions;
}) {
  const [filter, setFilter] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const tree = useMemo(() => buildTree(folders), [folders]);
  const byId = useMemo(() => new Map(folders.map((f) => [f.id, f])), [folders]);

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const out: Row[] = [];
    const matches = (n: TreeNode): boolean =>
      n.folder.name.toLowerCase().includes(needle) || n.children.some(matches);
    const walk = (list: TreeNode[], depth: number) => {
      for (const n of list) {
        if (needle && !matches(n)) continue;
        out.push({ node: n, depth });
        if (needle || !collapsed.has(n.folder.id)) walk(n.children, depth + 1);
      }
    };
    walk(tree, 0);
    return out;
  }, [tree, filter, collapsed]);

  const blocked = useMemo(
    () => (dragging ? subtreeIds(folders, dragging) : new Set<string>()),
    [dragging, folders],
  );

  const toggle = (id: string, open?: boolean) => {
    setCollapsed((c) => {
      const next = new Set(c);
      const isOpen = !next.has(id);
      if (open ?? !isOpen) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /** Siblings in display order, for reordering (docs/07 §5.4); Alt+↑/↓ from the keyboard. */
  const siblingsOf = (f: Folder) =>
    folders
      .filter((x) => x.parent_id === f.parent_id)
      .sort((a, b) => a.position - b.position || a.name.localeCompare(b.name));
  const reorder = (f: Folder, delta: number) => {
    const sibs = siblingsOf(f);
    const i = sibs.findIndex((x) => x.id === f.id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= sibs.length) return;
    actions.onMoveFolder(f, f.parent_id, j + 1);
  };

  const focusRow = (index: number) => {
    const items = listRef.current?.querySelectorAll<HTMLElement>("[role=treeitem]");
    items?.[Math.max(0, Math.min(index, items.length - 1))]?.focus();
  };

  const onKey = (e: KeyboardEvent, index: number, row: Row) => {
    const id = row.node.folder.id;
    const hasChildren = row.node.children.length > 0;
    if (canManage && e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      reorder(row.node.folder, e.key === "ArrowUp" ? -1 : 1);
    } else if (e.key === "ArrowDown") focusRow(index + 1);
    else if (e.key === "ArrowUp") focusRow(index - 1);
    else if (e.key === "ArrowRight" && hasChildren) toggle(id, true);
    else if (e.key === "ArrowLeft") {
      if (hasChildren && !collapsed.has(id)) toggle(id, false);
      else if (row.node.folder.parent_id) {
        const parentIndex = rows.findIndex((r) => r.node.folder.id === row.node.folder.parent_id);
        focusRow(parentIndex);
      }
    } else if (e.key === "Enter" || e.key === " ") onSelect(id);
    else return;
    e.preventDefault();
  };

  const accepts = (e: DragEvent) =>
    (canManage && e.dataTransfer.types.includes(DRAG_FOLDER)) ||
    (canMoveCases && e.dataTransfer.types.includes(DRAG_CASES));

  const onDrop = (e: DragEvent, target: Folder | null) => {
    e.preventDefault();
    setDropTarget(null);
    const folderId = e.dataTransfer.getData(DRAG_FOLDER);
    if (folderId) {
      const moving = byId.get(folderId);
      if (moving && moving.parent_id !== (target?.id ?? null) && !(target && blocked.has(target.id))) {
        actions.onMoveFolder(moving, target?.id ?? null);
      }
      return;
    }
    const cases = e.dataTransfer.getData(DRAG_CASES);
    if (cases && target) actions.onDropCases(JSON.parse(cases) as string[], target);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <label className="mb-2 flex h-8 items-center gap-1.5 rounded-control border border-border bg-surface px-2 text-[13px] focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent-tint">
        <Search aria-hidden="true" className="size-3.5 text-ink-muted" />
        <input
          type="text"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
          }}
          placeholder="Filter folders"
          aria-label="Filter folders"
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-muted"
        />
      </label>
      <div
        role="tree"
        tabIndex={-1}
        aria-label="Repository folders"
        ref={listRef}
        className="min-h-0 flex-1 overflow-y-auto"
        onDragOver={(e) => {
          if (canManage && e.dataTransfer.types.includes(DRAG_FOLDER) && e.target === e.currentTarget) {
            e.preventDefault();
            setDropTarget("root");
          }
        }}
        onDragLeave={() => {
          setDropTarget(null);
        }}
        onDrop={(e) => {
          if (e.target === e.currentTarget) onDrop(e, null);
        }}
      >
        <div
          role="treeitem"
          aria-selected={selectedId === null}
          tabIndex={selectedId === null ? 0 : -1}
          onClick={() => {
            onSelect(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              focusRow(1);
            } else if (e.key === "Enter") onSelect(null);
          }}
          onDragOver={(e) => {
            if (canManage && e.dataTransfer.types.includes(DRAG_FOLDER)) {
              e.preventDefault();
              setDropTarget("root");
            }
          }}
          onDrop={(e) => {
            onDrop(e, null);
          }}
          className={cn(
            "flex h-[30px] cursor-pointer items-center gap-2 rounded-control px-2 text-[13px] text-ink-strong hover:bg-ground",
            selectedId === null && "bg-accent-tint font-semibold text-accent-ink hover:bg-accent-tint",
            dropTarget === "root" && "ring-2 ring-accent",
          )}
        >
          All cases
        </div>
        {rows.map((row, index) => {
          const f = row.node.folder;
          const open = !collapsed.has(f.id);
          const selected = f.id === selectedId;
          return (
            <div
              key={f.id}
              role="treeitem"
              aria-selected={selected}
              aria-expanded={row.node.children.length ? open : undefined}
              aria-level={row.depth + 1}
              tabIndex={selected ? 0 : -1}
              draggable={canManage}
              onDragStart={(e) => {
                e.dataTransfer.setData(DRAG_FOLDER, f.id);
                e.dataTransfer.effectAllowed = "move";
                setDragging(f.id);
              }}
              onDragEnd={() => {
                setDragging(null);
                setDropTarget(null);
              }}
              onDragOver={(e) => {
                if (!accepts(e) || blocked.has(f.id)) return;
                e.preventDefault();
                setDropTarget(f.id);
              }}
              onDrop={(e) => {
                e.stopPropagation();
                onDrop(e, f);
              }}
              onClick={() => {
                onSelect(f.id);
              }}
              onKeyDown={(e) => {
                onKey(e, index + 1, row);
              }}
              data-folder={f.name}
              className={cn(
                "group flex h-[30px] cursor-pointer items-center gap-1.5 rounded-control pr-1 text-[13px] text-ink-strong hover:bg-ground",
                selected && "bg-accent-tint font-semibold text-accent-ink hover:bg-accent-tint",
                f.archived && "text-ink-muted",
                dropTarget === f.id && "ring-2 ring-accent",
              )}
              style={{ paddingLeft: 4 + row.depth * 14 }}
            >
              {row.node.children.length ? (
                <button
                  type="button"
                  tabIndex={-1}
                  aria-label={open ? `Collapse ${f.name}` : `Expand ${f.name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggle(f.id);
                  }}
                  className="rounded p-0.5 text-ink-faint hover:bg-surface-muted hover:text-ink-secondary"
                >
                  {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                </button>
              ) : (
                <span className="w-[18px] shrink-0" aria-hidden="true" />
              )}
              <FolderIcon
                aria-hidden="true"
                className={cn("size-[15px] shrink-0", selected ? "text-accent" : "text-ink-muted")}
              />
              <span className="min-w-0 flex-1 truncate">
                {f.name}
                {f.archived ? <span className="ml-1 text-xs">(archived)</span> : null}
              </span>
              <span className="tabular text-[11.5px] text-ink-muted" aria-label={`${f.total_count} cases`}>
                {f.total_count.toLocaleString()}
              </span>
              {canManage ? (
                <FolderMenu
                  folder={f}
                  actions={actions}
                  canUp={siblingsOf(f)[0]?.id !== f.id}
                  canDown={siblingsOf(f).at(-1)?.id !== f.id}
                  onReorder={(d) => {
                    reorder(f, d);
                  }}
                />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FolderMenu({
  folder,
  actions,
  canUp,
  canDown,
  onReorder,
}: {
  folder: Folder;
  actions: FolderActions;
  canUp: boolean;
  canDown: boolean;
  onReorder: (delta: number) => void;
}) {
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={`Folder actions for ${folder.name}`}
        onClick={(e) => {
          e.stopPropagation();
        }}
        className="rounded p-0.5 text-ink-muted opacity-0 hover:bg-surface-muted hover:text-ink focus:opacity-100 group-hover:opacity-100 group-focus:opacity-100 data-[state=open]:opacity-100"
      >
        <MoreHorizontal className="size-4" />
      </Menu.Trigger>
      <MenuContent
        align="end"

        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        {!folder.archived ? (
          <MenuItem
            onSelect={() => {
              actions.onNewSubfolder(folder);
            }}
          >
            New subfolder
          </MenuItem>
        ) : null}
        <MenuItem
          onSelect={() => {
            actions.onRename(folder);
          }}
        >
          Rename
        </MenuItem>
        {canUp ? (
          <MenuItem
            onSelect={() => {
              onReorder(-1);
            }}
          >
            Move up <MenuShortcut>Alt ↑</MenuShortcut>
          </MenuItem>
        ) : null}
        {canDown ? (
          <MenuItem
            onSelect={() => {
              onReorder(1);
            }}
          >
            Move down <MenuShortcut>Alt ↓</MenuShortcut>
          </MenuItem>
        ) : null}
        <MenuItem
          onSelect={() => {
            actions.onToggleArchive(folder);
          }}
        >
          {folder.archived ? "Restore" : "Archive"}
        </MenuItem>
        <MenuItem
          danger
          onSelect={() => {
            actions.onDelete(folder);
          }}
        >
          Delete
        </MenuItem>
      </MenuContent>
    </Menu.Root>
  );
}
