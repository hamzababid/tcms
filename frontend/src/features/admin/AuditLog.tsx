import type { ColumnDef } from "@tanstack/react-table";
import { Download } from "lucide-react";
import { useState } from "react";

import { useMembers, useOrgMembers, useProjects, type Project } from "@/api/queries";
import { DataTable, filterValue, type FilterOption } from "@/components/common/DataTable";
import { Page } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ENTITY_TYPES, useAuditState } from "@/features/projects/AuditTable";
import { formatDateTime } from "@/lib/format";

import { downloadUrl, useAuditEvents, type AuditEvent, type OrgAuditQuery } from "./api";

/** Record types in the audit log: the project feed's plus organization-level ones. */
const TYPES: FilterOption[] = [
  ...ENTITY_TYPES,
  { value: "requirement_ref", label: "Requirement" },
  { value: "bug_link", label: "Bug link" },
  { value: "release_decision", label: "Release decision" },
  { value: "saved_view", label: "Saved view" },
  { value: "data_transfer", label: "Import or export" },
  { value: "report", label: "Report export" },
  { value: "import_mapping", label: "Import template" },
  { value: "organization", label: "Organization" },
  { value: "user", label: "User" },
  { value: "invitation", label: "Invitation" },
  { value: "session", label: "Session" },
  { value: "api_token", label: "API token" },
  { value: "job", label: "Job" },
];
const typeLabel = (v: string) => TYPES.find((t) => t.value === v)?.label ?? v;

/** US-162 (docs/02 §13.3, docs/07 §5.13): the organization's audit log. */
export function OrgAuditLogPage() {
  const projects = useProjects();
  const members = useOrgMembers();
  return (
    <AuditLog
      title="Audit log"
      subtitle="Every recorded change in the organization, newest first. Events cannot be edited or deleted."
      people={(members.data ?? []).map((m) => ({ value: m.user.id, label: m.user.display_name }))}
      projects={(projects.data ?? []).map((p) => ({ value: p.id, label: p.key }))}
      csvPath="/api/v1/organization/audit-events"
    />
  );
}

/** docs/06 §4.12: one project's audit log (`project.audit.view`). */
export function ProjectAuditLogPage({ project }: { project: Project }) {
  const members = useMembers(project.id);
  return (
    <AuditLog
      title="Audit log"
      eyebrow={project.name}
      subtitle="Every recorded change in this project, with request details. Events cannot be edited or deleted."
      people={(members.data ?? []).map((m) => ({ value: m.user.id, label: m.user.display_name }))}
      projectId={project.id}
      csvPath={`/api/v1/projects/${project.id}/audit-events`}
    />
  );
}

function AuditLog({
  title,
  eyebrow,
  subtitle,
  people,
  projects,
  projectId,
  csvPath,
}: {
  title: string;
  eyebrow?: string;
  subtitle: string;
  people: FilterOption[];
  projects?: FilterOption[];
  projectId?: string;
  csvPath: string;
}) {
  const state = useAuditState(50);
  const project = filterValue(state.filters, "project");
  const query: OrgAuditQuery = { ...state.query, ...(project ? { project_id: project } : {}) };
  const events = useAuditEvents(query, projectId);
  const [open, setOpen] = useState<AuditEvent | null>(null);
  const filters = Object.fromEntries(
    Object.entries(query).filter(([k]) => k !== "page" && k !== "page_size"),
  ) as Record<string, string | undefined>;

  const columns: ColumnDef<AuditEvent>[] = [
    {
      id: "occurred_at",
      accessorKey: "occurred_at",
      header: "When",
      enableSorting: false,
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{formatDateTime(c.getValue() as string)}</span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44", fixed: true },
    },
    ...(projects
      ? [
          {
            id: "project",
            accessorFn: (e) => e.project_key ?? "",
            header: "Project",
            enableSorting: false,
            cell: (c) => (
              <span className="whitespace-nowrap font-mono text-[12.5px]">
                {(c.getValue() as string) || <span className="font-sans text-ink-muted">Organization</span>}
              </span>
            ),
            meta: { filter: { kind: "select", options: projects }, width: "w-32" },
          } satisfies ColumnDef<AuditEvent>,
        ]
      : []),
    {
      id: "actor",
      accessorFn: (e) => e.actor_display ?? "System",
      header: "By",
      enableSorting: false,
      cell: (c) => <span className="whitespace-nowrap">{c.getValue() as string}</span>,
      meta: { filter: { kind: "select", options: people }, width: "w-44" },
    },
    {
      id: "summary",
      accessorFn: (e) => e.summary ?? e.action,
      header: "Event",
      enableSorting: false,
      meta: { filter: { kind: "text", placeholder: "Search events" }, fixed: true },
    },
    {
      id: "entity_type",
      accessorKey: "entity_type",
      header: "Type",
      enableSorting: false,
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{typeLabel(c.getValue() as string)}</span>
      ),
      meta: { filter: { kind: "select", options: TYPES }, width: "w-40" },
    },
    {
      id: "action",
      accessorKey: "action",
      header: "Action",
      enableSorting: false,
      cell: (c) => (
        <span className="whitespace-nowrap font-mono text-[12px] text-ink-secondary">
          {c.getValue() as string}
        </span>
      ),
      meta: { width: "w-48" },
    },
  ];

  return (
    <Page
      title={title}
      {...(eyebrow ? { eyebrow } : {})}
      subtitle={subtitle}
      width="full"
      actions={
        <Button variant="secondary" size="sm" asChild>
          <a href={downloadUrl(csvPath, { ...filters, format: "csv" })} download>
            <Download aria-hidden="true" className="size-4" />
            Export CSV
          </a>
        </Button>
      }
    >
      <DataTable
        label="Audit events"
        columns={columns}
        data={events.data?.items ?? []}
        getRowId={(e) => e.id}
        loading={events.isPending}
        error={events.error}
        onRetry={() => void events.refetch()}
        noun={["event", "events"]}
        emptyText="No events match these filters."
        rowProps={(e) => ({
          tabIndex: 0,
          "aria-label": `Open event: ${e.summary ?? e.action}`,
          className: "cursor-pointer focus-visible:bg-accent-tint focus-visible:outline-none",
          onClick: () => {
            setOpen(e);
          },
          onKeyDown: (k) => {
            if (k.key === "Enter" && k.target === k.currentTarget) setOpen(e);
          },
        })}
        server={{
          total: events.data?.total ?? 0,
          pagination: state.pagination,
          onPaginationChange: state.setPagination,
          sorting: state.sorting,
          onSortingChange: state.setSorting,
          filters: state.filters,
          onFiltersChange: state.setFilters,
        }}
      />
      <EventDialog
        event={open}
        onClose={() => {
          setOpen(null);
        }}
      />
    </Page>
  );
}

