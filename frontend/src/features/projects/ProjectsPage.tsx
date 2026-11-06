import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Link, useNavigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api, ApiError } from "@/api/client";
import { keys, useMe, useProjects, type Project } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { Tag } from "@/components/common/Tag";
import { EmptyState, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/field";
import { FormError } from "@/features/auth/AuthCard";
import { formatDate, formatDateTime } from "@/lib/format";

const schema = z.object({
  key: z
    .string()
    .trim()
    .transform((v) => v.toUpperCase())
    .pipe(z.string().regex(/^[A-Z][A-Z0-9]{1,9}$/, "2–10 letters and digits, starting with a letter")),
  name: z.string().trim().min(1, "Enter a name").max(100),
  description: z.string().max(20000).optional(),
});
type Values = z.input<typeof schema>;

function CreateProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { key: "", name: "", description: "" },
  });
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      const { data } = await api.POST("/api/v1/projects", {
        body: { key: v.key, name: v.name, description: v.description || null },
      });
      await Promise.all([
        qc.invalidateQueries({ queryKey: keys.projects }),
        qc.invalidateQueries({ queryKey: keys.me }),
      ]);
      onOpenChange(false);
      if (data) await navigate({ to: "/p/$projectKey/settings", params: { projectKey: data.key } });
    } catch (e) {
      if (e instanceof ApiError && e.errors.length) {
        for (const fe of e.errors) form.setError(fe.field as keyof Values, { message: fe.message });
      } else setError(e instanceof ApiError ? (e.detail ?? e.code) : "Could not create the project");
    }
  });
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New project"
      description="You become the project's QA Manager. QA and Staging environments are created."
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button type="submit" form="create-project" disabled={form.formState.isSubmitting}>
            Create project
          </Button>
        </>
      }
    >
      <form id="create-project" className="flex flex-col gap-4" onSubmit={(e) => void onSubmit(e)} noValidate>
        <FormError message={error} />
        <Field
          label="Key"
          required
          hint="Used in keys like SPARK-TC-12. Cannot be changed."
          error={form.formState.errors.key?.message}
        >
          {(p) => <Input {...p} className="font-mono uppercase" maxLength={10} {...form.register("key")} />}
        </Field>
        <Field label="Name" required error={form.formState.errors.name?.message}>
          {(p) => <Input {...p} {...form.register("name")} />}
        </Field>
        <Field label="Description">{(p) => <Input {...p} {...form.register("description")} />}</Field>
      </form>
    </Dialog>
  );
}

const projectColumns: ColumnDef<Project>[] = [
  {
    accessorKey: "key",
    header: "Key",
    cell: (c) => (
      <Link
        to="/p/$projectKey"
        params={{ projectKey: c.row.original.key }}
        className="font-mono text-[13px] font-medium text-link hover:underline"
      >
        {c.row.original.key}
      </Link>
    ),
    meta: { filter: { kind: "text" }, width: "w-44", fixed: true },
  },
  {
    accessorKey: "name",
    header: "Name",
    cell: (c) => (
      <div className="min-w-0">
        <p className="truncate font-medium">{c.row.original.name}</p>
        {c.row.original.description ? (
          <p className="truncate text-xs text-ink-secondary">{c.row.original.description}</p>
        ) : null}
      </div>
    ),
    meta: { filter: { kind: "text" }, fixed: true },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: (c) =>
      c.row.original.status === "archived" ? (
        <Tag tone="neutral">Archived · read-only</Tag>
      ) : (
        <Tag>Active</Tag>
      ),
    meta: {
      filter: {
        kind: "select",
        options: [
          { value: "active", label: "Active" },
          { value: "archived", label: "Archived" },
        ],
      },
      width: "w-48",
    },
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: (c) => <span className="text-ink-secondary">{formatDate(c.row.original.created_at)}</span>,
    meta: { filter: { kind: "daterange" }, width: "w-44" },
  },
  {
    accessorKey: "updated_at",
    header: "Last changed",
    cell: (c) => <span className="text-ink-secondary">{formatDateTime(c.row.original.updated_at)}</span>,
    meta: { filter: { kind: "daterange" }, width: "w-44" },
  },
];

export function ProjectsPage() {
  const me = useMe().data;
  const projects = useProjects();
  const [open, setOpen] = useState(false);
  const canCreate = Boolean(me?.org_permissions.includes("project.create"));
  return (
    <Page
      title="Projects"
      subtitle="Projects you are a member of. Organization admins see every project."
      width="full"
      actions={
        canCreate ? (
          <Button
            size="sm"
            onClick={() => {
              setOpen(true);
            }}
          >
            <Plus aria-hidden="true" className="size-4" />
            New project
          </Button>
        ) : null
      }
    >
      {projects.isPending ? (
        <Skeleton />
      ) : projects.isError ? (
        <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
      ) : projects.data.length === 0 ? (
        <EmptyState
          text={
            canCreate
              ? "No projects yet."
              : "You are not a member of any project yet. Ask a QA Manager to add you."
          }
          action={
            canCreate ? (
              <Button
                onClick={() => {
                  setOpen(true);
                }}
              >
                Create a project
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DataTable
          label="Projects"
          columns={projectColumns}
          data={projects.data}
          getRowId={(p) => p.id}
          noun={["project", "projects"]}
          initialSorting={[{ id: "key", desc: false }]}
        />
      )}
      <CreateProjectDialog open={open} onOpenChange={setOpen} />
    </Page>
  );
}
