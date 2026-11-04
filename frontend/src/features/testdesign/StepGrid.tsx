import { GripVertical, MoreHorizontal } from "lucide-react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";

import { MarkdownEditor } from "@/components/common/Markdown";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MenuContent, MenuItem, MenuShortcut } from "@/components/ui/menu";

import type { Attachment } from "./api";
import { AttachmentList } from "./AttachmentList";

export interface StepDraft {
  /** Stable client key for React and focus management. */
  key: string;
  /** Step id of the latest version (attachments carry forward to the same position). */
  id?: string;
  action: string;
  expected_result: string;
  data: string;
}

let counter = 0;
export const newStep = (patch: Partial<StepDraft> = {}): StepDraft => ({
  key: `s${Date.now().toString(36)}${(counter++).toString(36)}`,
  action: "",
  expected_result: "",
  data: "",
  ...patch,
});

/** Tab-separated or multi-line paste → steps (docs/07 §5.5: paste rows from Excel). */
export function parsePastedSteps(text: string): { action: string; expected_result: string }[] | null {
  const rows = text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .filter((r) => r.trim() !== "");
  if (rows.length < 2 && !text.includes("\t")) return null;
  return rows.map((r) => {
    const [action = "", expected = ""] = r.split("\t");
    return { action: action.trim(), expected_result: expected.trim() };
  });
}

type Col = "action" | "expected_result" | "data";

/**
 * StepGrid (docs/07 §5.5, NFR-UX-01): Enter in Expected adds a step, Tab moves between cells,
 * Alt+↑/↓ reorders, Ctrl+D duplicates, Ctrl+Backspace deletes (undoable).
 */