const show = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
};

/** Event detail (docs/07 §5.13 "event detail drawer"): what changed, old → new, and the request. */
function EventDialog({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  const changes = Object.entries(event?.changes ?? {});
  const context = Object.entries(event?.context ?? {});
  return (
    <Dialog
      open={event !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={event?.summary ?? event?.action ?? "Event"}
      wide
    >
      {event ? (
        <div className="flex flex-col gap-5 text-[13px]">
          <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-1.5">
            <dt className="text-ink-secondary">When</dt>
            <dd>{formatDateTime(event.occurred_at)}</dd>
            <dt className="text-ink-secondary">By</dt>
            <dd>
              {event.actor_display ?? "System"}{" "}
              <span className="text-ink-muted">({event.actor_type.replaceAll("_", " ")})</span>
            </dd>
            <dt className="text-ink-secondary">Action</dt>
            <dd className="font-mono text-[12.5px]">{event.action}</dd>
            <dt className="text-ink-secondary">Record</dt>
            <dd>
              {typeLabel(event.entity_type)}
              {event.entity_key ? (
                <span className="ml-1.5 font-mono text-[12.5px]">{event.entity_key}</span>
              ) : null}
            </dd>
            <dt className="text-ink-secondary">Project</dt>
            <dd className="font-mono text-[12.5px]">
              {event.project_key ?? <span className="font-sans">Organization</span>}
            </dd>
          </dl>
          <section aria-label="Changes">
            <h3 className="mb-2 text-[13px] font-semibold text-ink">Changes</h3>
            {changes.length ? (
              <table aria-label="Changed fields" className="w-full">
                <thead>
                  <tr className="border-b border-border text-left text-ink-secondary">
                    <th scope="col" className="py-1.5 pr-3 font-medium">
                      Field
                    </th>
                    <th scope="col" className="py-1.5 pr-3 font-medium">
                      Before
                    </th>
                    <th scope="col" className="py-1.5 font-medium">
                      After
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map(([field, value]) => {
                    const pair = Array.isArray(value) && value.length === 2 ? value : [null, value];
                    return (
                      <tr key={field} className="border-b border-border align-top last:border-0">
                        <th scope="row" className="py-1.5 pr-3 text-left font-mono text-[12px] font-normal">
                          {field}
                        </th>
                        <td className="break-all py-1.5 pr-3 text-ink-secondary">{show(pair[0])}</td>
                        <td className="break-all py-1.5">{show(pair[1])}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="text-ink-secondary">No field changes are recorded for this event.</p>
            )}
          </section>
          <section aria-label="Request">
            <h3 className="mb-2 text-[13px] font-semibold text-ink">Request</h3>
            <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-1.5">
              {context.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-secondary">{k.replaceAll("_", " ")}</dt>
                  <dd className="break-all font-mono text-[12px]">{show(v)}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>
      ) : null}
    </Dialog>
  );
}
