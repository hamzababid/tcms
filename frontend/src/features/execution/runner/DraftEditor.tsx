import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/api/client";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import { errorMessage, useToast } from "@/components/common/feedback";
import { MarkdownView } from "@/components/common/Markdown";
import { Kbd } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/field";
import { uploadAttachment, type Attachment } from "@/features/testdesign/api";
import { cn } from "@/lib/utils";

import {
  finalizeAttempt,
  getResult,
  passRemaining,
  patchAttempt,
  type Outcome,
  type ResultRead,
  type RunRead,
  type StepStatus,
} from "../api";
import { previewOf } from "../rollup";
import { StepRow } from "./StepRow";
import { useStepSaver } from "./useStepSaver";

type ReasonAsk = { outcome: Outcome | null; title: string } | null;

const RUN_OUTCOMES: [Outcome, string][] = [
  ["blocked", "Block run…"],
  ["skipped", "Skip…"],
  ["not_applicable", "N/A…"],
];

const TEXT_OUTCOMES: [Outcome, string][] = [
  ["passed", "Passed"],
  ["failed", "Failed"],
  ["blocked", "Blocked"],
  ["skipped", "Skipped"],
  ["not_applicable", "N/A"],
];

/**
 * The open attempt (docs/07 §5.9): record steps with P/F/B/S, evidence, comment and build, then Finish
 * (Ctrl+Enter). The preview mirrors BR-09; the server decides and the reasons of BR-10 / K2 are asked for.
 */
