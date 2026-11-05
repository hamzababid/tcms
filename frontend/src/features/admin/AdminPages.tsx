import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "@/api/client";
import {
  keys,
  useInvitations,
  useOrganization,
  useProjects,
  type Invitation,
  type Organization,
} from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { Tag } from "@/components/common/Tag";
import {
  Card,
  EmptyState,
  ErrorState,
  errorMessage,
  Page,
  Skeleton,
  useToast,
} from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, ToggleField } from "@/components/ui/field";
import { FormError } from "@/features/auth/AuthCard";
import { ROLE_LABELS } from "@/lib/permissions";

const ROLES = ["viewer", "qa_engineer", "qa_lead", "qa_manager", "developer", "pm_ba"] as const;
type Role = (typeof ROLES)[number];
const dt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

/** US-015 (review Q4): invite people; the accept link is shown once for copy-link fallback. */
export function InvitationsPage() {
  const invitations = useInvitations();
  const projects = useProjects();
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ email: "", project: "", role: "viewer" as Role, admin: false });
  const [link, setLink] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function invite(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const { data } = await api.POST("/api/v1/organization/invitations", {
        body: {
          email: form.email,
          is_org_admin: form.admin,
          project_id: form.project || null,
          role_code: form.project ? form.role : null,
        },
      });
      setInviting(false);
      setLink(data?.accept_url ?? null);
      setForm({ ...form, email: "" });
      await qc.invalidateQueries({ queryKey: keys.invitations });
    } catch (err) {
      setError(
        err instanceof ApiError ? (err.errors[0]?.message ?? err.detail ?? err.code) : errorMessage(err),
      );
    }
  }

  const projectName = (id: string | null) =>
    id ? (projects.data?.find((x) => x.id === id)?.key ?? "—") : "—";
  const columns: ColumnDef<Invitation>[] = [
    {
      accessorKey: "email",
      header: "Email",
      cell: (c) => (
        <span className="font-medium">
          {c.row.original.email}
          {c.row.original.is_org_admin ? <Tag className="ml-2">Org admin</Tag> : null}
        </span>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      id: "project",
      accessorFn: (i) => projectName(i.project_id),
      header: "Project",
      cell: (c) => <span className="font-mono text-[12.5px]">{c.getValue() as string}</span>,
      meta: { filter: { kind: "text" }, width: "w-32" },
    },
    {
      id: "role",
      accessorFn: (i) => i.role_code ?? "",
      header: "Role",
      cell: (c) =>
        c.row.original.role_code ? (ROLE_LABELS[c.row.original.role_code] ?? c.row.original.role_code) : "—",
      meta: {
        filter: { kind: "select", options: ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] ?? r })) },
        width: "w-40",
      },
    },
    {
      id: "invited_by",
      accessorFn: (i) => i.invited_by?.display_name ?? "Setup",
      header: "Invited by",
      meta: { filter: { kind: "text" }, width: "w-40" },
    },
    {
      accessorKey: "created_at",
      header: "Sent",
      cell: (c) => <span className="text-ink-secondary">{dt.format(new Date(c.getValue() as string))}</span>,
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      id: "status",
      accessorFn: (i) => (i.expired ? "expired" : "pending"),
      header: "Status",
      cell: (c) =>
        c.row.original.expired ? (
          <Tag tone="neutral">Expired</Tag>
        ) : (
          <span className="whitespace-nowrap text-ink-secondary">
            Expires {dt.format(new Date(c.row.original.expires_at))}
          </span>
        ),
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "pending", label: "Pending" },
            { value: "expired", label: "Expired" },
          ],
        },
        width: "w-44",
      },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      cell: (c) => (
        <Button
          variant="ghost"
          size="xs"
          className="text-danger hover:bg-danger-surface hover:text-danger"
          onClick={() =>
            void api
              .DELETE("/api/v1/organization/invitations/{invitation_id}", {
                params: { path: { invitation_id: c.row.original.id } },
              })
              .then(() => qc.invalidateQueries({ queryKey: keys.invitations }))
              .then(() => {
                toast("Invitation revoked");
              })
          }
        >
          Revoke
        </Button>
      ),
      meta: { align: "right", width: "w-24", fixed: true, label: "Actions" },
    },
  ];

  return (
    <Page
      title="Invitations"
      subtitle="Invite people to the organization. Invitations expire after 7 days and can be used once."
      width="full"
    >
      {invitations.isError ? (
        <ErrorState error={invitations.error} />
      ) : (
        <DataTable
          label="Pending invitations"
          columns={columns}
          data={invitations.data ?? []}
          loading={invitations.isPending}
          getRowId={(i) => i.id}
          noun={["invitation", "invitations"]}
          initialSorting={[{ id: "created_at", desc: true }]}
          toolbar={
            <>
              <h2 className="text-[15px] font-semibold text-ink">Pending invitations</h2>
              <Button
                size="sm"
                className="ml-2"
                onClick={() => {
                  setInviting(true);
                }}
              >
                <UserPlus aria-hidden="true" className="size-4" />
                Invite someone
              </Button>
            </>
          }
          empty={<EmptyState text="No pending invitations." />}
        />
      )}
      <Dialog
        open={inviting}
        onOpenChange={setInviting}
        title="Invite someone"
        description="They get an email with a link to set their name and password."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setInviting(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" form="invite-form" disabled={!form.email}>
              Send invitation
            </Button>
          </>
        }
      >
        <form id="invite-form" onSubmit={(e) => void invite(e)}>
          <div className="flex flex-col gap-4">
            <FormError message={error} />
            <Field label="Email" required>
              {(p) => (
                <Input
                  {...p}
                  type="email"
                  value={form.email}
                  onChange={(e) => {
                    setForm({ ...form, email: e.target.value });
                  }}
                />
              )}
            </Field>
            <Field label="Project (optional)" hint="Adds them to this project when they accept.">
              {(p) => (
                <Select
                  {...p}
                  value={form.project}
                  onChange={(e) => {
                    setForm({ ...form, project: e.target.value });
                  }}
                >
                  <option value="">No project</option>
                  {(projects.data ?? [])
                    .filter((x) => x.status === "active")
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.key} · {x.name}
                      </option>
                    ))}
                </Select>
              )}
            </Field>
            {form.project ? (
              <Field label="Role">
                {(p) => (
                  <Select
                    {...p}
                    value={form.role}
                    onChange={(e) => {
                      setForm({ ...form, role: e.target.value as Role });
                    }}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABELS[r]}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            ) : null}
            <ToggleField
              label="Organization administrator"
              description="Manages users, security policy and every project."
              checked={form.admin}
              onChange={(e) => {
                setForm({ ...form, admin: e.target.checked });
              }}
            />
          </div>
        </form>
      </Dialog>
      <Dialog
        open={link !== null}
        onOpenChange={(o) => {
          if (!o) setLink(null);
        }}
        title="Invitation sent"
        description="An email is on its way. You can also copy the link now; it is not shown again."
      >
        <p className="break-all rounded-control bg-ground p-3 font-mono text-xs" aria-label="Invitation link">
          {link}
        </p>
        <Button
          className="mt-4"
          variant="secondary"
          onClick={() =>
            void navigator.clipboard.writeText(link ?? "").then(() => {
              toast("Link copied");
            })
          }
        >
          Copy link
        </Button>
      </Dialog>
    </Page>
  );
}

