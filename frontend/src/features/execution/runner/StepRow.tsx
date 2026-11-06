import { AlertTriangle, Check, Loader2, Paperclip } from "lucide-react";
import { forwardRef, useId, useRef, useState, type ClipboardEvent } from "react";

import type { Attachment } from "@/features/testdesign/api";
import { MarkdownView } from "@/components/common/Markdown";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { cn } from "@/lib/utils";

import type { StepStatus } from "../api";
import type { SaveState, StepLocal } from "./useStepSaver";

type Version = { action: string; expected_result: string | null; data: string | null; position: number };

/** Step status buttons in BR-09 order with their keys (docs/07 §5.9). */
const BUTTONS: [Exclude<StepStatus, "not_run">, string, string][] = [
  ["passed", "P", "Pass"],
  ["failed", "F", "Fail"],
  ["blocked", "B", "Block"],
  ["skipped", "S", "Skip"],
];

const PRESSED: Record<string, string> = {
  passed: "border-[var(--status-pass-bar)] bg-[var(--status-pass-bg)] text-[var(--status-pass-fg)]",
  failed: "border-[var(--status-fail-bar)] bg-[var(--status-fail-bg)] text-[var(--status-fail-fg)]",
  blocked: "border-[var(--status-blocked-bar)] bg-[var(--status-blocked-bg)] text-[var(--status-blocked-fg)]",
  skipped: "border-[var(--status-skip-bar)] bg-[var(--status-skip-bg)] text-[var(--status-skip-fg)]",
};

export function SaveIndicator({ state }: { state: SaveState | undefined }) {
  if (state === "saving")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-ink-secondary">
        <Loader2 aria-hidden="true" className="size-3 animate-spin" /> Saving
      </span>
    );
  if (state === "error")
    return (
      <span role="alert" className="inline-flex items-center gap-1 text-xs font-medium text-danger">
        <AlertTriangle aria-hidden="true" className="size-3" /> Not saved – retrying
      </span>
    );
  if (state === "saved")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-ink-secondary">
        <Check aria-hidden="true" className="size-3" /> Saved
      </span>
    );
  return null;
}

export interface StepRowProps {
  step: Version;
  value: StepLocal;
  saveState: SaveState | undefined;
  focused: boolean;
  editable: boolean;
  evidence: Attachment[];
  uploading: boolean;
  onFocus: () => void;
  onStatus: (s: StepStatus) => void;
  onText: (field: "actual_result" | "comment", v: string) => void;
  onAttach: (file: File) => void;
}

/** One step of the runner grid: action, expected result, P/F/B/S, actual result, comment, evidence. */
export const StepRow = forwardRef<HTMLLIElement, StepRowProps>(function StepRow(
  { step, value, saveState, focused, editable, evidence, uploading, onFocus, onStatus, onText, onAttach },
  ref,
) {
  const n = step.position;
  const id = useId();
  const file = useRef<HTMLInputElement>(null);
  const [showComment, setShowComment] = useState(value.comment !== "");
  const failed = value.status === "failed";
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const image = [...e.clipboardData.files].find((f) => f.type.startsWith("image/"));
    if (image) {
      e.preventDefault();
      onAttach(image);
    }
  };
  return (
    <li
      ref={ref}
      tabIndex={-1}
      data-step={n}
      aria-label={`Step ${n}`}
      aria-current={focused ? "step" : undefined}
      className={cn(
        "grid grid-cols-[32px_minmax(0,1fr)] gap-x-3 border-t border-border px-4 py-3 outline-none first:border-t-0",
        focused && "bg-accent-tint/40 shadow-[inset_3px_0_0_var(--accent)]",
      )}
    >
      <span className="tabular pt-0.5 text-[13px] font-medium text-ink-secondary">{n}</span>
      <div className="grid min-w-0 gap-2">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">Action</p>
            <MarkdownView text={step.action} />
            {step.data ? <p className="mt-1 text-xs text-ink-secondary">Data: {step.data}</p> : null}
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">Expected</p>
            {step.expected_result ? (
              <MarkdownView text={step.expected_result} />
            ) : (
              <p className="text-ink-muted">—</p>
            )}
          </div>
        </div>
        {editable ? (
          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label={`Step ${n} result`} className="flex gap-1.5">
              {BUTTONS.map(([status, key, label]) => (
                <button
                  key={status}
                  type="button"
                  aria-pressed={value.status === status}
                  aria-keyshortcuts={key}
                  title={`${label} (${key})`}
                  onClick={() => {
                    onFocus();
                    onStatus(value.status === status ? "not_run" : status);
                  }}
                  className={cn(
                    "h-8 min-w-[72px] rounded-control border px-2.5 text-[12.5px] font-semibold transition-colors",
                    value.status === status
                      ? PRESSED[status]
                      : "border-border-control bg-surface text-ink-secondary hover:bg-surface-muted",
                  )}
                >
                  {label} <span className="font-mono text-[11px] opacity-70">{key}</span>
                </button>
              ))}
            </div>
            <span className="flex-1" />
            <SaveIndicator state={saveState} />
          </div>
        ) : (
          <div>
            <StatusBadge kind="execution" status={value.status} />
          </div>
        )}
        {failed || value.actual_result ? (
          <div className="grid gap-1 text-[13px]">
            <label htmlFor={`${id}-actual`} className="font-medium text-ink">
              Actual result{failed ? <span aria-hidden="true"> *</span> : null}
            </label>
            <Textarea
              id={`${id}-actual`}
              rows={2}
              data-actual={n}
              aria-required={failed}
              readOnly={!editable}
              value={value.actual_result}
              placeholder="What happened instead (paste a screenshot to attach it)"
              onFocus={onFocus}
              onPaste={onPaste}
              onChange={(e) => {
                onText("actual_result", e.target.value);
              }}
            />
          </div>
        ) : null}
        {showComment ? (
          <div className="grid gap-1 text-[13px]">
            <label htmlFor={`${id}-comment`} className="font-medium text-ink">
              Comment
            </label>
            <Textarea
              id={`${id}-comment`}
              rows={2}
              readOnly={!editable}
              value={value.comment}
              onPaste={onPaste}
              onChange={(e) => {
                onText("comment", e.target.value);
              }}
            />
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {evidence.map((a) => (
            <a
              key={a.id}
              href={a.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-link hover:underline"
            >
              <Paperclip aria-hidden="true" className="size-3" />
              {a.file_name}
            </a>
          ))}
          {editable ? (
            <>
              <input
                ref={file}
                type="file"
                className="sr-only"
                aria-label={`Attach evidence to step ${n}`}
                data-attach={n}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onAttach(f);
                  e.target.value = "";
                }}
              />
              <Button variant="ghost" size="xs" disabled={uploading} onClick={() => file.current?.click()}>
                <Paperclip aria-hidden="true" className="size-3.5" />
                {uploading ? "Uploading…" : "Attach (A)"}
              </Button>
              {!showComment ? (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => {
                    setShowComment(true);
                  }}
                >
                  Add comment
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </li>
  );
});
