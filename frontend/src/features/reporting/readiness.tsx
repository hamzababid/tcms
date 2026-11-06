/** Readiness rules, ready badge, decision dialog and timeline (docs/07 §5.15, docs/02 §11.4; M7 D1–D3). */
import { CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";

import { errorMessage, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/field";
import { ruleText } from "@/features/planning/labels";
import { formatCount, formatDateTime, formatRate } from "@/lib/format";

import {
  DECISION_LABEL,
  recordDecision,
  useInvalidateReporting,
  type Decision,
  type DecisionKind,
  type RuleResult,
} from "./api";

/** Ready / Not ready, never colour alone. */
export function ReadyBadge({
  ready,
  size = "md",
}: {
  ready: boolean | null | undefined;
  size?: "md" | "lg";
}) {
  if (ready === null || ready === undefined) return <span className="text-ink-muted">—</span>;
  const Icon = ready ? CheckCircle2 : XCircle;
  return (
    <span
      data-ready={ready}
      className={`inline-flex items-center gap-1.5 font-semibold ${size === "lg" ? "text-base" : "text-[13px]"}`}
      style={{ color: ready ? "var(--status-pass-fg)" : "var(--status-fail-fg)" }}
    >
      <Icon aria-hidden="true" className={size === "lg" ? "size-5" : "size-4"} />
      {ready ? "Ready" : "Not ready"}
    </span>
  );
}

function threshold(r: RuleResult): string {
  return ruleText({ type: r.type as never, threshold: r.threshold, params: r.params });
}

function actual(r: RuleResult): string {
  if (r.count !== null) return formatCount(r.count);
  if (r.actual) return formatRate(r.actual);
  return "—";
}

/** The rule table: rule, actual value with counts, met (docs/07 §5.15). */
export function ReadinessRules({ rules, showPlan = true }: { rules: RuleResult[]; showPlan?: boolean }) {
  if (rules.length === 0)
    return <p className="text-[13px] text-ink-secondary">No exit rules. Add them on the plan's Overview.</p>;
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface">
      <table aria-label="Readiness rules" className="w-full text-left text-[13px]">
        <thead className="bg-ground text-xs text-ink-secondary">
          <tr>
            {showPlan ? <th className="px-3 py-2 font-medium">From</th> : null}
            <th className="px-3 py-2 font-medium">Rule</th>
            <th className="px-3 py-2 font-medium">Actual</th>
            <th className="w-28 px-3 py-2 font-medium">Met</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r, i) => (
            <tr key={i} className="h-10 border-t border-border" data-met={r.met}>
              {showPlan ? (
                <td className="px-3 text-ink-secondary">
                  {r.plan ? (
                    <>
                      <span className="font-mono text-xs">{r.plan.key}</span> {r.plan.name}
                    </>
                  ) : (
                    "Default rule"
                  )}
                </td>
              ) : null}
              <td className="px-3">{threshold(r)}</td>
              <td className="tabular px-3">
                {actual(r)}
                {r.note ? <span className="ml-2 text-xs text-ink-muted">{r.note}</span> : null}
              </td>
              <td className="px-3">
                <span
                  className="inline-flex items-center gap-1 text-xs font-medium"
                  style={{ color: r.met ? "var(--status-pass-fg)" : "var(--status-fail-fg)" }}
                >
                  {r.met ? (
                    <CheckCircle2 aria-hidden="true" className="size-3.5" />
                  ) : (
                    <XCircle aria-hidden="true" className="size-3.5" />
                  )}
                  {r.met ? "Met" : "Not met"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const KINDS: DecisionKind[] = ["go", "go_with_risks", "no_go"];

export function DecisionDialog({
  releaseId,
  releaseName,
  ready,
  open,
  onClose,
}: {
  releaseId: string;
  releaseName: string;
  ready: boolean;
  open: boolean;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<DecisionKind>(ready ? "go" : "no_go");
  const [comment, setComment] = useState("");
  const [risks, setRisks] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const invalidate = useInvalidateReporting();
  const submit = async () => {
    const e: Record<string, string> = {};
    if (!comment.trim()) e.comment = "Add a comment";
    if (kind === "go_with_risks" && !risks.trim()) e.risks = "Describe the risks you accept";
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    try {
      await recordDecision(releaseId, { decision: kind, comment, risks: risks.trim() || null });
      toast(`${DECISION_LABEL[kind]} recorded for ${releaseName}`);
      invalidate();
      setComment("");
      setRisks("");
      onClose();
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={`Record decision · ${releaseName}`}
      description="The decision is stored with a snapshot of every rule and metric. It cannot be changed later; record a new decision instead."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy} onClick={() => void submit()}>
            Record decision
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-medium text-ink">Decision</legend>
          {KINDS.map((k) => (
            <label key={k} className="flex items-center gap-2 text-[13px]">
              <input
                type="radio"
                name="decision"
                value={k}
                checked={kind === k}
                onChange={() => {
                  setKind(k);
                }}
              />
              {DECISION_LABEL[k]}
            </label>
          ))}
        </fieldset>
        <Field label="Comment" required error={errors.comment}>
          {(p) => (
            <Textarea
              {...p}
              rows={3}
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
              }}
            />
          )}
        </Field>
        {kind === "go_with_risks" ? (
          <Field label="Risks accepted" required error={errors.risks}>
            {(p) => (
              <Textarea
                {...p}
                rows={3}
                value={risks}
                onChange={(e) => {
                  setRisks(e.target.value);
                }}
              />
            )}
          </Field>
        ) : null}
      </div>
    </Dialog>
  );
}

/** Decisions, newest first, each with its frozen snapshot (docs/07 §5.15 "timeline with snapshot viewer"). */
export function DecisionTimeline({ decisions }: { decisions: Decision[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (decisions.length === 0)
    return <p className="text-[13px] text-ink-secondary">No decision recorded yet.</p>;
  return (
    <ol aria-label="Decisions" className="flex flex-col gap-3">
      {decisions.map((d) => {
        const snap = d.snapshot as {
          rules?: RuleResult[];
          summary?: { executed: number; applicable: number };
        };
        return (
          <li key={d.id} className="rounded-card border border-border bg-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <span className="text-[14px] font-semibold text-ink">{DECISION_LABEL[d.decision]}</span>
                <span className="text-xs text-ink-secondary">
                  {d.decided_by?.display_name ?? "—"} · {formatDateTime(d.decided_at)}
                </span>
              </div>
              <span className="text-xs text-ink-secondary">
                Readiness then: <ReadyBadge ready={d.ready} />
              </span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-[13px] text-ink">{d.comment}</p>
            {d.risks ? (
              <p className="mt-2 whitespace-pre-wrap text-[13px] text-ink">
                <span className="font-medium">Risks: </span>
                {d.risks}
              </p>
            ) : null}
            <Button
              variant="link"
              size="xs"
              className="mt-2"
              aria-expanded={open === d.id}
              onClick={() => {
                setOpen(open === d.id ? null : d.id);
              }}
            >
              {open === d.id ? "Hide snapshot" : "Show snapshot"}
            </Button>
            {open === d.id ? (
              <div className="mt-2">
                <ReadinessRules rules={snap.rules ?? []} />
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
