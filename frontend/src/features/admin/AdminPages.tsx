import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "@/api/client";
import { keys, useInvitations, useOrganization, useProjects, type Organization } from "@/api/queries";
import { EmptyState, ErrorState, errorMessage, Page, Skeleton, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select } from "@/components/ui/field";
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
      setLink(data?.accept_url ?? null);
      setForm({ ...form, email: "" });
      await qc.invalidateQueries({ queryKey: keys.invitations });
    } catch (err) {
      setError(
        err instanceof ApiError ? (err.errors[0]?.message ?? err.detail ?? err.code) : errorMessage(err),
      );
    }
  }

  return (
    <Page title="Invitations" subtitle="Invitations expire after 7 days and can be used once.">
      <form className="mb-8 flex flex-wrap items-end gap-3" onSubmit={(e) => void invite(e)}>
        <div className="w-full">
          <FormError message={error} />
        </div>
        <div className="w-64">
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
        </div>
        <div className="w-48">
          <Field label="Project (optional)">
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
        </div>
        {form.project ? (
          <div className="w-44">
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
          </div>
        ) : null}
        <div className="pb-2">
          <Checkbox
            label="Organization administrator"
            checked={form.admin}
            onChange={(e) => {
              setForm({ ...form, admin: e.target.checked });
            }}
          />
        </div>
        <Button type="submit" disabled={!form.email}>
          Send invitation
        </Button>
      </form>
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
      <h2 className="mb-3 text-base font-semibold text-ink">Pending</h2>
      {invitations.isPending ? (
        <Skeleton />
      ) : invitations.isError ? (
        <ErrorState error={invitations.error} />
      ) : invitations.data.length === 0 ? (
        <EmptyState text="No pending invitations." />
      ) : (
        <ul className="data-list">
          {invitations.data.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div>
                <p className="text-ink">
                  {i.email}
                  {i.is_org_admin ? (
                    <span className="ml-2 text-xs font-medium text-accent-ink">org admin</span>
                  ) : null}
                </p>
                <p className="text-xs text-ink-muted">
                  {i.role_code ? `${ROLE_LABELS[i.role_code] ?? i.role_code} · ` : ""}
                  invited by {i.invited_by?.display_name ?? "setup"} ·{" "}
                  {i.expired ? "expired" : `expires ${dt.format(new Date(i.expires_at))}`}
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  void api
                    .DELETE("/api/v1/organization/invitations/{invitation_id}", {
                      params: { path: { invitation_id: i.id } },
                    })
                    .then(() => qc.invalidateQueries({ queryKey: keys.invitations }))
                    .then(() => {
                      toast("Invitation revoked");
                    })
                }
              >
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
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
    <Page title="Security policy" subtitle={org.name} width="3xl">
      <form className="flex flex-col gap-5" onSubmit={(e) => void save(e)}>
        <FormError message={error} />
        <Checkbox
          label="Require two-step verification for everyone (always required for administrators)"
          checked={values.mfa_required_for_all}
          onChange={(e) => {
            setValues({ ...values, mfa_required_for_all: e.target.checked });
          }}
        />
        <Checkbox
          label="QA Managers may create projects"
          checked={values.qa_managers_can_create_projects}
          onChange={(e) => {
            setValues({ ...values, qa_managers_can_create_projects: e.target.checked });
          }}
        />
        <div className="grid gap-4 md:grid-cols-2">
          {num("session_idle_minutes", "Idle timeout (minutes)", "15–480")}
          {num("session_absolute_hours", "Session lifetime (hours)", "1–24")}
          {num("default_attachment_max_mb", "Attachment limit (MB)", "1–100; default and cap for projects")}
          {num("audit_retention_years", "Audit retention (years)", "1–10")}
        </div>
        <div>
          <Button type="submit">Save policy</Button>
        </div>
      </form>
    </Page>
  );
}
