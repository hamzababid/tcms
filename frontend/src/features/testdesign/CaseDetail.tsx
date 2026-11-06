import * as Menu from "@radix-ui/react-dropdown-menu";
import { useMutation } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Link } from "@tanstack/react-router";
import { ExternalLink, MoreHorizontal, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { api, ApiError } from "@/api/client";
import type { Me, Project, ProjectMember } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import { Card, EmptyState, ErrorState, Skeleton, errorMessage, useToast } from "@/components/common/feedback";
import { MarkdownView } from "@/components/common/Markdown";
import { PriorityIcon } from "@/components/common/PriorityIcon";
import { EXECUTION_STATUS } from "@/components/common/status";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Tag } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { formatDate, formatDateTime } from "@/lib/format";
import { can } from "@/lib/permissions";
import { MenuContent, MenuItem } from "@/components/ui/menu";
import { CaseBugs } from "@/features/bugs/components";
import { AuditTable, useAuditState } from "@/features/projects/AuditTable";
import { cn } from "@/lib/utils";

import {
  useCase,
  useCaseHistory,
  useExecutions,
  useInvalidateCase,
  useReviewers,
  useVersions,
  type CaseRead,
  type Execution,
  type VersionListItem,
} from "./api";
import { AttachmentList } from "./AttachmentList";
import { CommentThread } from "./CommentThread";
import { DiffView } from "./DiffView";
import { AUTOMATION, CASE_TYPES, TECHNIQUES, label } from "./labels";

type Action = "submit" | "approve" | "return" | "deprecate" | "archive" | "restore" | "duplicate" | "delete";