export function StepGrid({
  steps,
  onChange,
  showData,
  errors,
  stepAttachments,
}: {
  steps: StepDraft[];
  onChange: (steps: StepDraft[]) => void;
  showData: boolean;
  errors: Record<number, string>;
  stepAttachments: {
    byStep: Record<string, Attachment[]>;
    canUpload: boolean;
    maxMb: number;
    onChanged: () => void;
  } | null;
}) {
  const grid = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<{ key: string; col: Col } | null>(null);
  const setPendingFocus = (v: { key: string; col: Col }) => {
    pendingFocus.current = v;
  };
  const [undo, setUndo] = useState<{ step: StepDraft; index: number } | null>(null);
  const [dragKey, setDragKey] = useState<string | null>(null);

  // Focus the cell an action asked for once the new step order has rendered.
  useEffect(() => {
    const want = pendingFocus.current;
    if (!want) return;
    pendingFocus.current = null;
    grid.current
      ?.querySelector<HTMLTextAreaElement>(`[data-step="${want.key}"][data-col="${want.col}"]`)
      ?.focus();
  }, [steps]);

  const update = (i: number, patch: Partial<StepDraft>) => {
    onChange(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  };
  const insertAfter = (i: number, step = newStep()) => {
    const next = [...steps];
    next.splice(i + 1, 0, step);
    onChange(next);
    setPendingFocus({ key: step.key, col: "action" });
  };
  const move = (i: number, delta: number, col: Col) => {
    const j = i + delta;
    if (j < 0 || j >= steps.length) return;
    const next = [...steps];
    const [s] = next.splice(i, 1);
    next.splice(j, 0, s as StepDraft);
    onChange(next);
    setPendingFocus({ key: (s as StepDraft).key, col });
  };
  const remove = (i: number) => {
    const s = steps[i];
    if (!s) return;
    const next = steps.filter((_, j) => j !== i);
    onChange(next.length ? next : [newStep()]);
    setUndo({ step: s, index: i });
    const neighbour = next[Math.min(i, next.length - 1)];
    if (neighbour) setPendingFocus({ key: neighbour.key, col: "action" });
  };
  const duplicate = (i: number) => {
    const s = steps[i];
    if (s) insertAfter(i, newStep({ action: s.action, expected_result: s.expected_result, data: s.data }));
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>, i: number, col: Col) => {
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === "Enter" && !e.shiftKey && !mod && !e.altKey && col === "expected_result") {
      e.preventDefault();
      insertAfter(i);
    } else if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      move(i, e.key === "ArrowUp" ? -1 : 1, col);
    } else if (mod && (e.key === "d" || e.key === "D")) {
      e.preventDefault();
      duplicate(i);
    } else if (mod && e.key === "Backspace") {
      e.preventDefault();
      remove(i);
    }
  };

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>, i: number) => {
    const rows = parsePastedSteps(e.clipboardData.getData("text/plain"));
    if (!rows) return;
    e.preventDefault();
    const created = rows.map((r) => newStep(r));
    const next = [...steps];
    const current = steps[i];
    const replaceCurrent = current && !current.action && !current.expected_result;
    next.splice(replaceCurrent ? i : i + 1, replaceCurrent ? 1 : 0, ...created);
    onChange(next.slice(0, 100));
  };

  const cell =
    "min-h-9 w-full resize-y rounded border border-transparent bg-transparent px-2 py-1.5 text-[13.5px] leading-6 text-ink hover:border-border focus:border-[var(--focus-ring)] focus:bg-surface focus:outline-none focus:ring-2 focus:ring-avatar aria-[invalid=true]:border-danger";
  const cols = showData
    ? "grid-cols-[44px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.7fr)_36px]"
    : "grid-cols-[44px_minmax(0,1fr)_minmax(0,1fr)_36px]";

  return (
    <div>
      <div
        ref={grid}
        role="table"
        aria-label="Steps"
        className="overflow-hidden rounded-card border border-border bg-surface"
      >
        <div
          role="row"
          className={cn(
            "grid border-b border-border bg-ground text-[12.5px] font-medium text-ink-secondary",
            cols,
          )}
        >
          <div role="columnheader" className="px-2 py-2">
            #
          </div>
          <div role="columnheader" className="px-2 py-2">
            Action *
          </div>
          <div role="columnheader" className="px-2 py-2">
            Expected result
          </div>
          {showData ? (
            <div role="columnheader" className="px-2 py-2">
              Data
            </div>
          ) : null}
          <div role="columnheader" className="sr-only">
            Actions
          </div>
        </div>
        {steps.map((s, i) => (
          // Drop target for drag reordering; Alt+↑/↓ is the keyboard alternative.
          // eslint-disable-next-line jsx-a11y/interactive-supports-focus
          <div
            key={s.key}
            role="row"
            className={cn(
              "grid border-t border-rule first-of-type:border-t-0 focus-within:bg-[#f8faff]",
              cols,
              dragKey === s.key && "opacity-50",
            )}
            onDragOver={(e) => {
              if (dragKey) e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              const from = steps.findIndex((x) => x.key === dragKey);
              if (from >= 0 && from !== i) move(from, i - from, "action");
              setDragKey(null);
            }}
          >
            <div role="cell" className="flex items-start gap-0.5 px-1 py-2 text-xs text-ink-muted">
              <span
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "move";
                  setDragKey(s.key);
                }}
                onDragEnd={() => {
                  setDragKey(null);
                }}
                className="cursor-grab"
                aria-hidden="true"
              >
                <GripVertical className="size-3.5" />
              </span>
              {i + 1}
            </div>
            <div role="cell" className="py-1">
              <MarkdownEditor
                aria-label={`Step ${i + 1} action`}
                aria-invalid={Boolean(errors[i])}
                data-step={s.key}
                data-col="action"
                rows={1}
                value={s.action}
                className={cell}
                onChange={(e) => {
                  update(i, { action: e.target.value });
                }}
                onKeyDown={(e) => {
                  onKey(e, i, "action");
                }}
                onPaste={(e) => {
                  onPaste(e, i);
                }}
              />
              {errors[i] ? <p className="px-2 text-xs text-danger">{errors[i]}</p> : null}
            </div>
            <div role="cell" className="py-1">
              <MarkdownEditor
                aria-label={`Step ${i + 1} expected result`}
                data-step={s.key}
                data-col="expected_result"
                rows={1}
                value={s.expected_result}
                className={cell}
                onChange={(e) => {
                  update(i, { expected_result: e.target.value });
                }}
                onKeyDown={(e) => {
                  onKey(e, i, "expected_result");
                }}
              />
              {stepAttachments &&
              s.id &&
              (stepAttachments.byStep[s.id]?.length || stepAttachments.canUpload) ? (
                <div className="px-2 pb-1">
                  <AttachmentList
                    attachments={stepAttachments.byStep[s.id] ?? []}
                    entityType="test_case_step"
                    entityId={s.id}
                    canUpload={stepAttachments.canUpload}
                    canRemove={() => stepAttachments.canUpload}
                    maxMb={stepAttachments.maxMb}
                    onChanged={stepAttachments.onChanged}
                    compact
                    label={`step ${i + 1}`}
                  />
                </div>
              ) : null}
            </div>
            {showData ? (
              <div role="cell" className="py-1">
                <MarkdownEditor
                  aria-label={`Step ${i + 1} data`}
                  data-step={s.key}
                  data-col="data"
                  rows={1}
                  value={s.data}
                  className={cell}
                  onChange={(e) => {
                    update(i, { data: e.target.value });
                  }}
                  onKeyDown={(e) => {
                    onKey(e, i, "data");
                  }}
                />
              </div>
            ) : null}
            <div role="cell" className="flex items-start justify-center py-2">
              <StepMenu
                n={i + 1}
                first={i === 0}
                last={i === steps.length - 1}
                onUp={() => {
                  move(i, -1, "action");
                }}
                onDown={() => {
                  move(i, 1, "action");
                }}
                onDuplicate={() => {
                  duplicate(i);
                }}
                onDelete={() => {
                  remove(i);
                }}
              />
            </div>
          </div>
        ))}
        <div className="border-t border-border px-2 py-1.5">
          <Button
            variant="ghost"
            size="sm"
            disabled={steps.length >= 100}
            onClick={() => {
              insertAfter(steps.length - 1);
            }}
          >
            + Add step
          </Button>
        </div>
      </div>
      {undo ? (
        <div role="status" className="mt-2 flex items-center gap-2 text-sm text-ink-secondary">
          Step {undo.index + 1} deleted.
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              const next = [...steps];
              next.splice(undo.index, 0, undo.step);
              onChange(next);
              setUndo(null);
            }}
          >
            Undo
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function StepMenu({
  n,
  first,
  last,
  onUp,
  onDown,
  onDuplicate,
  onDelete,
}: {
  n: number;
  first: boolean;
  last: boolean;
  onUp: () => void;
  onDown: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  return (
    <Menu.Root>
      <Menu.Trigger aria-label={`Step ${n} actions`} className="rounded p-1 text-ink-muted hover:bg-ground">
        <MoreHorizontal className="size-4" />
      </Menu.Trigger>
      <MenuContent align="end">
        <MenuItem disabled={first} onSelect={onUp}>
          Move up <MenuShortcut>Alt ↑</MenuShortcut>
        </MenuItem>
        <MenuItem disabled={last} onSelect={onDown}>
          Move down <MenuShortcut>Alt ↓</MenuShortcut>
        </MenuItem>
        <MenuItem onSelect={onDuplicate}>
          Duplicate <MenuShortcut>Ctrl D</MenuShortcut>
        </MenuItem>
        <MenuItem danger onSelect={onDelete}>
          Delete <MenuShortcut>Ctrl ⌫</MenuShortcut>
        </MenuItem>
      </MenuContent>
    </Menu.Root>
  );
}
