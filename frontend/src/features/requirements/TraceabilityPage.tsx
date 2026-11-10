import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { Fragment, useState } from "react";

import { useReleases, type Project } from "@/api/queries";
import { EmptyState, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Checkbox, Input, Select } from "@/components/ui/field";
import { Pager, usePaging } from "@/components/common/DataTable";
import { MoreList } from "@/components/common/MoreList";
import { safeUrl } from "@/features/bugs/api";
import { formatDateTime } from "@/lib/format";
import { useDebounced } from "@/lib/useDebounced";

import { STATUS_LABEL, useTraceability, type Coverage, type RefStatus, type TraceQuery } from "./api";
import { LatestMark, RefLink, RequirementDialog } from "./components";

const STATUSES: RefStatus[] = ["failed", "blocked", "not_run", "passed", "not_covered"];

function pct(r: Coverage["coverage"]): string {
  return r.value === null ? "—" : `${Math.round(r.value * 100)}%`;
}

/** Traceability matrix (docs/07 §5.11, docs/design/Traceability.dc.html; FR-REQ-004; ADR-024: flat list). */
export function TraceabilityPage({
  project,
  canManage,
  canLink,
}: {
  project: Project;
  canManage: boolean;
  canLink: boolean;
}) {
  const releases = useReleases(project.id);
  const [releaseId, setReleaseId] = useState("");
  const [status, setStatus] = useState("");
  const [uncovered, setUncovered] = useState(false);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<string | null>(null);
  const search = useDebounced(q.trim());
  const where = {
    ...(releaseId ? { release_id: releaseId } : {}),
    ...(status ? { status } : {}),
    ...(uncovered ? { uncovered: true } : {}),
    ...(search ? { q: search } : {}),
  };
  const [pagination, setPagination] = usePaging(JSON.stringify(where));
  const query: TraceQuery = { ...where, page: pagination.pageIndex + 1, page_size: pagination.pageSize };
  const trace = useTraceability(project.id, query);
  const s = trace.data?.summary;
  const writable = project.status !== "archived";
  const toggle = (id: string) => {
    setOpen((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <Page
      title="Traceability"
      subtitle="Which requirements are covered by test cases and how they did in the release."
      width="full"
    >
      <div className="mb-4 flex flex-wrap items-center gap-3 text-[13px]">
        <label className="flex items-center gap-2">
          <span className="text-ink-secondary">Release</span>
          <Select
            aria-label="Release"
            className="w-48"
            value={releaseId}
            onChange={(e) => {
              setReleaseId(e.target.value);
            }}
          >
            <option value="">All cycles</option>
            {(releases.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-ink-secondary">Status</span>
          <Select
            aria-label="Status in release"
            className="w-40"
            value={status}
            disabled={uncovered}
            onChange={(e) => {
              setStatus(e.target.value);
            }}
          >
            <option value="">Any</option>
            {STATUSES.map((st) => (
              <option key={st} value={st}>
                {STATUS_LABEL[st]}
              </option>
            ))}
          </Select>
        </label>
        <Checkbox
          label="Uncovered only"
          checked={uncovered}
          onChange={(e) => {
            setUncovered(e.target.checked);
          }}
        />
        <Input
          aria-label="Find requirement"
          placeholder="Reference or title"
          className="w-56"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
          }}
        />
      </div>
      {s ? (
        <p aria-label="Coverage summary" className="mb-3 text-[13.5px] text-ink">
          Coverage <strong>{s.covered}</strong> of {s.total} ({pct(s.coverage)}) · Verified{" "}
          <strong>{s.passed}</strong> of {s.total} ({pct(s.verified)}) · Failed {s.failed} · Blocked{" "}
          {s.blocked} · Not run {s.not_run} · Not covered {s.not_covered}
        </p>
      ) : null}
      {trace.isPending ? (
        <Skeleton rows={6} />
      ) : trace.isError ? (
        <ErrorState error={trace.error} onRetry={() => void trace.refetch()} />
      ) : trace.data.rows.length === 0 ? (
        <EmptyState text="No requirements match. Add references on the Requirements page or a plan's Requirements tab." />
      ) : (
        <div className="rounded-card border border-border bg-surface">
          <div className="overflow-x-auto">
            <table aria-label="Traceability matrix" className="w-full text-left text-[13px]">
              <thead className="bg-ground text-xs text-ink-secondary">
                <tr>
                  <th className="px-3 py-2 font-medium">Requirement</th>
                  <th className="w-20 px-3 py-2 text-right font-medium">Cases</th>
                  <th className="w-40 px-3 py-2 font-medium">Status in release</th>
                  <th className="px-3 py-2 font-medium">Latest results</th>
                  <th className="w-48 px-3 py-2 font-medium">Bugs</th>
                </tr>
              </thead>
              <tbody>
                {trace.data.rows.map((row) => {
                  const r = row.requirement;
                  const expanded = open.has(r.id);
                  return (
                    <Fragment key={r.id}>
                      <tr className="h-11 border-t border-border">
                        <td className="px-3">
                          <span className="flex min-w-0 items-center gap-1.5">
                            <button
                              type="button"
                              aria-expanded={expanded}
                              aria-label={`${expanded ? "Collapse" : "Expand"} ${r.reference}`}
                              disabled={row.linked_cases === 0}
                              className="rounded p-0.5 text-ink-muted hover:bg-surface-muted disabled:opacity-30"
                              onClick={() => {
                                toggle(r.id);
                              }}
                            >
                              {expanded ? (
                                <ChevronDown aria-hidden="true" className="size-4" />
                              ) : (
                                <ChevronRight aria-hidden="true" className="size-4" />
                              )}
                            </button>
                            <RefLink r={r} />
                            <Button
                              variant="link"
                              size="xs"
                              onClick={() => {
                                setDetail(r.id);
                              }}
                            >
                              Details
                            </Button>
                          </span>
                        </td>
                        <td
                          className={`tabular px-3 text-right ${row.linked_cases === 0 ? "text-danger" : ""}`}
                        >
                          {row.linked_cases}
                        </td>
                        <td className="px-3">
                          <StatusBadge kind="requirement" status={row.status_in_release} />
                        </td>
                        <td className="px-3">
                          {row.cases.length ? (
                            <MoreList
                              max={6}
                              label={`Latest results for ${r.reference}`}
                              items={row.cases.map((c) => ({
                                key: c.id,
                                node: <LatestMark c={c} project={project} />,
                              }))}
                            />
                          ) : canLink && writable ? (
                            <Button
                              variant="link"
                              size="xs"
                              onClick={() => {
                                setDetail(r.id);
                              }}
                            >
                              <Plus aria-hidden="true" className="size-3.5" /> Link cases
                            </Button>
                          ) : (
                            <span className="text-ink-muted">—</span>
                          )}
                        </td>
                        <td className="px-3">
                          {row.bugs.length ? (
                            <MoreList
                              max={4}
                              label={`Bugs for ${r.reference}`}
                              items={row.bugs.map((b) => {
                                const href = safeUrl(b.url);
                                const node = href ? (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="font-mono text-xs text-[var(--status-fail-fg)] hover:underline"
                                  >
                                    {b.reference}
                                  </a>
                                ) : (
                                  <span className="font-mono text-xs text-[var(--status-fail-fg)]">
                                    {b.reference}
                                  </span>
                                );
                                return { key: b.reference, node };
                              })}
                            />
                          ) : (
                            <span className="text-ink-muted">—</span>
                          )}
                        </td>
                      </tr>
                      {expanded
                        ? row.cases.map((c) => (
                            <tr key={c.id} className="h-9 border-t border-border bg-ground/60 text-[12.5px]">
                              <td className="px-3 pl-10" colSpan={2}>
                                <span className="font-mono">{c.key}</span>{" "}
                                <span className="text-ink-secondary">{c.title}</span>
                              </td>
                              <td className="px-3">
                                <StatusBadge kind="execution" status={c.latest?.status ?? "not_run"} />
                              </td>
                              <td className="px-3 text-ink-secondary" colSpan={2}>
                                {c.latest
                                  ? `${c.latest.cycle_key} · ${formatDateTime(c.latest.finished_at)} · ${c.latest.executed_by?.display_name ?? "—"}`
                                  : "No result in the release"}
                              </td>
                            </tr>
                          ))
                        : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pager
            label="Traceability matrix"
            total={trace.data.total}
            pagination={pagination}
            onChange={setPagination}
            noun={["requirement", "requirements"]}
          />
        </div>
      )}
      <p className="mt-3 text-xs text-ink-secondary">
        Status rule: Failed if any linked case failed · then Blocked · then Not run if any case has no result
        in the release · Passed only when every linked case passed.
      </p>
      <RequirementDialog
        project={project}
        refId={detail}
        releaseId={releaseId || null}
        canManage={canManage && writable}
        canLink={canLink && writable}
        onClose={() => {
          setDetail(null);
        }}
      />
    </Page>
  );
}
