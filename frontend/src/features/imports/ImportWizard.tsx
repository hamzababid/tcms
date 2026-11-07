/**
 * Import wizard (docs/07 §5.16, docs/02 §15; US-150/151/153; AC-IMP-01): 1 Upload → 2 Map columns →
 * 3 Validate (dry run) → 4 Import. Nothing is written before step 4, and step 4 imports the whole file or
 * nothing.
 */
import { Link } from "@tanstack/react-router";
import { CheckCircle2, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { Project } from "@/api/queries";
import { Card, ErrorState, errorMessage, Page, Skeleton, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/field";
import { useInvalidateRequirements } from "@/features/requirements/api";
import { useFolders, useInvalidateCase } from "@/features/testdesign/api";
import { formatCount } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  commitImport,
  saveTemplate,
  uploadImport,
  useImportTransfer,
  useInvalidateTemplates,
  useTemplates,
  validateImport,
  type Entity,
  type ImportOptions,
  type Uploaded,
} from "./api";

const STEPS = ["Upload", "Map", "Validate", "Import"] as const;
const ENTITY_LABEL: Record<Entity, string> = {
  test_case: "test cases",
  requirement: "requirement references",
};

interface MappingState {
  sheet: string;
  columns: Record<string, string>;
  valueMaps: Record<string, Record<string, string>>;
  options: ImportOptions;
}

export function ImportWizard({
  project,
  entity: initialEntity,
  canImportCases,
  canImportRequirements,
}: {
  project: Project;
  entity: Entity;
  canImportCases: boolean;
  canImportRequirements: boolean;
}) {
  const [entity, setEntity] = useState<Entity>(initialEntity);
  const [uploaded, setUploaded] = useState<Uploaded | null>(null);
  const [state, setState] = useState<MappingState | null>(null);
  const [step, setStep] = useState(0);
  const transfer = useImportTransfer(step >= 2 && uploaded ? uploaded.transfer_id : null);
  const allowed = entity === "test_case" ? canImportCases : canImportRequirements;

  const restart = () => {
    setUploaded(null);
    setState(null);
    setStep(0);
  };

  return (
    <Page
      title={`Import ${ENTITY_LABEL[entity]}`}
      subtitle="CSV or Excel up to 20 MB. Nothing changes until the last step, and the last step imports the whole file or nothing."
      width="6xl"
    >
      <ol aria-label="Import steps" className="mb-6 flex flex-wrap gap-2 text-[13px]">
        {STEPS.map((label, i) => (
          <li
            key={label}
            aria-current={i === step ? "step" : undefined}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1",
              i === step
                ? "border-accent bg-accent-tint font-semibold text-accent-ink"
                : "border-border text-ink-secondary",
            )}
          >
            {i < step ? (
              <CheckCircle2 aria-hidden="true" className="size-3.5" />
            ) : (
              <span className="tabular">{i + 1}</span>
            )}
            {label}
          </li>
        ))}
      </ol>
      {!allowed ? (
        <ErrorState error={new Error(`You cannot import ${ENTITY_LABEL[entity]} in this project.`)} />
      ) : step === 0 || !uploaded || !state ? (
        <UploadStep
          project={project}
          entity={entity}
          onEntity={setEntity}
          canPick={canImportCases && canImportRequirements}
          onUploaded={(u) => {
            const sheet = u.sheets[0];
            if (!sheet) return;
            setUploaded(u);
            setState({
              sheet: sheet.name,
              columns: sheet.suggested_mapping,
              valueMaps: {},
              options: defaultOptions(),
            });
            setStep(1);
          }}
        />
      ) : step === 1 ? (
        <MapStep
          project={project}
          uploaded={uploaded}
          state={state}
          onChange={setState}
          onBack={restart}
          onValidate={async () => {
            await validateImport(uploaded.transfer_id, {
              sheet: state.sheet,
              mapping: state.columns,
              value_maps: state.valueMaps,
              options: state.options,
            });
            setStep(2);
          }}
        />
      ) : (
        <ResultStep
          project={project}
          entity={entity}
          transfer={transfer.data}
          loading={transfer.isPending}
          state={state}
          step={step}
          onBack={() => {
            setStep(1);
          }}
          onSkipErrors={async (skip) => {
            const next = { ...state, options: { ...state.options, skip_error_rows: skip } };
            setState(next);
            await validateImport(uploaded.transfer_id, {
              sheet: next.sheet,
              mapping: next.columns,
              value_maps: next.valueMaps,
              options: next.options,
            });
            void transfer.refetch();
          }}
          onCommit={async () => {
            await commitImport(uploaded.transfer_id);
            setStep(3);
            void transfer.refetch();
          }}
          onRestart={restart}
        />
      )}
    </Page>
  );
}

