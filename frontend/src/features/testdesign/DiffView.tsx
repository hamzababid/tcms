import { Minus, Plus } from "lucide-react";
import { useState } from "react";

import { ErrorState, Skeleton } from "@/components/common/feedback";
import { Checkbox } from "@/components/ui/field";
import { cn } from "@/lib/utils";

import { useCompare, type CompareRead } from "./api";

const FIELD_LABELS: Record<string, string> = {
  format: "Format",
  title: "Title",
  description: "Description",
  preconditions: "Preconditions",
  test_data: "Test data",
  expected_result: "Overall expected result",
  postconditions: "Postconditions",
  text_body: "Procedure",
};

/** Word-level diff (LCS over tokens); small inputs only, which step and field texts are. */
export function wordDiff(a: string, b: string): { text: string; kind: "same" | "add" | "del" }[] {
  const x = a.split(/(\s+)/).filter((t) => t !== "");
  const y = b.split(/(\s+)/).filter((t) => t !== "");
  if (x.length * y.length > 250_000) {
    return [
      { text: a, kind: "del" },
      { text: b, kind: "add" },
    ];
  }
  const w = y.length + 1;
  const dp = new Int32Array((x.length + 1) * w);
  const at = (i: number, j: number) => dp[i * w + j] ?? 0;
  for (let i = x.length - 1; i >= 0; i--) {
    for (let j = y.length - 1; j >= 0; j--) {
      dp[i * w + j] = x[i] === y[j] ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1));
    }
  }
  const out: { text: string; kind: "same" | "add" | "del" }[] = [];
  const push = (text: string, kind: "same" | "add" | "del") => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ text, kind });
  };
  let i = 0;
  let j = 0;
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) {
      push(x[i] ?? "", "same");
      i++;
      j++;
    } else if (at(i + 1, j) >= at(i, j + 1)) push(x[i++] ?? "", "del");
    else push(y[j++] ?? "", "add");
  }
  while (i < x.length) push(x[i++] ?? "", "del");
  while (j < y.length) push(y[j++] ?? "", "add");
  return out;
}

function Inline({ before, after }: { before: string | null; after: string | null }) {
  return (
    <span className="whitespace-pre-wrap">
      {wordDiff(before ?? "", after ?? "").map((p, i) =>
        p.kind === "same" ? (
          <span key={i}>{p.text}</span>
        ) : p.kind === "add" ? (
          <ins key={i} className="bg-[var(--status-pass-bg)] text-[var(--status-pass-fg)] no-underline">
            {p.text}
          </ins>
        ) : (
          <del key={i} className="bg-[var(--status-fail-bg)] text-[var(--status-fail-fg)]">
            {p.text}
          </del>
        ),
      )}
    </span>
  );
}

/** DiffView (AC-TD-12): changed fields highlighted, steps aligned by position, unchanged collapsed. */
export function DiffView({ caseId, from, to }: { caseId: string; from: number; to: number }) {
  const diff = useCompare(caseId, from, to);
  if (diff.isPending) return <Skeleton rows={4} />;
  if (diff.isError) return <ErrorState error={diff.error} />;
  return <DiffBody diff={diff.data} />;
}

export function DiffBody({ diff }: { diff: CompareRead }) {
  const [showUnchanged, setShowUnchanged] = useState(false);
  const fields = diff.fields.filter((f) => showUnchanged || f.changed);
  const steps = diff.steps.filter((s) => showUnchanged || s.change !== "unchanged");
  const hiddenSteps = diff.steps.length - steps.length;
  return (
    <div
      className="flex flex-col gap-4 text-[13px]"
      aria-label={`Changes from v${diff.from_version} to v${diff.to_version}`}
    >
      <div className="flex items-center justify-between">
        <p className="font-medium text-ink">
          v{diff.from_version} → v{diff.to_version}
        </p>
        <Checkbox
          label="Show unchanged"
          checked={showUnchanged}
          onChange={(e) => {
            setShowUnchanged(e.target.checked);
          }}
        />
      </div>
      {fields.length === 0 && steps.length === 0 ? (
        <p className="text-ink-secondary">No differences.</p>
      ) : null}
      {fields.map((f) => (
        <div
          key={f.field}
          className={cn(
            "rounded-control border px-3 py-2",
            f.changed
              ? "border-[var(--status-blocked-border)] bg-[var(--status-blocked-bg)]"
              : "border-border",
          )}
        >
          <div className="mb-1 text-xs font-medium text-ink-secondary">
            {FIELD_LABELS[f.field] ?? f.field}
            {f.changed ? " · changed" : ""}
          </div>
          {f.changed ? (
            <Inline before={f.before} after={f.after} />
          ) : (
            <span className="whitespace-pre-wrap">{f.after ?? "—"}</span>
          )}
        </div>
      ))}
      {diff.steps.length ? (
        <div>
          <div className="mb-2 text-xs font-medium text-ink-secondary">Steps</div>
          <ol className="flex flex-col gap-1">
            {steps.map((s) => (
              <li
                key={s.position}
                data-change={s.change}
                className={cn(
                  "grid grid-cols-[48px_1fr_1fr] gap-3 rounded-control border px-3 py-2",
                  s.change === "added" && "border-[var(--status-pass-border)] bg-[var(--status-pass-bg)]",
                  s.change === "removed" &&
                    "border-[var(--status-fail-border)] bg-[var(--status-fail-bg)] line-through",
                  s.change === "changed" &&
                    "border-[var(--status-blocked-border)] bg-[var(--status-blocked-bg)]",
                  s.change === "unchanged" && "border-border",
                )}
              >
                <span className="flex items-start gap-1 font-mono text-xs text-ink-secondary">
                  {s.change === "added" ? <Plus aria-label="Added" className="size-3.5" /> : null}
                  {s.change === "removed" ? <Minus aria-label="Removed" className="size-3.5" /> : null}
                  {s.position}
                </span>
                {s.change === "changed" ? (
                  <>
                    <Inline before={s.before?.action ?? null} after={s.after?.action ?? null} />
                    <Inline
                      before={s.before?.expected_result ?? null}
                      after={s.after?.expected_result ?? null}
                    />
                  </>
                ) : (
                  <>
                    <span className="whitespace-pre-wrap">{(s.after ?? s.before)?.action}</span>
                    <span className="whitespace-pre-wrap text-ink-secondary">
                      {(s.after ?? s.before)?.expected_result ?? ""}
                    </span>
                  </>
                )}
              </li>
            ))}
          </ol>
          {!showUnchanged && hiddenSteps > 0 ? (
            <p className="mt-1 text-xs text-ink-muted">
              {hiddenSteps} unchanged {hiddenSteps === 1 ? "step" : "steps"} hidden
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