export function DraftEditor({
  run,
  draft,
  editable,
  onFinished,
  onHelp,
}: {
  run: RunRead;
  draft: ResultRead;
  editable: boolean;
  onFinished: (status: string) => void;
  onHelp: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const version = run.version;
  const isText = version?.format === "text";
  const saver = useStepSaver(draft.id, draft.steps);
  const [focus, setFocus] = useState(0);
  const [evidence, setEvidence] = useState<Record<string, Attachment[]>>(() =>
    Object.fromEntries(draft.steps.map((s) => [s.step_id, s.attachments])),
  );
  const [uploading, setUploading] = useState<string | null>(null);
  const [comment, setComment] = useState(draft.comment ?? "");
  const [build, setBuild] = useState(draft.build ?? "");
  const [textOutcome, setTextOutcome] = useState<Outcome | null>(null);
  const [ask, setAsk] = useState<ReasonAsk>(null);
  const [confirmPassAll, setConfirmPassAll] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [fieldTimer, setFieldTimer] = useState<number | undefined>(undefined);
  const rows = useRef<(HTMLLIElement | null)[]>([]);
  // Step index whose actual-result box should get focus once it has rendered (docs/02 §7.4).
  const focusActual = useRef<number | null>(null);
  useLayoutEffect(() => {
    const i = focusActual.current;
    if (i === null) return;
    const box = rows.current[i]?.querySelector<HTMLTextAreaElement>("textarea[data-actual]");
    if (box) {
      focusActual.current = null;
      box.focus();
    }
  });

  const steps = useMemo(() => {
    const byId = new Map((version?.steps ?? []).map((s) => [s.id, s]));
    return draft.steps.map((d) => ({ draft: d, version: byId.get(d.step_id) }));
  }, [draft.steps, version?.steps]);
  const statuses: StepStatus[] = steps.map((s) => saver.values[s.draft.step_id]?.status ?? "not_run");
  const preview = previewOf(statuses);
  const correction = draft.corrects_result_id !== null;

  const saveAttempt = (fields: { comment?: string; build?: string }) => {
    window.clearTimeout(fieldTimer);
    setFieldTimer(
      window.setTimeout(() => {
        patchAttempt(draft.id, {
          ...(fields.comment !== undefined ? { comment: fields.comment } : {}),
          ...(fields.build !== undefined ? { build: fields.build } : {}),
        }).catch((e: unknown) => {
          toast(errorMessage(e), "error");
        });
      }, 600),
    );
  };

  const setStatus = (i: number, status: StepStatus) => {
    const s = steps[i];
    if (!s || !editable) return;
    saver.update(s.draft.step_id, { status }, true);
    if (status === "failed") {
      // docs/02 §7.4: Fail focuses the actual result (required before Finish).
      // Focus after the render that shows the box; a timer can fire before that commit.
      focusActual.current = i;
    } else if (status !== "not_run" && i + 1 < steps.length) {
      setFocus(i + 1);
      rows.current[i + 1]?.focus();
    }
  };

  const attach = async (stepId: string, stepResultId: string, file: File) => {
    setUploading(stepId);
    try {
      const a = await uploadAttachment("test_step_result", stepResultId, file);
      setEvidence((cur) => ({ ...cur, [stepId]: [...(cur[stepId] ?? []), a] }));
      toast(`Attached ${a.file_name}`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setUploading(null);
    }
  };

  const finish = async (outcome: Outcome | null, reason: string | null) => {
    if (finishing) return;
    setFinishing(true);
    try {
      await saver.flushAll();
      window.clearTimeout(fieldTimer);
      if (isText || comment !== (draft.comment ?? "") || build !== (draft.build ?? ""))
        await patchAttempt(draft.id, { comment, build });
      const done = await finalizeAttempt(draft.id, { outcome, reason });
      setAsk(null);
      void qc.invalidateQueries({ queryKey: ["run"] });
      void qc.invalidateQueries({ queryKey: ["cycle", run.cycle.id] });
      void qc.invalidateQueries({ queryKey: ["me", "work"] });
      onFinished(done.result.status ?? "");
    } catch (e) {
      if (e instanceof ApiError && e.code === "reason_required")
        setAsk({ outcome, title: correction ? "Why is this result corrected?" : "Reason for this result" });
      else if (e instanceof ApiError && e.code === "actual_result_required") {
        const first = /steps\[(\d+)\]/.exec(e.errors[0]?.field ?? "")?.[1];
        if (first !== undefined) {
          setFocus(Number(first));
          rows.current[Number(first)]?.querySelector<HTMLTextAreaElement>("textarea[data-actual]")?.focus();
        }
        toast(e.detail ?? "Describe the actual result of every failed step", "error");
      } else toast(errorMessage(e), "error");
    } finally {
      setFinishing(false);
    }
  };

  /** Finish button / Ctrl+Enter: ask for the reason first when one is needed (BR-10, K2, correction). */
  const requestFinish = () => {
    if (isText) {
      if (!textOutcome) {
        toast("Choose the result of this run", "error");
        return;
      }
      if (
        textOutcome === "blocked" ||
        textOutcome === "skipped" ||
        textOutcome === "not_applicable" ||
        correction
      )
        setAsk({ outcome: textOutcome, title: "Reason for this result" });
      else void finish(textOutcome, null);
      return;
    }
    if (preview.incomplete) {
      toast(preview.hint, "error");
      return;
    }
    if (preview.needsReason || correction)
      setAsk({
        outcome: null,
        title: correction ? "Why is this result corrected?" : "Why is the run blocked?",
      });
    else void finish(null, null);
  };

  const doPassAll = async () => {
    setConfirmPassAll(false);
    try {
      await saver.flushAll();
      const n = await passRemaining(draft.id);
      saver.applyServer((await getResult(draft.id)).steps);
      toast(`Passed ${n} remaining ${n === 1 ? "step" : "steps"}`);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const passAll = () => {
    if (statuses.filter((s) => s === "not_run").length > 10) setConfirmPassAll(true);
    else void doPassAll();
  };

  // Runner keys (docs/02 §7.4): P/F/B/S, J/K/↑/↓, A, Ctrl+Enter, ?; off while typing (except Esc, Ctrl+Enter).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (editable) requestFinish();
        return;
      }
      if (typing) {
        if (e.key === "Escape") t.blur();
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector("[role=dialog]")) return;
      const key = e.key.toLowerCase();
      const map: Record<string, StepStatus> = { p: "passed", f: "failed", b: "blocked", s: "skipped" };
      if (!isText && editable && map[key] && !e.shiftKey) {
        e.preventDefault();
        setStatus(focus, map[key]);
      } else if (!isText && (key === "j" || e.key === "ArrowDown")) {
        e.preventDefault();
        const next = Math.min(focus + 1, steps.length - 1);
        setFocus(next);
        rows.current[next]?.focus();
      } else if (!isText && (key === "k" || e.key === "ArrowUp")) {
        e.preventDefault();
        const prev = Math.max(focus - 1, 0);
        setFocus(prev);
        rows.current[prev]?.focus();
      } else if (!isText && editable && key === "a") {
        e.preventDefault();
        rows.current[focus]?.querySelector<HTMLInputElement>("input[data-attach]")?.click();
      } else if (e.key === "?") {
        e.preventDefault();
        onHelp();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  });

  return (
    <div className="grid gap-4">
      {isText ? (
        <section aria-label="Test" className="rounded-card border border-border bg-surface p-4">
          <MarkdownView text={version.text_body} />
          {version.expected_result ? (
            <div className="mt-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">Expected</p>
              <MarkdownView text={version.expected_result} />
            </div>
          ) : null}
          <fieldset className="mt-4">
            <legend className="mb-1.5 text-[13px] font-medium text-ink">Result</legend>
            <div className="flex flex-wrap gap-1.5">
              {TEXT_OUTCOMES.map(([o, label]) => (
                <button
                  key={o}
                  type="button"
                  aria-pressed={textOutcome === o}
                  disabled={!editable}
                  onClick={() => {
                    setTextOutcome(o);
                  }}
                  className={cn(
                    "h-8 rounded-control border px-3 text-[12.5px] font-semibold",
                    textOutcome === o
                      ? "border-accent bg-accent-tint text-accent-ink"
                      : "border-border-control bg-surface text-ink-secondary hover:bg-surface-muted",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>
        </section>
      ) : (
        <ol aria-label="Steps" className="rounded-card border border-border bg-surface">
          {steps.map((s, i) => (
            <StepRow
              key={s.draft.step_id}
              ref={(el) => {
                rows.current[i] = el;
              }}
              step={
                s.version ?? { action: "—", expected_result: null, data: null, position: s.draft.position }
              }
              value={saver.values[s.draft.step_id] ?? { status: "not_run", actual_result: "", comment: "" }}
              saveState={saver.state[s.draft.step_id]}
              focused={focus === i}
              editable={editable}
              evidence={evidence[s.draft.step_id] ?? []}
              uploading={uploading === s.draft.step_id}
              onFocus={() => {
                setFocus(i);
              }}
              onStatus={(st) => {
                setStatus(i, st);
              }}
              onText={(field, v) => {
                saver.update(s.draft.step_id, { [field]: v }, false);
              }}
              onAttach={(f) => void attach(s.draft.step_id, s.draft.id, f)}
            />
          ))}
        </ol>
      )}

      <section aria-label="Finish" className="grid gap-3 rounded-card border border-border bg-surface p-4">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_200px]">
          <Field label={isText && textOutcome === "failed" ? "Comment (required)" : "Comment"}>
            {(p) => (
              <Textarea
                {...p}
                rows={2}
                readOnly={!editable}
                value={comment}
                onChange={(e) => {
                  setComment(e.target.value);
                  saveAttempt({ comment: e.target.value });
                }}
              />
            )}
          </Field>
          <Field label="Build">
            {(p) => (
              <Input
                {...p}
                readOnly={!editable}
                value={build}
                onChange={(e) => {
                  setBuild(e.target.value);
                  saveAttempt({ build: e.target.value });
                }}
              />
            )}
          </Field>
        </div>
        {editable ? (
          <div className="flex flex-wrap items-center gap-2">
            {!isText ? (
              <Button variant="secondary" size="sm" onClick={passAll} disabled={preview.notRecorded === 0}>
                Pass all remaining
              </Button>
            ) : null}
            {!isText
              ? RUN_OUTCOMES.map(([o, label]) => (
                  <Button
                    key={o}
                    variant="secondary"
                    size="sm"
                    disabled={
                      statuses.includes("failed") || (o !== "blocked" && statuses.includes("blocked"))
                    }
                    onClick={() => {
                      setAsk({ outcome: o, title: label.replace("…", "") });
                    }}
                  >
                    {label}
                  </Button>
                ))
              : null}
            <span className="flex-1" />
            {!isText ? (
              <span className="text-[13px] text-ink-secondary">
                Result preview{" "}
                <span
                  data-preview={preview.status ?? "incomplete"}
                  className="ml-1 rounded-full border border-border px-2.5 py-0.5 font-semibold text-ink"
                >
                  {preview.label}
                </span>
              </span>
            ) : null}
            <Button
              disabled={finishing || saver.unsaved || (!isText && preview.incomplete)}
              title={saver.unsaved ? "Waiting for steps to save" : undefined}
              onClick={requestFinish}
            >
              Finish run <Kbd onAccent>Ctrl ⏎</Kbd>
            </Button>
          </div>
        ) : null}
        {!isText ? (
          <p
            className={cn(
              "text-xs",
              preview.incomplete ? "text-[var(--status-blocked-fg)]" : "text-ink-secondary",
            )}
          >
            {saver.failing
              ? "Some steps are not saved yet; Finish is available once they are."
              : preview.hint}
          </p>
        ) : null}
      </section>

      <PromptDialog
        open={ask !== null}
        onOpenChange={(o) => {
          if (!o) setAsk(null);
        }}
        title={ask?.title ?? "Reason"}
        label="Reason"
        submitLabel="Finish run"
        multiline
        pending={finishing}
        onSubmit={(reason) => {
          void finish(ask?.outcome ?? null, reason);
        }}
      />
      <ConfirmDialog
        open={confirmPassAll}
        onOpenChange={setConfirmPassAll}
        title={`Pass all ${preview.notRecorded} remaining steps?`}
        description="Every step without a result is marked passed."
        confirmLabel="Pass all"
        onConfirm={() => void doPassAll()}
      />
    </div>
  );
}