function defaultOptions(): ImportOptions {
  return { mode: "upsert", target_folder_id: null, steps_layout: "row_per_step", skip_error_rows: false };
}

function UploadStep({
  project,
  entity,
  onEntity,
  canPick,
  onUploaded,
}: {
  project: Project;
  entity: Entity;
  onEntity: (e: Entity) => void;
  canPick: boolean;
  onUploaded: (u: Uploaded) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onUploaded(await uploadImport(project.id, entity, file));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="1 · Upload a file">
      <div className="flex flex-col gap-4">
        {canPick ? (
          <fieldset className="flex gap-4 text-[13px]">
            <legend className="mb-1 font-medium text-ink">What does the file contain?</legend>
            {(["test_case", "requirement"] as const).map((e) => (
              <label key={e} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="entity"
                  checked={entity === e}
                  onChange={() => {
                    onEntity(e);
                  }}
                />
                {e === "test_case"
                  ? "Test cases (one row per step)"
                  : "Requirement references (reference, title, link, case keys)"}
              </label>
            ))}
          </fieldset>
        ) : null}
        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-card border border-dashed border-border-control bg-ground px-6 py-10 text-center text-[13px] text-ink-secondary hover:border-accent">
          <Upload aria-hidden="true" className="size-6 text-ink-muted" />
          <span className="font-medium text-ink">
            {busy ? "Reading the file…" : "Choose a .csv or .xlsx file"}
          </span>
          <span>Up to 20 MB, 5,000 {entity === "test_case" ? "cases" : "references"} and 50,000 rows</span>
          <input
            type="file"
            aria-label="File to import"
            accept=".csv,.xlsx"
            className="sr-only"
            disabled={busy}
            onChange={(e) => void upload(e.target.files?.[0])}
          />
        </label>
        {error ? <ErrorState error={error} /> : null}
        {entity === "test_case" ? (
          <p className="text-xs text-ink-secondary">
            Tip: an export from the repository re-imports as updates; edit it and import it back.
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function MapStep({
  project,
  uploaded,
  state,
  onChange,
  onBack,
  onValidate,
}: {
  project: Project;
  uploaded: Uploaded;
  state: MappingState;
  onChange: (s: MappingState) => void;
  onBack: () => void;
  onValidate: () => Promise<void>;
}) {
  const sheet = uploaded.sheets.find((s) => s.name === state.sheet) ?? uploaded.sheets[0];
  const folders = useFolders(project.id, false);
  const templates = useTemplates(project.id, uploaded.entity);
  const invalidateTemplates = useInvalidateTemplates();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const fieldByKey = useMemo(() => new Map(uploaded.fields.map((f) => [f.key, f])), [uploaded.fields]);
  if (!sheet) return null;
  const used = new Map<string, string>();
  for (const [col, f] of Object.entries(state.columns)) if (f) used.set(f, col);
  const isCases = uploaded.entity === "test_case";
  const setColumn = (col: string, f: string) => {
    onChange({ ...state, columns: { ...state.columns, [col]: f } });
  };
  const setValue = (field: string, value: string, mapped: string) => {
    onChange({
      ...state,
      valueMaps: { ...state.valueMaps, [field]: { ...(state.valueMaps[field] ?? {}), [value]: mapped } },
    });
  };
  const setOption = (patch: Partial<ImportOptions>) => {
    onChange({ ...state, options: { ...state.options, ...patch } });
  };
  const enumColumns = Object.entries(state.columns).filter(
    ([col, f]) => f && (fieldByKey.get(f)?.choices.length ?? 0) > 0 && sheet.values[col],
  );
  return (
    <div className="grid gap-5">
      <Card
        title="2 · Map columns"
        description={`${uploaded.file_name} · ${formatCount(sheet.rows)} rows`}
        actions={
          (templates.data?.length ?? 0) > 0 ? (
            <Select
              aria-label="Use a saved mapping"
              className="w-56"
              value=""
              onChange={(e) => {
                const t = templates.data?.find((x) => x.id === e.target.value);
                if (!t) return;
                const m = t.mapping as {
                  columns?: Record<string, string>;
                  value_maps?: Record<string, Record<string, string>>;
                  options?: Partial<ImportOptions>;
                };
                const columns = { ...state.columns };
                for (const col of sheet.columns)
                  if (m.columns && col in m.columns) columns[col] = m.columns[col] ?? "";
                onChange({
                  ...state,
                  columns,
                  valueMaps: m.value_maps ?? {},
                  options: { ...state.options, ...(m.options ?? {}) },
                });
              }}
            >
              <option value="">Use a saved mapping…</option>
              {templates.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          ) : null
        }
        flush
      >
        <div className="flex flex-wrap items-center gap-4 border-b border-border px-5 py-3 text-[13px]">
          {uploaded.sheets.length > 1 ? (
            <label className="flex items-center gap-2">
              <span className="text-ink-secondary">Sheet</span>
              <Select
                aria-label="Sheet"
                value={state.sheet}
                onChange={(e) => {
                  const next = uploaded.sheets.find((s) => s.name === e.target.value);
                  if (next) onChange({ ...state, sheet: next.name, columns: next.suggested_mapping });
                }}
              >
                {uploaded.sheets.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name} ({formatCount(s.rows)} rows)
                  </option>
                ))}
              </Select>
            </label>
          ) : null}
          {isCases ? (
            <>
              <fieldset className="flex items-center gap-3">
                <legend className="sr-only">Steps layout</legend>
                <span className="text-ink-secondary">Steps</span>
                {(["row_per_step", "single_cell"] as const).map((v) => (
                  <label key={v} className="flex items-center gap-1.5">
                    <input
                      type="radio"
                      name="steps_layout"
                      checked={state.options.steps_layout === v}
                      onChange={() => {
                        setOption({ steps_layout: v });
                      }}
                    />
                    {v === "row_per_step" ? "One row per step" : "All steps in one cell (1., 2., …)"}
                  </label>
                ))}
              </fieldset>
              <span className="flex items-center gap-2">
                <span className="text-ink-secondary">Cases with a known Key</span>
                <Select
                  aria-label="Cases with a known Key"
                  value={state.options.mode}
                  onChange={(e) => {
                    setOption({ mode: e.target.value as ImportOptions["mode"] });
                  }}
                >
                  <option value="upsert">are updated</option>
                  <option value="create_only">are errors (create only)</option>
                </Select>
              </span>
              <label className="flex items-center gap-2">
                <span className="text-ink-secondary">Rows without a folder go to</span>
                <Select
                  aria-label="Target folder"
                  className="w-56"
                  value={state.options.target_folder_id ?? ""}
                  onChange={(e) => {
                    setOption({ target_folder_id: e.target.value || null });
                  }}
                >
                  <option value="">— (Folder column required)</option>
                  {(folders.data ?? []).map((f) => (
                    <option key={f.id} value={f.id}>
                      {"· ".repeat(f.depth - 1)}
                      {f.name}
                    </option>
                  ))}
                </Select>
              </label>
            </>
          ) : null}
        </div>
        <table aria-label="Column mapping" className="w-full text-left text-[13px]">
          <thead className="bg-ground text-xs text-ink-secondary">
            <tr>
              <th className="px-5 py-2 font-medium">File column</th>
              <th className="px-3 py-2 font-medium">Sample</th>
              <th className="w-64 px-3 py-2 font-medium">Maps to</th>
            </tr>
          </thead>
          <tbody>
            {sheet.columns.map((col, i) => {
              const current = state.columns[col] ?? "";
              return (
                <tr key={col} className="h-10 border-t border-border">
                  <td className="px-5 font-medium">{col}</td>
                  <td className="max-w-xs truncate px-3 text-ink-secondary">
                    {sheet.sample.map((r) => r[i]).find((v) => v) ?? "—"}
                  </td>
                  <td className="px-3">
                    <Select
                      aria-label={`Field for column ${col}`}
                      className="w-full"
                      value={current}
                      onChange={(e) => {
                        setColumn(col, e.target.value);
                      }}
                    >
                      <option value="">Ignore</option>
                      {uploaded.fields.map((f) => (
                        <option
                          key={f.key}
                          value={f.key}
                          disabled={used.has(f.key) && used.get(f.key) !== col}
                        >
                          {f.label}
                        </option>
                      ))}
                    </Select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      {enumColumns.length ? (
        <Card title="Values" description="Values the file uses for list fields; choose what each one means.">
          <div className="grid gap-4 md:grid-cols-2">
            {enumColumns.map(([col, f]) => {
              const spec = fieldByKey.get(f);
              if (!spec) return null;
              return (
                <fieldset key={col} className="flex flex-col gap-1.5 text-[13px]">
                  <legend className="mb-1 font-medium">
                    {col} → {spec.label}
                  </legend>
                  {(sheet.values[col] ?? []).map((v) => (
                    <label key={v} className="flex items-center justify-between gap-3">
                      <span className="truncate">{v}</span>
                      <Select
                        aria-label={`${spec.label} for ${v}`}
                        className="w-48"
                        value={state.valueMaps[f]?.[v] ?? ""}
                        onChange={(e) => {
                          setValue(f, v, e.target.value);
                        }}
                      >
                        <option value="">Automatic</option>
                        {spec.choices.map((c) => (
                          <option key={c} value={c}>
                            {c.replaceAll("_", " ")}
                          </option>
                        ))}
                      </Select>
                    </label>
                  ))}
                </fieldset>
              );
            })}
          </div>
        </Card>
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-end gap-2">
          <Field label="Save this mapping as">
            {(p) => (
              <Input
                {...p}
                className="w-56"
                placeholder="e.g. TestRail export"
                value={templateName}
                onChange={(e) => {
                  setTemplateName(e.target.value);
                }}
              />
            )}
          </Field>
          <Button
            variant="secondary"
            disabled={!templateName.trim()}
            onClick={() => {
              saveTemplate(project.id, uploaded.entity, templateName.trim(), {
                columns: state.columns,
                value_maps: state.valueMaps,
                options: { steps_layout: state.options.steps_layout, mode: state.options.mode },
              })
                .then(() => {
                  invalidateTemplates();
                  toast(`Mapping "${templateName.trim()}" saved`);
                  setTemplateName("");
                })
                .catch((err: unknown) => {
                  toast(errorMessage(err), "error");
                });
            }}
          >
            Save mapping
          </Button>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onBack}>
            Choose another file
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              setBusy(true);
              onValidate()
                .catch((err: unknown) => {
                  toast(errorMessage(err), "error");
                })
                .finally(() => {
                  setBusy(false);
                });
            }}
          >
            Validate →
          </Button>
        </div>
      </div>
    </div>
  );
}

function ResultStep({
  project,
  entity,
  transfer,
  loading,
  state,
  step,
  onBack,
  onSkipErrors,
  onCommit,
  onRestart,
}: {
  project: Project;
  entity: Entity;
  transfer: ReturnType<typeof useImportTransfer>["data"];
  loading: boolean;
  state: MappingState;
  step: number;
  onBack: () => void;
  onSkipErrors: (skip: boolean) => Promise<void>;
  onCommit: () => Promise<void>;
  onRestart: () => void;
}) {
  const toast = useToast();
  const invalidateCase = useInvalidateCase();
  const invalidateRequirements = useInvalidateRequirements();
  const committed = transfer?.status === "committed";
  // The import wrote folders, cases and links behind the cache's back: refresh what the user opens next.
  useEffect(() => {
    if (!committed) return;
    invalidateCase(project.id);
    invalidateRequirements();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when the import lands
  }, [committed, project.id]);
  if (loading || !transfer) return <Skeleton rows={5} />;
  const summary = transfer.summary as {
    counts?: Record<string, number>;
    committable?: boolean;
    warnings?: { row: number; column: string | null; message: string }[];
    folders_to_create?: string[];
    result?: Record<string, number>;
  };
  const errors = transfer.errors as { row: number; column: string | null; code: string; message: string }[];
  if (transfer.status === "validating" || transfer.status === "committing")
    return (
      <Card title={transfer.status === "validating" ? "3 · Checking the file…" : "4 · Importing…"}>
        <p role="status" className="text-[13px] text-ink-secondary">
          {transfer.status === "validating"
            ? "Every row is checked; nothing is saved yet."
            : "The whole file is imported in one go. You can leave this page; the bell tells you when it is done."}
        </p>
      </Card>
    );
  if (transfer.status === "committed") {
    const r = summary.result ?? {};
    return (
      <Card title="4 · Imported">
        <div role="status" className="flex flex-col gap-3 text-[13px]">
          <p className="text-[15px] font-semibold text-ink">
            {Object.entries(r)
              .filter(([, n]) => n)
              .map(([k, n]) => `${formatCount(n)} ${k.replaceAll("_", " ")}`)
              .join(" · ") || "Nothing changed"}
          </p>
          <div className="flex gap-3">
            {transfer.download_url ? (
              <a className="font-medium text-accent-ink hover:underline" href={transfer.download_url}>
                Download the import report
              </a>
            ) : null}
            <Link
              to={entity === "test_case" ? "/p/$projectKey/repository" : "/p/$projectKey/requirements"}
              params={{ projectKey: project.key }}
              className="font-medium text-accent-ink hover:underline"
            >
              Open {entity === "test_case" ? "the repository" : "Requirements"}
            </Link>
            <Button variant="link" size="xs" onClick={onRestart}>
              Import another file
            </Button>
          </div>
        </div>
      </Card>
    );
  }
  const counts = summary.counts ?? {};
  const failed = transfer.status === "failed";
  return (
    <div className="grid gap-5">
      <Card title={failed ? "Import failed" : "3 · Validation"} tone={failed ? "danger" : "default"}>
        <div className="flex flex-col gap-3 text-[13px]">
          {failed ? null : (
            <p aria-label="Validation counts" className="text-ink">
              Create <strong>{formatCount(counts.create ?? 0)}</strong> · Update{" "}
              <strong>{formatCount(counts.update ?? 0)}</strong> · Unchanged{" "}
              <strong>{formatCount(counts.unchanged ?? 0)}</strong> · Errors{" "}
              <strong className={(counts.error ?? 0) > 0 ? "text-danger" : ""}>
                {formatCount(counts.error ?? 0)}
              </strong>
              {counts.folders_to_create ? ` · New folders ${formatCount(counts.folders_to_create)}` : ""}
              {counts.links_to_add ? ` · Links to add ${formatCount(counts.links_to_add)}` : ""}
            </p>
          )}
          {(summary.folders_to_create?.length ?? 0) > 0 ? (
            <p className="text-xs text-ink-secondary">
              New folders: {summary.folders_to_create?.slice(0, 8).join(", ")}
            </p>
          ) : null}
          {!failed ? (
            <Checkbox
              label="Skip rows with errors"
              checked={state.options.skip_error_rows}
              onChange={(e) => void onSkipErrors(e.target.checked)}
            />
          ) : null}
        </div>
      </Card>
      {errors.length ? (
        <Card
          title={`Errors (${formatCount(errors.length)})`}
          actions={
            <a
              className="text-[13px] font-medium text-accent-ink hover:underline"
              href={`/api/v1/data-transfers/${transfer.id}/errors`}
            >
              Download errors
            </a>
          }
          flush
        >
          <div className="max-h-96 overflow-auto">
            <table aria-label="Import errors" className="w-full text-left text-[13px]">
              <thead className="sticky top-0 bg-ground text-xs text-ink-secondary">
                <tr>
                  <th className="w-20 px-5 py-2 font-medium">Row</th>
                  <th className="w-44 px-3 py-2 font-medium">Column</th>
                  <th className="px-3 py-2 font-medium">Message</th>
                </tr>
              </thead>
              <tbody>
                {errors.map((e, i) => (
                  <tr key={i} className="h-9 border-t border-border">
                    <td className="tabular px-5">{e.row}</td>
                    <td className="px-3 text-ink-secondary">{e.column?.replaceAll("_", " ") ?? "—"}</td>
                    <td className="px-3">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
      {(summary.warnings?.length ?? 0) > 0 ? (
        <Card title={`Warnings (${formatCount(summary.warnings?.length ?? 0)})`}>
          <ul className="flex flex-col gap-1 text-[13px]">
            {summary.warnings?.slice(0, 20).map((w, i) => (
              <li key={i}>
                Row {w.row}: {w.message}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onBack}>
          ← Back to mapping
        </Button>
        <Button
          disabled={!summary.committable || step >= 3}
          title={summary.committable ? undefined : "Fix the errors or choose to skip rows with errors"}
          onClick={() => {
            onCommit().catch((err: unknown) => {
              toast(errorMessage(err), "error");
            });
          }}
        >
          Import {formatCount((counts.create ?? 0) + (counts.update ?? 0))}{" "}
          {entity === "test_case" ? "cases" : "references"}
        </Button>
      </div>
    </div>
  );
}