/** US-021: security policy and organization limits (docs/02 §4.1). */
export function SecurityPage() {
  const org = useOrganization();
  if (org.isPending) return <Skeleton />;
  if (org.isError) return <ErrorState error={org.error} />;
  if (!org.data.settings)
    return <EmptyState text="Only organization administrators can change the security policy." />;
  return <SecurityForm key={org.data.row_version} org={org.data} settings={org.data.settings} />;
}

function SecurityForm({
  org,
  settings,
}: {
  org: Organization;
  settings: NonNullable<Organization["settings"]>;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [values, setValues] = useState(settings);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    setError(null);
    try {
      await api.PATCH("/api/v1/organization", { body: { settings: values, row_version: org.row_version } });
      await qc.invalidateQueries({ queryKey: keys.organization });
      toast("Security policy saved");
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale_row_version") {
        setError("The policy was changed by someone else. Reloaded the latest values.");
        await qc.invalidateQueries({ queryKey: keys.organization });
      } else if (err instanceof ApiError)
        setErrors(Object.fromEntries(err.errors.map((x) => [x.field, x.message])));
    }
  }
  const num = (
    k:
      | "session_idle_minutes"
      | "session_absolute_hours"
      | "default_attachment_max_mb"
      | "audit_retention_years",
    label: string,
    hint: string,
  ) => (
    <Field label={label} hint={hint} error={errors[`settings.${k}`]}>
      {(p) => (
        <Input
          {...p}
          type="number"
          value={values[k]}
          onChange={(e) => {
            setValues({ ...values, [k]: Number(e.target.value) });
          }}
        />
      )}
    </Field>
  );
  return (
    <Page title="Security policy" subtitle={`Sign-in, session and data rules for ${org.name}.`} width="full">
      <form className="flex flex-col gap-5" onSubmit={(e) => void save(e)}>
        <FormError message={error} />
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="Sign-in" description="Two-step verification and who may create projects.">
            <div className="flex flex-col gap-4">
              <ToggleField
                label="Require two-step verification for everyone"
                description="Always required for organization administrators. Users without it are asked to set it up at their next sign-in."
                checked={values.mfa_required_for_all}
                onChange={(e) => {
                  setValues({ ...values, mfa_required_for_all: e.target.checked });
                }}
              />
              <ToggleField
                label="QA Managers may create projects"
                description="When off, only organization administrators create projects."
                checked={values.qa_managers_can_create_projects}
                onChange={(e) => {
                  setValues({ ...values, qa_managers_can_create_projects: e.target.checked });
                }}
              />
            </div>
          </Card>
          <Card title="Sessions" description="How long people stay signed in.">
            <div className="grid gap-4 md:grid-cols-2">
              {num("session_idle_minutes", "Idle timeout (minutes)", "15–480")}
              {num("session_absolute_hours", "Session lifetime (hours)", "1–24")}
            </div>
          </Card>
          <Card
            title="Attachments"
            description="Default size limit for new projects and the cap for all projects."
          >
            {num("default_attachment_max_mb", "Attachment limit (MB)", "1–100")}
          </Card>
          <Card title="Audit" description="How long audit events are kept.">
            {num("audit_retention_years", "Audit retention (years)", "1–10")}
          </Card>
        </div>
        <div className="flex justify-end">
          <Button type="submit">Save policy</Button>
        </div>
      </form>
    </Page>
  );
}
