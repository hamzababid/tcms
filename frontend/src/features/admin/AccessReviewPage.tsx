import type { ColumnDef } from "@tanstack/react-table";
import { Download } from "lucide-react";

import { DataTable } from "@/components/common/DataTable";
import { ErrorState, Page } from "@/components/common/feedback";
import { Tag } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/permissions";

import { useAccessReview, type AccessRow } from "./api";

const yesNo = (v: boolean) => (v ? "Yes" : "No");

/** US-163 / FR-AUD-004 (docs/07 §5.13): who has access to what, for periodic reviews. */
export function AccessReviewPage() {
  const review = useAccessReview();
  const columns: ColumnDef<AccessRow>[] = [
    {
      id: "name",
      accessorFn: (r) => `${r.name} ${r.email}`,
      header: "Person",
      cell: (c) => (
        <span className="flex flex-col">
          <span className="font-medium">
            {c.row.original.name}
            {c.row.original.active ? null : (
              <Tag tone="neutral" className="ml-2">
                Deactivated
              </Tag>
            )}
          </span>
          <span className="text-[12px] text-ink-secondary">{c.row.original.email}</span>
        </span>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      id: "scope",
      accessorFn: (r) => (r.project_key ? `${r.project_key} · ${r.project_name ?? ""}` : "Organization"),
      header: "Scope",
      cell: (c) =>
        c.row.original.project_key ? (
          <span>
            <span className="font-mono text-[12.5px] font-medium">{c.row.original.project_key}</span>{" "}
            <span className="text-ink-secondary">{c.row.original.project_name}</span>
          </span>
        ) : (
          <span className="text-ink-secondary">Organization</span>
        ),
      meta: { filter: { kind: "text", placeholder: "Project" } },
    },
    {
      id: "role",
      accessorFn: (r) => ROLE_LABELS[r.role_code] ?? r.role_name,
      header: "Role",
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "Org admin", label: "Org admin" },
            { value: "Member", label: "Member" },
            ...Object.values(ROLE_LABELS).map((l) => ({ value: l, label: l })),
          ],
        },
        width: "w-36",
      },
    },
    {
      id: "mfa",
      accessorFn: (r) => yesNo(r.mfa_enrolled),
      header: "Two-step",
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "Yes", label: "Yes" },
            { value: "No", label: "No" },
          ],
        },
        width: "w-28",
      },
    },
    {
      id: "granted_by",
      accessorFn: (r) => r.granted_by ?? "",
      header: "Granted by",
      cell: (c) => (c.getValue() as string) || <span className="text-ink-muted">Invitation or setup</span>,
      meta: { width: "w-44" },
    },
    {
      id: "granted_at",
      accessorKey: "granted_at",
      header: "Granted",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{formatDateTime(c.getValue() as string)}</span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "last_sign_in",
      accessorKey: "last_sign_in",
      header: "Last sign-in",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {c.getValue() ? formatDateTime(c.getValue() as string) : "Never"}
        </span>
      ),
      meta: { width: "w-44" },
    },
  ];
  return (
    <Page
      title="Access review"
      subtitle="One row per person and scope: their organization role, then each project. Exports are recorded in the audit log."
      width="full"
      actions={
        <>
          <Button variant="secondary" size="sm" asChild>
            <a href="/api/v1/organization/access-review?format=xlsx" download>
              <Download aria-hidden="true" className="size-4" />
              Export XLSX
            </a>
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <a href="/api/v1/organization/access-review?format=csv" download>
              <Download aria-hidden="true" className="size-4" />
              Export CSV
            </a>
          </Button>
        </>
      }
    >
      {review.isError ? (
        <ErrorState error={review.error} />
      ) : (
        <DataTable
          label="Access review"
          columns={columns}
          data={review.data ?? []}
          loading={review.isPending}
          getRowId={(r) => `${r.user_id}:${r.project_id ?? "org"}`}
          noun={["row", "rows"]}
        />
      )}
    </Page>
  );
}