export function CaseDetail({
  project,
  caseId,
  me,
  perms,
  members,
  variant,
  onClose,
  onDeleted,
  onDuplicated,
}: {
  project: Project;
  caseId: string;
  me: Me;
  perms: Set<string>;
  members: ProjectMember[];
  variant: "panel" | "page";
  onClose?: () => void;
  onDeleted: () => void;
  onDuplicated: (key: string) => void;
}) {
  const [viewVersion, setViewVersion] = useState<number | null>(null);
  const [tab, setTab] = useState("details");
  const latest = useCase(caseId);
  const shown = useCase(caseId, viewVersion);
  const invalidate = useInvalidateCase();
  const refresh = () => {
    invalidate(project.id, caseId);
  };

  if (latest.isPending) return <Skeleton rows={6} />;
  if (latest.isError) return <ErrorState error={latest.error} onRetry={() => void latest.refetch()} />;
  const c = latest.data;
  const view = viewVersion && shown.data ? shown.data : c;
  const writable = project.status !== "archived";
  const editable = writable && can(perms, "testcase.edit") && c.status !== "archived";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className={cn(
          "flex flex-col gap-2 border-b border-border",
          variant === "panel" ? "px-5 py-4" : "pb-4",
        )}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[13px] font-medium text-ink-secondary">{c.key}</span>
          <StatusBadge kind="case" status={c.status} />
          <Tag tone="neutral">v{c.latest_version_no}</Tag>
          <span className="flex-1" />
          {editable ? (
            <Button asChild size="sm">
              <Link
                to="/p/$projectKey/cases/$caseKey/edit"
                params={{ projectKey: project.key, caseKey: c.key }}
              >
                Edit
              </Link>
            </Button>
          ) : null}
          <CaseActions
            project={project}
            c={c}
            me={me}
            perms={perms}
            members={members}
            writable={writable}
            onChanged={refresh}
            onDeleted={onDeleted}
            onDuplicated={onDuplicated}
          />
          {variant === "panel" ? (
            <>
              <Button asChild variant="ghost" size="icon" aria-label="Open full page">
                <Link to="/p/$projectKey/cases/$caseKey" params={{ projectKey: project.key, caseKey: c.key }}>
                  <ExternalLink className="size-4" />
                </Link>
              </Button>
              <Button variant="ghost" size="icon" aria-label="Close panel" onClick={onClose}>
                <X className="size-4" />
              </Button>
            </>
          ) : null}
        </div>
        <h2
          className={cn(
            "font-semibold leading-snug text-ink",
            variant === "page" ? "text-2xl" : "text-[17px]",
          )}
        >
          {c.title}
        </h2>
        {c.tags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {c.tags.map((t) => (
              <Tag key={t}>{t}</Tag>
            ))}
          </div>
        ) : null}
      </header>
      <ReviewBar project={project} c={c} me={me} perms={perms} writable={writable} onChanged={refresh} />
      {c.status === "archived" ? (
        <p
          role="status"
          className="mx-5 mt-3 rounded-control border border-border bg-ground px-3 py-2 text-[13px] text-ink-secondary"
        >
          This case is archived. Restore it to edit or use it in plans and cycles.
        </p>
      ) : null}
      {viewVersion && viewVersion !== c.latest_version_no ? (
        <p
          role="status"
          className="mx-5 mt-3 flex items-center justify-between rounded-control border border-[var(--status-progress-border)] bg-[var(--status-progress-bg)] px-3 py-2 text-[13px] text-[var(--status-progress-fg)]"
        >
          Viewing v{viewVersion}. The latest version is v{c.latest_version_no}.
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              setViewVersion(null);
            }}
          >
            Show latest
          </Button>
        </p>
      ) : null}
      <div className="flex min-h-0 flex-1 flex-col">
        <Tabs
          label="Case sections"
          value={tab}
          onValueChange={setTab}
          className="flex min-h-0 flex-1 flex-col"
          listClassName={variant === "panel" ? "px-3" : ""}
          contentClassName={cn("min-h-0 flex-1 overflow-y-auto", variant === "panel" ? "px-5 py-4" : "py-5")}
          items={[
            {
              value: "details",
              label: "Details",
              content: (
                <Details
                  project={project}
                  c={view}
                  perms={perms}
                  editable={editable && !viewVersion}
                  onChanged={refresh}
                  layout={variant}
                />
              ),
            },
            {
              value: "versions",
              label: "Versions",
              count: c.latest_version_no,
              content: (
                <Versions
                  c={c}
                  canRestore={editable}
                  onView={(n) => {
                    setViewVersion(n === c.latest_version_no ? null : n);
                    setTab("details");
                  }}
                  onChanged={refresh}
                />
              ),
            },
            { value: "executions", label: "Executions", content: <Executions caseId={c.id} /> },
            {
              value: "bugs",
              label: "Bugs",
              content: (
                <CaseBugs
                  project={project}
                  caseId={c.id}
                  caseKey={c.key}
                  canLink={writable && can(perms, "defect.create")}
                  canRetest={writable && can(perms, "cycle.manage")}
                />
              ),
            },
            { value: "history", label: "History", content: <History caseId={c.id} members={members} /> },
            {
              value: "comments",
              label: "Comments",
              count: c.counts.comments,
              content: (
                <CommentThread
                  entityType="test_case"
                  entityId={c.id}
                  me={me}
                  members={members}
                  canComment={writable && can(perms, "comment.create")}
                />
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}

// -- details --------------------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-5 text-[13px]">
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-[0.04em] text-ink-secondary">{title}</h3>
      {children}
    </section>
  );
}

function Details({
  project,
  c,
  perms,
  editable,
  onChanged,
  layout,
}: {
  project: Project;
  c: CaseRead;
  perms: Set<string>;
  editable: boolean;
  onChanged: () => void;
  layout: "panel" | "page";
}) {
  const v = c.version;
  const maxMb = project.settings.attachment_max_mb;
  const properties = (
    <dl
      className={cn(
        "grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[13px]",
        layout === "panel" && "mb-5",
      )}
    >
      <dt className="text-ink-secondary">Folder</dt>
      <dd className="text-ink">{c.folder.path_names.join(" › ")}</dd>
      <dt className="text-ink-secondary">Type</dt>
      <dd className="text-ink">
        {label(CASE_TYPES, c.type)}
        {c.design_technique ? ` · ${label(TECHNIQUES, c.design_technique)}` : ""}
      </dd>
      <dt className="text-ink-secondary">Priority</dt>
      <dd>
        <PriorityIcon priority={c.priority} />
      </dd>
      <dt className="text-ink-secondary">Owner</dt>
      <dd className="text-ink">{c.owner?.display_name ?? "—"}</dd>
      <dt className="text-ink-secondary">Reviewer</dt>
      <dd className="text-ink">{c.reviewer?.display_name ?? "—"}</dd>
      <dt className="text-ink-secondary">Automation</dt>
      <dd className="text-ink">
        {label(AUTOMATION, c.automation_status)}
        {c.automation_keys.length ? (
          <span className="ml-2 font-mono text-xs text-ink-secondary">{c.automation_keys.join(", ")}</span>
        ) : null}
      </dd>
      <dt className="text-ink-secondary">Estimate</dt>
      <dd className="text-ink">{c.estimated_minutes !== null ? `${c.estimated_minutes} min` : "—"}</dd>
      <dt className="text-ink-secondary">Approved</dt>
      <dd className="text-ink">{c.approved_version_no ? `v${c.approved_version_no}` : "Not yet"}</dd>
      <dt className="text-ink-secondary">Version</dt>
      <dd className="text-ink">
        v{v.version_no} · {v.created_by?.display_name ?? "—"} · {formatDateTime(v.created_at)}
        {v.change_note ? <span className="block text-xs text-ink-secondary">{v.change_note}</span> : null}
      </dd>
    </dl>
  );
  return (
    <div
      className={cn(
        "[&_.md]:text-[13px]",
        layout === "page" && "grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]",
      )}
    >
      {layout === "page" ? (
        <aside className="xl:order-2">
          <Card title="Properties">{properties}</Card>
        </aside>
      ) : (
        properties
      )}
      <div className="min-w-0 xl:order-1">
        {v.description ? (
          <Section title="Description">
            <MarkdownView text={v.description} />
          </Section>
        ) : null}
        {v.preconditions ? (
          <Section title="Preconditions">
            <MarkdownView text={v.preconditions} />
          </Section>
        ) : null}
        {v.test_data ? (
          <Section title="Test data">
            <MarkdownView text={v.test_data} />
          </Section>
        ) : null}
        {v.format === "steps" ? (
          <Section title={`Steps (${v.steps.length})`}>
            <ol className="overflow-hidden rounded-control border border-border">
              {v.steps.map((s) => (
                <li
                  key={s.id}
                  className="grid grid-cols-[24px_minmax(0,1fr)_minmax(0,1fr)] gap-2.5 border-t border-rule px-3 py-2.5 first:border-t-0"
                >
                  <span className="tabular font-semibold text-ink-muted">{s.position}</span>
                  <div>
                    <MarkdownView text={s.action} />
                    {s.data ? (
                      <MarkdownView text={s.data} className="mt-1 text-xs text-ink-secondary" />
                    ) : null}
                  </div>
                  <div className="text-ink-secondary">
                    <MarkdownView text={s.expected_result} />
                    {s.attachments.length ? (
                      <div className="mt-2">
                        <AttachmentList
                          attachments={s.attachments}
                          entityType="test_case_step"
                          entityId={s.id}
                          canUpload={false}
                          canRemove={() => false}
                          maxMb={maxMb}
                          onChanged={onChanged}
                        />
                      </div>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          </Section>
        ) : (
          <Section title="Procedure">
            <MarkdownView text={v.text_body} />
          </Section>
        )}
        {v.expected_result ? (
          <Section title="Overall expected result">
            <MarkdownView text={v.expected_result} />
          </Section>
        ) : null}
        {v.postconditions ? (
          <Section title="Postconditions">
            <MarkdownView text={v.postconditions} />
          </Section>
        ) : null}
        <Section title={`Attachments (${c.attachments.length})`}>
          {c.attachments.length || editable ? (
            <AttachmentList
              attachments={c.attachments}
              entityType="test_case"
              entityId={c.id}
              canUpload={editable}
              canRemove={() => editable}
              maxMb={maxMb}
              onChanged={onChanged}
            />
          ) : (
            <p className="text-[13px] text-ink-muted">None</p>
          )}
        </Section>
        <RelatedCases
          project={project}
          c={c}
          editable={editable && can(perms, "testcase.edit")}
          onChanged={onChanged}
        />
      </div>
    </div>
  );
}

function RelatedCases({
  project,
  c,
  editable,
  onChanged,
}: {
  project: Project;
  c: CaseRead;
  editable: boolean;
  onChanged: () => void;
}) {
  const [key, setKey] = useState("");
  const add = useMutation({
    mutationFn: async () => {
      const target = await api.GET("/api/v1/projects/{project_id}/resolve", {
        params: { path: { project_id: project.id }, query: { key: key.trim() } },
      });
      if (!target.data) throw new Error("not found");
      return api.POST("/api/v1/test-cases/{case_id}/links", {
        params: { path: { case_id: c.id } },
        body: { target_case_id: target.data.id, link_type: "related" },
      });
    },
    onSuccess: () => {
      setKey("");
      onChanged();
    },
  });
  const remove = useMutation({
    mutationFn: async (target: { case_id: string; link_type: "related" | "duplicated_from" }) =>
      api.DELETE("/api/v1/test-cases/{case_id}/links", {
        params: { path: { case_id: c.id } },
        body: { target_case_id: target.case_id, link_type: target.link_type },
      }),
    onSuccess: onChanged,
  });
  const dirLabel = { related: "Related", duplicated_from: "Duplicated from", duplicated_to: "Duplicated to" };
  return (
    <Section title={`Related cases (${c.links.length})`}>
      {c.links.length ? (
        <ul className="mb-2 flex flex-col gap-1 text-[13px]">
          {c.links.map((lk) => (
            <li key={`${lk.case_id}-${lk.direction}`} className="flex items-center gap-2">
              <span className="text-xs text-ink-muted">{dirLabel[lk.direction]}</span>
              <Link
                to="/p/$projectKey/cases/$caseKey"
                params={{ projectKey: project.key, caseKey: lk.key }}
                className="font-mono text-xs text-link hover:underline"
              >
                {lk.key}
              </Link>
              <span className="min-w-0 flex-1 truncate text-ink">{lk.title}</span>
              <StatusBadge kind="case" status={lk.status} compact />
              {editable && lk.direction === "related" ? (
                <button
                  type="button"
                  aria-label={`Unlink ${lk.key}`}
                  className="rounded p-0.5 text-ink-muted hover:bg-ground"
                  onClick={() => {
                    remove.mutate({ case_id: lk.case_id, link_type: "related" });
                  }}
                >
                  <X className="size-3.5" />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {editable ? (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (key.trim()) add.mutate();
          }}
        >
          <Input
            aria-label="Case key to link"
            placeholder={`${project.key}-TC-…`}
            className="h-8 w-48"
            value={key}
            onChange={(e) => {
              setKey(e.target.value);
            }}
          />
          <Button type="submit" variant="secondary" size="sm" disabled={add.isPending || !key.trim()}>
            Link case
          </Button>
          {add.error ? (
            <span role="alert" className="self-center text-xs text-danger">
              {add.error instanceof ApiError && add.error.status === 404
                ? "No case with that key"
                : errorMessage(add.error)}
            </span>
          ) : null}
        </form>
      ) : c.links.length === 0 ? (
        <p className="text-[13px] text-ink-muted">None</p>
      ) : null}
    </Section>
  );
}

// -- versions -------------------------------------------------------------------------------------

function Versions({
  c,
  canRestore,
  onView,
  onChanged,
}: {
  c: CaseRead;
  canRestore: boolean;
  onView: (n: number) => void;
  onChanged: () => void;
}) {
  const versions = useVersions(c.id);
  const [pick, setPick] = useState<number[]>([]);
  const [compare, setCompare] = useState<[number, number] | null>(null);
  const [restore, setRestore] = useState<number | null>(null);
  const restoreMut = useMutation({
    mutationFn: async (n: number) =>
      api.POST("/api/v1/test-cases/{case_id}/restore-version", {
        params: { path: { case_id: c.id } },
        body: { version_no: n, row_version: c.row_version },
      }),
    onSuccess: () => {
      setRestore(null);
      onChanged();
      void versions.refetch();
    },
  });
  if (versions.isError) return <ErrorState error={versions.error} />;
  const sorted = [...pick].sort((a, b) => a - b);
  const approvalOf = (v: VersionListItem) =>
    v.approval ? (v.approval.mode === "auto" ? "auto" : "manual") : v.submission ? "review" : "none";
  const APPROVAL_LABEL: Record<string, string> = {
    auto: "Auto",
    manual: "Approved",
    review: "In review",
    none: "Not approved",
  };
  const authors = [...new Set((versions.data ?? []).map((v) => v.created_by?.display_name ?? "—"))];
  const columns: ColumnDef<VersionListItem>[] = [
    {
      id: "pick",
      header: () => <span className="sr-only">Compare</span>,
      enableSorting: false,
      cell: (x) => {
        const v = x.row.original;
        return (
          <input
            type="checkbox"
            aria-label={`Compare v${v.version_no}`}
            checked={pick.includes(v.version_no)}
            onChange={(e) => {
              setPick((p) =>
                e.target.checked
                  ? [...p.filter((n) => n !== v.version_no), v.version_no].slice(-2)
                  : p.filter((n) => n !== v.version_no),
              );
            }}
          />
        );
      },
      meta: { width: "w-10", fixed: true, label: "Compare" },
    },
    {
      id: "version_no",
      accessorKey: "version_no",
      header: "Ver",
      cell: (x) => (
        <span className="whitespace-nowrap font-medium">
          v{x.row.original.version_no}
          {x.row.original.is_latest ? (
            <Tag tone="neutral" className="ml-1.5">
              latest
            </Tag>
          ) : null}
        </span>
      ),
      meta: { width: "w-24", fixed: true },
    },
    {
      accessorKey: "created_at",
      header: "Date",
      cell: (x) => (
        <span className="whitespace-nowrap text-ink-secondary">{formatDate(x.row.original.created_at)}</span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      id: "author",
      accessorFn: (v) => v.created_by?.display_name ?? "—",
      header: "Author",
      cell: (x) => <span className="whitespace-nowrap">{x.getValue() as string}</span>,
      meta: {
        filter: { kind: "select", options: authors.map((a) => ({ value: a, label: a })) },
        width: "w-36",
      },
    },
    {
      id: "note",
      accessorFn: (v) => v.change_note ?? "",
      header: "Note",
      cell: (x) => (
        <span className="block max-w-[260px] truncate text-ink-secondary" title={x.getValue() as string}>
          {(x.getValue() as string) || "—"}
        </span>
      ),
      meta: { filter: { kind: "text" } },
    },
    {
      id: "approval",
      accessorFn: approvalOf,
      header: "Approval",
      cell: (x) => {
        const v = x.row.original;
        return (
          <span className="whitespace-nowrap text-ink-secondary">
            {APPROVAL_LABEL[approvalOf(v)]}
            {v.approval?.mode === "manual" && v.approval.approved_by
              ? ` · ${v.approval.approved_by.display_name}`
              : ""}
          </span>
        );
      },
      meta: {
        filter: {
          kind: "select",
          options: Object.entries(APPROVAL_LABEL).map(([value, label]) => ({ value, label })),
        },
        width: "w-40",
      },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      cell: (x) => {
        const v = x.row.original;
        return (
          <span className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                onView(v.version_no);
              }}
            >
              View
            </Button>
            {canRestore && !v.is_latest ? (
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  setRestore(v.version_no);
                }}
              >
                Restore
              </Button>
            ) : null}
          </span>
        );
      },
      meta: { align: "right", width: "w-36", fixed: true, label: "Actions" },
    },
  ];
  return (
    <div className="flex flex-col gap-4">
      <DataTable
        label="Versions"
        columns={columns}
        data={versions.data ?? []}
        loading={versions.isPending}
        getRowId={(v) => String(v.version_no)}
        noun={["version", "versions"]}
        initialPageSize={10}
        dense
        initialHidden={["note", "created_at", "author"]}
        toolbar={
          <Button
            variant="secondary"
            size="xs"
            disabled={sorted.length !== 2}
            onClick={() => {
              setCompare([sorted[0] as number, sorted[1] as number]);
            }}
          >
            {sorted.length === 2 ? `Compare v${sorted[0]} ↔ v${sorted[1]}` : "Select two versions to compare"}
          </Button>
        }
      />
      {compare ? <DiffView caseId={c.id} from={compare[0]} to={compare[1]} /> : null}
      <ConfirmDialog
        open={restore !== null}
        onOpenChange={(o) => {
          if (!o) setRestore(null);
        }}
        title={`Restore v${restore ?? ""}?`}
        description={`This creates v${c.latest_version_no + 1} with the content of v${restore ?? ""}. Earlier versions are kept.`}
        confirmLabel="Restore"
        pending={restoreMut.isPending}
        error={restoreMut.error}
        onConfirm={() => {
          if (restore) restoreMut.mutate(restore);
        }}
      />
    </div>
  );
}

// -- executions and history -----------------------------------------------------------------------

function Executions({ caseId }: { caseId: string }) {
  const runs = useExecutions(caseId);
  const people = [...new Set((runs.data ?? []).map((r) => r.executed_by?.display_name ?? "—"))];
  const columns: ColumnDef<Execution>[] = [
    {
      id: "cycle",
      accessorFn: (r) => `${r.cycle_key} ${r.cycle_name}`,
      header: "Cycle",
      cell: (x) => (
        <span className="whitespace-nowrap">
          <span className="font-mono text-[12.5px] font-medium">{x.row.original.cycle_key}</span>{" "}
          {x.row.original.cycle_name}
        </span>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      accessorKey: "version_no",
      header: "Version",
      cell: (x) => `v${x.row.original.version_no}`,
      meta: { width: "w-24" },
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: (x) => <StatusBadge kind="execution" status={x.row.original.status} />,
      meta: {
        filter: {
          kind: "select",
          options: Object.entries(EXECUTION_STATUS).map(([value, s]) => ({ value, label: s.label })),
        },
        width: "w-40",
      },
    },
    {
      id: "executed_by",
      accessorFn: (r) => r.executed_by?.display_name ?? "—",
      header: "Executed by",
      meta: {
        filter: { kind: "select", options: people.map((p) => ({ value: p, label: p })) },
        width: "w-40",
      },
    },
    {
      accessorKey: "finished_at",
      header: "Date",
      cell: (x) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {formatDateTime(x.row.original.finished_at)}
        </span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
  ];
  if (runs.isError) return <ErrorState error={runs.error} />;
  return (
    <DataTable
      label="Executions"
      columns={columns}
      data={runs.data ?? []}
      loading={runs.isPending}
      getRowId={(r) => r.run_id}
      noun={["run", "runs"]}
      initialPageSize={10}
      dense
      initialHidden={["executed_by"]}
      empty={<EmptyState text="This case has not been in a cycle yet." />}
    />
  );
}

function History({ caseId, members }: { caseId: string; members: ProjectMember[] }) {
  const state = useAuditState(10);
  const history = useCaseHistory(caseId, state.query);
  return (
    <AuditTable
      label="Case history"
      rows={history.data?.items ?? []}
      total={history.data?.total ?? 0}
      loading={history.isPending}
      error={history.error}
      onRetry={() => void history.refetch()}
      members={members}
      state={state}
      showType={false}
      dense
    />
  );
}

// -- review and lifecycle actions -----------------------------------------------------------------

function useCaseAction(c: CaseRead, onDone: (data: unknown) => void) {
  const toast = useToast();
  return useMutation({
    mutationFn: async ({ action, body }: { action: Action; body?: Record<string, unknown> }) => {
      const path = { params: { path: { case_id: c.id } } };
      switch (action) {
        case "submit":
          return (await api.POST("/api/v1/test-cases/{case_id}/submit", { ...path, body: body ?? {} })).data;
        case "approve":
          return (
            await api.POST("/api/v1/test-cases/{case_id}/approve", {
              ...path,
              body: { row_version: c.row_version, ...body },
            })
          ).data;
        case "return":
          return (
            await api.POST("/api/v1/test-cases/{case_id}/return", {
              ...path,
              body: { comment: typeof body?.comment === "string" ? body.comment : "" },
            })
          ).data;
        case "deprecate":
          return (await api.POST("/api/v1/test-cases/{case_id}/deprecate", { ...path, body: body ?? {} }))
            .data;
        case "archive":
          return (await api.POST("/api/v1/test-cases/{case_id}/archive", { ...path, body: body ?? {} })).data;
        case "restore":
          return (await api.POST("/api/v1/test-cases/{case_id}/restore", { ...path, body: body ?? {} })).data;
        case "duplicate":
          return (await api.POST("/api/v1/test-cases/{case_id}/duplicate", { ...path, body: {} })).data;
        case "delete":
          await api.DELETE("/api/v1/test-cases/{case_id}", path);
          return null;
      }
    },
    onSuccess: onDone,
    onError: (e) => {
      toast(errorMessage(e), "error");
    },
  });
}

function selfApprovalBlocked(project: Project, c: CaseRead, me: Me): boolean {
  return !project.settings.allow_self_approval && c.version.created_by?.id === me.user.id;
}

/** Review mode (docs/07 §5.6): Approve / Return… when in review and the user may approve. */
function ReviewBar({
  project,
  c,
  me,
  perms,
  writable,
  onChanged,
}: {
  project: Project;
  c: CaseRead;
  me: Me;
  perms: Set<string>;
  writable: boolean;
  onChanged: () => void;
}) {
  const [returning, setReturning] = useState(false);
  const [showDiff, setShowDiff] = useState(true);
  const act = useCaseAction(c, () => {
    setReturning(false);
    onChanged();
  });
  if (c.status !== "in_review" || !writable || !can(perms, "testcase.approve")) return null;
  const blocked = selfApprovalBlocked(project, c, me);
  return (
    <div className="border-b border-border bg-[var(--status-progress-bg)] px-4 py-2">
      <div className="flex items-center gap-2 text-[13px] text-[var(--status-progress-fg)]">
        <span className="flex-1">
          v{c.latest_version_no} is waiting for review
          {c.version.submission?.submitted_by
            ? ` · submitted by ${c.version.submission.submitted_by.display_name}`
            : ""}
        </span>
        {c.approved_version_no ? (
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              setShowDiff((s) => !s);
            }}
          >
            {showDiff ? "Hide changes" : `Changes since v${c.approved_version_no}`}
          </Button>
        ) : null}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            setReturning(true);
          }}
        >
          Return…
        </Button>
        <span title={blocked ? "You can't approve your own version" : undefined}>
          <Button
            size="sm"
            disabled={blocked || act.isPending}
            onClick={() => {
              act.mutate({ action: "approve" });
            }}
          >
            Approve
          </Button>
        </span>
      </div>
      {showDiff && c.approved_version_no && c.approved_version_no !== c.latest_version_no ? (
        <div className="mt-2 max-h-80 overflow-y-auto rounded-control border border-border bg-surface p-3">
          <DiffView caseId={c.id} from={c.approved_version_no} to={c.latest_version_no} />
        </div>
      ) : null}
      <PromptDialog
        open={returning}
        onOpenChange={setReturning}
        title={`Return ${c.key} to the author`}
        label="What needs to change?"
        submitLabel="Return"
        multiline
        pending={act.isPending}
        error={act.error}
        onSubmit={(comment) => {
          act.mutate({ action: "return", body: { comment } });
        }}
      />
    </div>
  );
}

function CaseActions({
  project,
  c,
  me,
  perms,
  members,
  writable,
  onChanged,
  onDeleted,
  onDuplicated,
}: {
  project: Project;
  c: CaseRead;
  me: Me;
  perms: Set<string>;
  members: ProjectMember[];
  writable: boolean;
  onChanged: () => void;
  onDeleted: () => void;
  onDuplicated: (key: string) => void;
}) {
  const [dialog, setDialog] = useState<Action | null>(null);
  const [reviewer, setReviewer] = useState(c.reviewer?.id ?? "");
  const [note, setNote] = useState("");
  const toast = useToast();
  const act = useCaseAction(c, (data) => {
    const action = dialog;
    setDialog(null);
    if (action === "delete") {
      toast(`${c.key} deleted`);
      onDeleted();
      return;
    }
    onChanged();
    if (action === "duplicate" && data && typeof data === "object" && "case" in data) {
      const key = (data as { case: CaseRead }).case.key;
      toast(`Created ${key}`);
      onDuplicated(key);
    }
  });
  const reviewers = useReviewers(members);
  if (!writable) return null;
  const approval = project.settings.approval_required;
  const items: [Action, string][] = [];
  if (approval && c.status === "draft" && can(perms, "testcase.edit"))
    items.push(["submit", "Submit for review…"]);
  if (c.status === "in_review" && can(perms, "testcase.approve") && !selfApprovalBlocked(project, c, me)) {
    items.push(["approve", "Approve"]);
  }
  if (c.status === "in_review" && can(perms, "testcase.approve")) items.push(["return", "Return…"]);
  if (can(perms, "testcase.create") && c.status !== "archived") items.push(["duplicate", "Duplicate"]);
  if (can(perms, "testcase.archive")) {
    if (c.status === "approved") items.push(["deprecate", "Deprecate"]);
    if (c.status !== "archived") items.push(["archive", "Archive"]);
    if (c.status === "archived" || c.status === "deprecated") items.push(["restore", "Restore"]);
  }
  if (can(perms, "testcase.delete")) items.push(["delete", "Delete…"]);
  if (items.length === 0) return null;
  return (
    <>
      <Menu.Root>
        <Menu.Trigger asChild>
          <Button variant="ghost" size="icon" aria-label="Case actions">
            <MoreHorizontal className="size-4" />
          </Button>
        </Menu.Trigger>
        <MenuContent align="end">
          {items.map(([a, l]) => (
            <MenuItem
              key={a}
              danger={a === "delete"}
              onSelect={() => {
                if (a === "approve" || a === "duplicate" || a === "deprecate" || a === "restore")
                  act.mutate({ action: a });
                else setDialog(a);
              }}
            >
              {l}
            </MenuItem>
          ))}
        </MenuContent>
      </Menu.Root>
      <Dialog
        open={dialog === "submit"}
        onOpenChange={(o) => {
          if (!o) setDialog(null);
        }}
        title={`Submit ${c.key} for review`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setDialog(null);
              }}
            >
              Cancel
            </Button>
            <Button
              disabled={act.isPending}
              onClick={() => {
                act.mutate({
                  action: "submit",
                  body: { reviewer_id: reviewer || null, comment: note.trim() || null },
                });
              }}
            >
              Submit
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <Field label="Reviewer">
            {(p) => (
              <Select
                {...p}
                value={reviewer}
                onChange={(e) => {
                  setReviewer(e.target.value);
                }}
              >
                <option value="">Anyone who can approve</option>
                {reviewers.map((m) => (
                  <option key={m.user.id} value={m.user.id}>
                    {m.user.display_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Note for the reviewer">
            {(p) => (
              <textarea
                {...p}
                rows={3}
                value={note}
                onChange={(e) => {
                  setNote(e.target.value);
                }}
                className="w-full rounded-control border border-border bg-surface px-3 py-2 text-[13px]"
              />
            )}
          </Field>
        </div>
      </Dialog>
      <PromptDialog
        open={dialog === "return"}
        onOpenChange={(o) => {
          if (!o) setDialog(null);
        }}
        title={`Return ${c.key} to the author`}
        label="What needs to change?"
        submitLabel="Return"
        multiline
        pending={act.isPending}
        error={act.error}
        onSubmit={(comment) => {
          act.mutate({ action: "return", body: { comment } });
        }}
      />
      <PromptDialog
        open={dialog === "archive"}
        onOpenChange={(o) => {
          if (!o) setDialog(null);
        }}
        title={`Archive ${c.key}`}
        label="Reason"
        required={false}
        submitLabel="Archive"
        pending={act.isPending}
        error={act.error}
        onSubmit={(reason) => {
          act.mutate({ action: "archive", body: reason ? { reason } : {} });
        }}
      />
      <ConfirmDialog
        open={dialog === "delete"}
        onOpenChange={(o) => {
          if (!o) setDialog(null);
        }}
        title={`Delete ${c.key} permanently?`}
        description="Only cases that were never in a cycle can be deleted. Archive the case to keep its history instead."
        confirmLabel="Delete"
        confirmText={c.key}
        destructive
        pending={act.isPending}
        error={act.error}
        onConfirm={() => {
          act.mutate({ action: "delete" });
        }}
      />
    </>
  );
}
