import { Plus, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { useEnvironments, useMembers, useReleases, type Project } from "@/api/queries";
import { ConflictDialog } from "@/components/common/dialogs";
import { useToast } from "@/components/common/feedback";
import { MarkdownEditor } from "@/components/common/Markdown";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { FormError } from "@/features/auth/AuthCard";
import { useTags } from "@/features/testdesign/api";

import {
  useCreatePlan,
  usePatchPlan,
  type ExitRule,
  type PlanCreate,
  type PlanRead,
  type PlanType,
  type Risk,
} from "./api";
import { PLAN_TYPES, RISK_IMPACTS, RULE_TYPES, type RuleType } from "./labels";

interface Values {
  name: string;
  type: PlanType;
  release_id: string;
  owner_id: string;
  start_date: string;
  end_date: string;
  environment_ids: string[];
  objectives: string;
  scope_in: string;
  scope_out: string;
  entry_criteria: string;
  exit_rules: ExitRule[];
  exit_criteria_notes: string;
  risks: Risk[];
  acceptance_criteria: string;
  member_ids: string[];
}

function initialValues(plan: PlanRead | null): Values {
  return {
    name: plan?.name ?? "",
    type: plan?.type ?? "regression",
    release_id: plan?.release_id ?? "",
    owner_id: plan?.owner?.id ?? "",
    start_date: plan?.start_date ?? "",
    end_date: plan?.end_date ?? "",
    environment_ids: plan?.environment_ids ?? [],
    objectives: plan?.objectives ?? "",
    scope_in: plan?.scope_in ?? "",
    scope_out: plan?.scope_out ?? "",
    entry_criteria: plan?.entry_criteria ?? "",
    exit_rules: (plan?.exit_rules ?? []) as unknown as ExitRule[],
    exit_criteria_notes: plan?.exit_criteria_notes ?? "",
    risks: (plan?.risks ?? []) as unknown as Risk[],
    acceptance_criteria: plan?.acceptance_criteria ?? "",
    member_ids: plan?.member_ids ?? [],
  };
}

const orNull = (v: string) => (v.trim() === "" ? null : v);

function toBody(v: Values): PlanCreate {
  return {
    name: v.name.trim(),
    type: v.type,
    release_id: orNull(v.release_id),
    owner_id: orNull(v.owner_id),
    start_date: orNull(v.start_date),
    end_date: orNull(v.end_date),
    environment_ids: v.environment_ids,
    objectives: orNull(v.objectives),
    scope_in: orNull(v.scope_in),
    scope_out: orNull(v.scope_out),
    entry_criteria: orNull(v.entry_criteria),
    exit_rules: v.exit_rules,
    exit_criteria_notes: orNull(v.exit_criteria_notes),
    risks: v.risks.map((r) => ({ ...r, mitigation: r.mitigation?.trim() ? r.mitigation : null })),
    acceptance_criteria: orNull(v.acceptance_criteria),
    member_ids: v.member_ids,
  };
}

/** Client checks mirroring docs/02 §6.1; the server stays authoritative. */
function validate(v: Values): Record<string, string> {
  const e: Record<string, string> = {};
  const n = v.name.trim().length;
  if (n < 3 || n > 120) e.name = "Use 3 to 120 characters";
  if (v.start_date && v.end_date && v.end_date < v.start_date)
    e.end_date = "The end date is before the start";
  v.exit_rules.forEach((r, i) => {
    const kind = RULE_TYPES[r.type].kind;
    if (kind === "percent" && !(r.threshold >= 0 && r.threshold <= 1))
      e[`exit_rules[${i}]`] = "Give a percentage between 0 and 100";
    if (kind === "count" && !(Number.isInteger(r.threshold) && r.threshold >= 0))
      e[`exit_rules[${i}]`] = "Give a whole number of 0 or more";
    if (kind === "tag" && !r.params?.tag) e[`exit_rules[${i}]`] = "Choose a tag";
  });
  v.risks.forEach((r, i) => {
    if (!r.description.trim()) e[`risks[${i}]`] = "Describe the risk";
  });
  return e;
}

/** Server field pointers (`exit_rules[0].threshold`, `owner_id`) → the form's error keys. */
function fieldKey(field: string): string {
  const m = /^(exit_rules|risks)\[(\d+)\]/.exec(field);
  if (m) return `${m[1]}[${m[2]}]`;
  return field.split(/[.[]/)[0] ?? field;
}

function newRule(type: RuleType): ExitRule {
  if (type === "tag_fully_executed") return { type, threshold: 1, params: { tag: "" } };
  if (RULE_TYPES[type].kind === "count") return { type, threshold: 0 };
  return { type, threshold: 1 };
}

/** New / edit test plan (docs/07 §5.7; US-070, FR-PLN-001/005). */
export function PlanForm({
  project,
  plan,
  onClose,
  onSaved,
}: {
  project: Project;
  plan: PlanRead | null;
  onClose: () => void;
  onSaved: (plan: PlanRead) => void;
}) {
  const toast = useToast();
  const create = useCreatePlan(project.id);
  const patch = usePatchPlan(project.id, plan?.id ?? "");
  const environments = useEnvironments(project.id);
  const releases = useReleases(project.id);
  const members = useMembers(project.id);
  const tags = useTags(project.id);
  const [v, setV] = useState<Values>(() => initialValues(plan));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<unknown>(null);
  const pending = create.isPending || patch.isPending;

  const set = <K extends keyof Values>(k: K, value: Values[K]) => {
    setV((cur) => ({ ...cur, [k]: value }));
  };
  const setRule = (i: number, rule: ExitRule) => {
    set(
      "exit_rules",
      v.exit_rules.map((r, j) => (j === i ? rule : r)),
    );
  };
  const setRisk = (i: number, risk: Risk) => {
    set(
      "risks",
      v.risks.map((r, j) => (j === i ? risk : r)),
    );
  };

  const submit = async () => {
    setFormError(null);
    const local = validate(v);
    setErrors(local);
    if (Object.keys(local).length) return;
    try {
      const body = toBody(v);
      const saved = plan
        ? await patch.mutateAsync({ ...body, row_version: plan.row_version })
        : await create.mutateAsync(body);
      toast(plan ? "Plan saved" : `Plan ${saved.key} created`);
      onSaved(saved);
    } catch (e) {
      if (e instanceof ApiError && e.code === "stale_row_version") setConflict(e);
      else if (e instanceof ApiError && e.code === "name_taken")
        setErrors({ name: e.detail ?? "A plan with this name already exists" });
      else if (e instanceof ApiError && e.errors.length) {
        setErrors(Object.fromEntries(e.errors.map((fe) => [fieldKey(fe.field), fe.message])));
        setFormError(e.detail);
      } else setFormError(e instanceof ApiError ? (e.detail ?? e.code) : "Could not save the plan");
    }
  };

  const activeEnvs = (environments.data ?? []).filter((e) => !e.archived || v.environment_ids.includes(e.id));
  const memberOptions = (members.data ?? []).map((m) => ({ id: m.user.id, label: m.user.display_name }));

  return (
    <Dialog
      open
      wide
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={plan ? `Edit ${plan.key}` : "New test plan"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="plan-form" disabled={pending}>
            {plan ? "Save" : "Create"}
          </Button>
        </>
      }
    >
      <form
        id="plan-form"
        noValidate
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <FormError message={formError} />
        <Field label="Name" required error={errors.name}>
          {(p) => (
            <Input
              {...p}
              value={v.name}
              placeholder="e.g. SPARK v2.5 Regression"
              onChange={(e) => {
                set("name", e.target.value);
              }}
            />
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Type" required error={errors.type}>
            {(p) => (
              <Select
                {...p}
                value={v.type}
                onChange={(e) => {
                  set("type", e.target.value as PlanType);
                }}
              >
                {PLAN_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Release" error={errors.release_id}>
            {(p) => (
              <Select
                {...p}
                value={v.release_id}
                onChange={(e) => {
                  set("release_id", e.target.value);
                }}
              >
                <option value="">No release</option>
                {(releases.data ?? []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Owner" error={errors.owner_id}>
            {(p) => (
              <Select
                {...p}
                value={v.owner_id}
                onChange={(e) => {
                  set("owner_id", e.target.value);
                }}
              >
                <option value="">{plan ? "No owner" : "Me"}</option>
                {memberOptions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Start date" error={errors.start_date}>
            {(p) => (
              <Input
                {...p}
                type="date"
                value={v.start_date}
                onChange={(e) => {
                  set("start_date", e.target.value);
                }}
              />
            )}
          </Field>
          <Field label="End date" error={errors.end_date}>
            {(p) => (
              <Input
                {...p}
                type="date"
                value={v.end_date}
                onChange={(e) => {
                  set("end_date", e.target.value);
                }}
              />
            )}
          </Field>
        </div>
        <ChipPicker
          legend="Environments"
          options={activeEnvs.map((e) => ({ id: e.id, label: e.name }))}
          value={v.environment_ids}
          onChange={(ids) => {
            set("environment_ids", ids);
          }}
          error={errors.environment_ids}
          empty="No environments yet. Add them in project settings."
        />
        <MarkdownField
          label="Objectives"
          value={v.objectives}
          onChange={(x) => {
            set("objectives", x);
          }}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <MarkdownField
            label="In scope"
            value={v.scope_in}
            onChange={(x) => {
              set("scope_in", x);
            }}
          />
          <MarkdownField
            label="Out of scope"
            value={v.scope_out}
            onChange={(x) => {
              set("scope_out", x);
            }}
          />
        </div>
        <MarkdownField
          label="Entry criteria"
          value={v.entry_criteria}
          onChange={(x) => {
            set("entry_criteria", x);
          }}
        />

        <Section
          title="Exit criteria"
          hint="Rules are checked against the release's results (readiness, M7)."
          action={
            <Select
              aria-label="Add exit rule"
              className="h-8 w-auto text-[13px]"
              value=""
              disabled={v.exit_rules.length >= 20}
              onChange={(e) => {
                if (e.target.value) set("exit_rules", [...v.exit_rules, newRule(e.target.value as RuleType)]);
              }}
            >
              <option value="">+ Rule</option>
              {(Object.entries(RULE_TYPES) as [RuleType, (typeof RULE_TYPES)[RuleType]][]).map(([t, s]) => (
                <option key={t} value={t}>
                  {s.label.replace(" ≥", "").replace(" ≤", "")}
                </option>
              ))}
            </Select>
          }
        >
          {v.exit_rules.length === 0 ? (
            <p className="text-[13px] text-ink-muted">No rules yet.</p>
          ) : (
            <ul className="grid gap-2">
              {v.exit_rules.map((r, i) => (
                <RuleRow
                  key={i}
                  index={i}
                  rule={r}
                  tags={(tags.data ?? []).map((t) => t.name)}
                  error={errors[`exit_rules[${i}]`] ?? errors.exit_rules}
                  onChange={(rule) => {
                    setRule(i, rule);
                  }}
                  onRemove={() => {
                    set(
                      "exit_rules",
                      v.exit_rules.filter((_, j) => j !== i),
                    );
                  }}
                />
              ))}
            </ul>
          )}
          <div className="mt-3">
            <MarkdownField
              label="Exit criteria notes"
              value={v.exit_criteria_notes}
              onChange={(x) => {
                set("exit_criteria_notes", x);
              }}
            />
          </div>
        </Section>

        <Section
          title="Risks"
          action={
            <Button
              variant="secondary"
              size="sm"
              disabled={v.risks.length >= 50}
              onClick={() => {
                set("risks", [...v.risks, { description: "", impact: "medium", mitigation: "" }]);
              }}
            >
              <Plus aria-hidden="true" className="size-4" />
              Risk
            </Button>
          }
        >
          {v.risks.length === 0 ? (
            <p className="text-[13px] text-ink-muted">No risks recorded.</p>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-xs text-ink-secondary">
                  <th className="pb-1.5 font-medium">Description</th>
                  <th className="w-32 pb-1.5 font-medium">Impact</th>
                  <th className="pb-1.5 font-medium">Mitigation</th>
                  <th className="w-10">
                    <span className="sr-only">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {v.risks.map((r, i) => (
                  <tr key={i} className="align-top">
                    <td className="pb-2 pr-2">
                      <Input
                        aria-label={`Risk ${i + 1} description`}
                        aria-invalid={Boolean(errors[`risks[${i}]`])}
                        value={r.description}
                        onChange={(e) => {
                          setRisk(i, { ...r, description: e.target.value });
                        }}
                      />
                      {errors[`risks[${i}]`] ? (
                        <p className="mt-1 text-xs text-danger">{errors[`risks[${i}]`]}</p>
                      ) : null}
                    </td>
                    <td className="pb-2 pr-2">
                      <Select
                        aria-label={`Risk ${i + 1} impact`}
                        value={r.impact}
                        onChange={(e) => {
                          setRisk(i, { ...r, impact: e.target.value });
                        }}
                      >
                        {Object.entries(RISK_IMPACTS).map(([k, l]) => (
                          <option key={k} value={k}>
                            {l}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="pb-2 pr-2">
                      <Input
                        aria-label={`Risk ${i + 1} mitigation`}
                        value={r.mitigation ?? ""}
                        onChange={(e) => {
                          setRisk(i, { ...r, mitigation: e.target.value });
                        }}
                      />
                    </td>
                    <td className="pb-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Remove risk ${i + 1}`}
                        onClick={() => {
                          set(
                            "risks",
                            v.risks.filter((_, j) => j !== i),
                          );
                        }}
                      >
                        <Trash2 aria-hidden="true" className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {errors.risks ? <p className="mt-1 text-xs text-danger">{errors.risks}</p> : null}
        </Section>

        <MarkdownField
          label="Acceptance criteria"
          value={v.acceptance_criteria}
          onChange={(x) => {
            set("acceptance_criteria", x);
          }}
        />
        <ChipPicker
          legend="QA members"
          options={memberOptions}
          value={v.member_ids}
          onChange={(ids) => {
            set("member_ids", ids);
          }}
          error={errors.member_ids}
          empty="No project members."
        />
      </form>
      <ConflictDialog
        error={conflict}
        onClose={() => {
          setConflict(null);
        }}
        onReload={() => {
          setConflict(null);
          onClose();
        }}
      />
    </Dialog>
  );
}

function Section({
  title,
  hint,
  action,
  children,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <fieldset className="rounded-card border border-border p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <legend className="text-[13px] font-semibold text-ink">{title}</legend>
          {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </fieldset>
  );
}

function MarkdownField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label} hint="Markdown">
      {(p) => (
        <MarkdownEditor
          {...p}
          rows={3}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
          }}
        />
      )}
    </Field>
  );
}

function RuleRow({
  index,
  rule,
  tags,
  error,
  onChange,
  onRemove,
}: {
  index: number;
  rule: ExitRule;
  tags: string[];
  error: string | undefined;
  onChange: (r: ExitRule) => void;
  onRemove: () => void;
}) {
  const spec = RULE_TYPES[rule.type];
  const n = index + 1;
  return (
    <li className="rounded-control border border-border bg-ground px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <span className="font-medium text-ink">{spec.kind === "tag" ? "Every case tagged" : spec.label}</span>
        {spec.kind === "percent" ? (
          <span className="inline-flex items-center gap-1">
            <Input
              aria-label={`Rule ${n} threshold (%)`}
              type="number"
              min={0}
              max={100}
              className="h-8 w-20"
              value={Math.round(rule.threshold * 100)}
              onChange={(e) => {
                onChange({ ...rule, threshold: Number(e.target.value) / 100 });
              }}
            />
            %
          </span>
        ) : spec.kind === "count" ? (
          <Input
            aria-label={`Rule ${n} threshold`}
            type="number"
            min={0}
            step={1}
            className="h-8 w-20"
            value={rule.threshold}
            onChange={(e) => {
              onChange({ ...rule, threshold: Number(e.target.value) });
            }}
          />
        ) : (
          <>
            <Select
              aria-label={`Rule ${n} tag`}
              className="h-8 w-48"
              value={rule.params?.tag ?? ""}
              onChange={(e) => {
                onChange({ ...rule, params: { tag: e.target.value } });
              }}
            >
              <option value="">Choose a tag…</option>
              {tags.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
            <span className="text-ink">executed</span>
          </>
        )}
        <span className="flex-1" />
        <Button variant="ghost" size="icon" aria-label={`Remove rule ${n}`} onClick={onRemove}>
          <Trash2 aria-hidden="true" className="size-4" />
        </Button>
      </div>
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </li>
  );
}

/** Multi-select as toggle chips (environments, QA members). */
export function ChipPicker({
  legend,
  options,
  value,
  onChange,
  error,
  empty,
}: {
  legend: string;
  options: { id: string; label: string }[];
  value: string[];
  onChange: (ids: string[]) => void;
  error?: string | undefined;
  empty: string;
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-[13px] font-medium text-ink">{legend}</legend>
      {options.length === 0 ? (
        <p className="text-[13px] text-ink-muted">{empty}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {options.map((o) => (
            <label
              key={o.id}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs has-[:checked]:border-accent-border has-[:checked]:bg-accent-tint has-[:checked]:text-accent-ink"
            >
              <input
                type="checkbox"
                checked={value.includes(o.id)}
                onChange={(e) => {
                  onChange(e.target.checked ? [...value, o.id] : value.filter((x) => x !== o.id));
                }}
              />
              {o.label}
            </label>
          ))}
        </div>
      )}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </fieldset>
  );
}
