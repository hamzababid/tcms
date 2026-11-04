import { useState } from "react";

import { useActivity, type Project } from "@/api/queries";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";

const TYPES: [string, string][] = [
  ["", "All activity"],
  ["project", "Project"],
  ["membership", "Members"],
  ["environment", "Environments"],
  ["release", "Releases"],
];

const timeFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** US-028 / FR-WS-007: audit events rendered as sentences, filterable by entity type. */
export function ActivityPage({ project }: { project: Project }) {
  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState("");
  const activity = useActivity(project.id, page, entityType || null);
  const pages = activity.data ? Math.max(1, Math.ceil(activity.data.total / activity.data.page_size)) : 1;
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title={`${project.name} · Activity`}
        subtitle={project.status === "archived" ? "This project is archived and read-only." : undefined}
      />
      <div className="mb-4 w-56">
        <Field label="Show">
          {(p) => (
            <Select
              {...p}
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value);
                setPage(1);
              }}
            >
              {TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {activity.isPending ? (
        <Skeleton rows={6} />
      ) : activity.isError ? (
        <ErrorState error={activity.error} onRetry={() => void activity.refetch()} />
      ) : activity.data.items.length === 0 ? (
        <EmptyState text="No activity yet." />
      ) : (
        <>
          <ol className="divide-y divide-border rounded-card border border-border bg-surface">
            {activity.data.items.map((e) => (
              <li key={e.id} className="flex items-baseline justify-between gap-4 px-4 py-3 text-sm">
                <span className="text-ink">{e.summary ?? e.action}</span>
                <time dateTime={e.occurred_at} className="shrink-0 text-xs text-ink-muted">
                  {timeFormat.format(new Date(e.occurred_at))}
                </time>
              </li>
            ))}
          </ol>
          {pages > 1 ? (
            <div className="mt-4 flex items-center justify-end gap-2 text-sm">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => {
                  setPage((p) => p - 1);
                }}
              >
                Previous
              </Button>
              <span className="text-ink-secondary">
                Page {page} of {pages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= pages}
                onClick={() => {
                  setPage((p) => p + 1);
                }}
              >
                Next
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
