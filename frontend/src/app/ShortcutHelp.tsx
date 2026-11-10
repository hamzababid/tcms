import { useEffect } from "react";

import { Kbd } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

/** docs/07 §10, grouped by scope. The runner adds its own list (RunnerPage) for its page keys. */
const GROUPS: [string, [string, string][]][] = [
  [
    "Everywhere",
    [
      ["/", "Search and command palette"],
      ["?", "This help"],
      ["G then W", "My Work"],
      ["G then R / C / D", "Repository, cycles, bugs"],
      ["G then Q / T / O", "Requirements, traceability, overview"],
      ["G then P", "Project switcher"],
    ],
  ],
  ["Lists", [["J / K, X, Enter, Esc", "Move, select, open, close the panel"]]],
  [
    "Repository",
    [
      ["C", "New case in the current folder"],
      ["F", "New folder"],
      ["↑ / ↓, ← / →", "Move in the folder tree, collapse or expand"],
      ["Shift + F10", "Actions for the focused folder"],
      ["Alt + ↑ / ↓", "Move the focused folder up or down"],
    ],
  ],
  [
    "Case editor",
    [
      ["Ctrl + S", "Save"],
      ["Ctrl + Shift + S", "Save and new"],
      ["Enter (in expected)", "New step"],
      ["Alt + ↑ / ↓", "Move the step"],
      ["Ctrl + D", "Duplicate the step"],
      ["Ctrl + Backspace", "Delete the step"],
    ],
  ],
  [
    "Runner",
    [
      ["Space", "Start the attempt"],
      ["P / F / B / S", "Set the step status"],
      ["J / K or ↓ / ↑", "Next or previous step"],
      ["D", "Link a bug to the step"],
      ["A", "Attach a file to the step"],
      ["Ctrl + Enter", "Finish the run"],
      ["Shift + N / Shift + P", "Next or previous run"],
    ],
  ],
];

/**
 * `?` opens the shortcut list (docs/07 §10, L20) unless a page already handled the key (the runner shows
 * its own list and calls preventDefault). Checked after the event has reached every listener.
 */
export function useShortcutHelpKey(onOpen: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "?" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
      if (document.querySelector("[role=dialog]")) return;
      window.setTimeout(() => {
        if (!e.defaultPrevented) onOpen();
      }, 0);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [onOpen]);
}

export function ShortcutHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Keyboard shortcuts"
      wide
      footer={
        <Button
          onClick={() => {
            onOpenChange(false);
          }}
        >
          Close
        </Button>
      }
    >
      {/* Its own scroll area, focusable so the keyboard can scroll it (axe scrollable-region-focusable). */}
      <div
        role="region"
        aria-label="Shortcut list"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region needs a tab stop
        tabIndex={0}
        className="-mx-1 grid max-h-[min(60vh,520px)] gap-x-8 gap-y-4 overflow-y-auto px-1 md:grid-cols-2"
      >
        {GROUPS.map(([scope, keys], i) => (
          <section key={scope} aria-labelledby={`shortcut-scope-${i}`}>
            <h3
              id={`shortcut-scope-${i}`}
              className="mb-1.5 text-[12px] font-semibold uppercase tracking-[0.06em] text-ink-muted"
            >
              {scope}
            </h3>
            <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[13px]">
              {keys.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt>
                    <Kbd>{k}</Kbd>
                  </dt>
                  <dd className="text-ink-secondary">{v}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Dialog>
  );
}
