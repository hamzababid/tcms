import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api, ApiError } from "@/api/client";
import { keys, useMe, useProjects } from "@/api/queries";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/field";
import { FormError } from "@/features/auth/AuthCard";

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

export function ProjectsPage() {
  const me = useMe().data;
  const projects = useProjects();
  const [open, setOpen] = useState(false);
  const canCreate = Boolean(me?.org_permissions.includes("project.create"));
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Projects"
        actions={
          canCreate ? (
            <Button
              onClick={() => {
                setOpen(true);
              }}
            >
              New project
            </Button>
          ) : null
        }
      />
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
        <table className="w-full overflow-hidden rounded-card border border-border bg-surface text-[13px]">
          <thead className="bg-ground text-left text-xs font-medium text-ink-secondary">
            <tr className="h-9">
              <th scope="col" className="px-4">
                Key
              </th>
              <th scope="col" className="px-4">
                Name
              </th>
              <th scope="col" className="px-4">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {projects.data.map((p) => (
              <tr key={p.id} className="h-10 border-t border-border hover:bg-ground">
                <td className="px-4 font-mono text-xs">
                  <Link
                    to="/p/$projectKey/activity"
                    params={{ projectKey: p.key }}
                    className="text-accent hover:underline"
                  >
                    {p.key}
                  </Link>
                </td>
                <td className="px-4 text-ink">{p.name}</td>
                <td className="px-4 text-ink-secondary">
                  {p.status === "archived" ? "Archived (read-only)" : "Active"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <CreateProjectDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
