import { useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import { keys, useMe, useSessions, useTokens, type ApiToken, type SessionInfo } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { Tag } from "@/components/common/Tag";
import {
  Card,
  EmptyState,
  ErrorState,
  Facts,
  errorMessage,
  Page,
  Skeleton,
  useToast,
} from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { FormError } from "@/features/auth/AuthCard";
import { MfaEnrollment } from "@/features/auth/MfaEnrollment";
import { PASSWORD_HINT } from "@/features/auth/PasswordPages";

const dt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const fmt = (s: string | null | undefined) => (s ? dt.format(new Date(s)) : "—");

/** "Chrome on Windows" from a user agent (full string on hover). */
export function deviceName(ua: string | null | undefined): string {
  if (!ua) return "Unknown device";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Firefox\//.test(ua)
      ? "Firefox"
      : /Chrome\//.test(ua)
        ? "Chrome"
        : /Safari\//.test(ua)
          ? "Safari"
          : /python|curl|httpx|okhttp/i.test(ua)
            ? "API client"
            : "Browser";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS X|Macintosh/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return os ? `${browser} on ${os}` : browser;
}

function timeZones(): string[] {
  const supported = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf;
  return supported ? supported("timeZone") : ["UTC"];
}

function ProfileTab() {
  const me = useMe().data;
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(me?.user.display_name ?? "");
  const [tz, setTz] = useState(me?.time_zone ?? "UTC");
  const [pw, setPw] = useState({ current: "", next: "" });
  const [error, setError] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.PATCH("/api/v1/auth/me", { body: { display_name: name, time_zone: tz } });
      await qc.invalidateQueries({ queryKey: keys.me });
      toast("Profile saved");
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  async function changePassword(e: FormEvent) {
    e.preventDefault();
    setPwError(null);
    try {
      await api.POST("/api/v1/auth/password/change", {
        body: { current_password: pw.current, new_password: pw.next },
      });
      setPw({ current: "", next: "" });
      await qc.invalidateQueries({ queryKey: keys.sessions });
      toast("Password changed. Your other sessions were signed out.");
    } catch (err) {
      setPwError(errorMessage(err));
    }
  }
  return (
    <div className="grid gap-5 xl:grid-cols-3">
      <form onSubmit={(e) => void saveProfile(e)}>
        <Card
          title="Profile"
          description="How you appear to your colleagues."
          footer={<Button type="submit">Save profile</Button>}
          className="h-full"
        >
          <div className="flex flex-col gap-4">
            <FormError message={error} />
            <Field label="Name">
              {(p) => (
                <Input
                  {...p}
                  value={name}
                  maxLength={100}
                  onChange={(e) => {
                    setName(e.target.value);
                  }}
                />
              )}
            </Field>
            <Field label="Email" hint="Ask an administrator to change your email.">
              {(p) => <Input {...p} value={me?.user.email ?? ""} readOnly />}
            </Field>
            <Field label="Time zone" hint="Dates and times are shown in this zone.">
              {(p) => (
                <Select
                  {...p}
                  value={tz}
                  onChange={(e) => {
                    setTz(e.target.value);
                  }}
                >
                  {timeZones().map((z) => (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
        </Card>
      </form>
      <form onSubmit={(e) => void changePassword(e)}>
        <Card
          title="Password"
          description="Changing it signs out your other sessions."
          footer={
            <Button type="submit" disabled={!pw.current || !pw.next}>
              Change password
            </Button>
          }
          className="h-full"
        >
          <div className="flex flex-col gap-4">
            <FormError message={pwError} />
            <Field label="Current password">
              {(p) => (
                <Input
                  {...p}
                  type="password"
                  autoComplete="current-password"
                  value={pw.current}
                  onChange={(e) => {
                    setPw({ ...pw, current: e.target.value });
                  }}
                />
              )}
            </Field>
            <Field label="New password" hint={PASSWORD_HINT}>
              {(p) => (
                <Input
                  {...p}
                  type="password"
                  autoComplete="new-password"
                  value={pw.next}
                  onChange={(e) => {
                    setPw({ ...pw, next: e.target.value });
                  }}
                />
              )}
            </Field>
          </div>
        </Card>
      </form>
      <Card title="Account" className="h-full">
        {me ? (
          <Facts
            items={[
              ["Organization", me.organization.name],
              ["Email", me.user.email],
              ["Administrator", me.is_org_admin ? "Yes" : "No"],
              ["Projects", me.memberships.length],
              [
                "Two-step",
                me.mfa.enrolled ? (
                  <Tag>On</Tag>
                ) : (
                  <Tag tone="neutral">{me.mfa.required ? "Required, not set up" : "Off"}</Tag>
                ),
              ],
              ["Time zone", me.time_zone],
            ]}
          />
        ) : null}
      </Card>
    </div>
  );
}

function SessionsTab() {
  const sessions = useSessions();
  const qc = useQueryClient();
  const toast = useToast();
  const columns: ColumnDef<SessionInfo>[] = [
    {
      id: "device",
      accessorFn: (s) => deviceName(s.user_agent),
      header: "Device",
      cell: (c) => (
        <span
          className="block max-w-[420px] truncate font-medium"
          title={c.row.original.user_agent ?? undefined}
        >
          {c.getValue() as string}
        </span>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      id: "ip",
      accessorFn: (s) => s.ip ?? "—",
      header: "IP address",
      cell: (c) => <span className="font-mono text-[12.5px]">{c.getValue() as string}</span>,
      meta: { filter: { kind: "text" }, width: "w-40" },
    },
    {
      accessorKey: "created_at",
      header: "Signed in",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{fmt(c.getValue() as string)}</span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      accessorKey: "last_seen_at",
      header: "Last active",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{fmt(c.getValue() as string)}</span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      accessorKey: "expires_at",
      header: "Expires",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{fmt(c.getValue() as string)}</span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      cell: (c) =>
        c.row.original.current ? (
          <Tag>This session</Tag>
        ) : (
          <Button
            variant="ghost"
            size="xs"
            onClick={() =>
              void api
                .DELETE("/api/v1/me/sessions/{session_id}", {
                  params: { path: { session_id: c.row.original.id } },
                })
                .then(() => qc.invalidateQueries({ queryKey: keys.sessions }))
                .then(() => {
                  toast("Session signed out");
                })
            }
          >
            Sign out
          </Button>
        ),
      meta: { align: "right", width: "w-32", fixed: true, label: "Actions" },
    },
  ];
  if (sessions.isError) return <ErrorState error={sessions.error} />;
  return (
    <DataTable
      label="Active sessions"
      columns={columns}
      data={sessions.data ?? []}
      loading={sessions.isPending}
      getRowId={(s) => s.id}
      noun={["session", "sessions"]}
      initialSorting={[{ id: "last_seen_at", desc: true }]}
      toolbar={<p className="text-[13px] text-ink-secondary">Devices signed in to your account.</p>}
    />
  );
}

function TokensTab() {
  const me = useMe().data;
  const tokens = useTokens();
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({
    name: "",
    scope: "read" as "read" | "read_write",
    days: 90,
    project: "",
  });
  const [secret, setSecret] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.tokens });

  async function create(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const { data } = await api.POST("/api/v1/me/api-tokens", {
        body: {
          name: form.name,
          scope: form.scope,
          expires_in_days: form.days,
          project_id: form.project || null,
        },
      });
      setCreating(false);
      setSecret(data?.token ?? null);
      setForm({ ...form, name: "" });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const projectKey = (id: string | null) =>
    id ? (me?.memberships.find((m) => m.project.id === id)?.project.key ?? "—") : "All my projects";
  const statusOf = (tk: ApiToken) =>
    tk.revoked_at ? "revoked" : new Date(tk.expires_at) < new Date() ? "expired" : "active";
  const columns: ColumnDef<ApiToken>[] = [
    {
      accessorKey: "name",
      header: "Name",
      cell: (c) => (
        <span className="font-medium">
          {c.row.original.name}
          <span className="ml-2 font-mono text-xs text-ink-muted">{c.row.original.token_prefix}…</span>
        </span>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      accessorKey: "scope",
      header: "Scope",
      cell: (c) => (c.getValue() === "read" ? "Read only" : "Read and write"),
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "read", label: "Read only" },
            { value: "read_write", label: "Read and write" },
          ],
        },
        width: "w-40",
      },
    },
    {
      id: "project",
      accessorFn: (tk) => projectKey(tk.project_id),
      header: "Project",
      cell: (c) => <span className="font-mono text-[12.5px]">{c.getValue() as string}</span>,
      meta: { filter: { kind: "text" }, width: "w-40" },
    },
    {
      accessorKey: "expires_at",
      header: "Expires",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{fmt(c.getValue() as string)}</span>
      ),
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      accessorKey: "last_used_at",
      header: "Last used",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">{fmt(c.getValue() as string | null)}</span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "status",
      accessorFn: statusOf,
      header: "Status",
      cell: (c) =>
        c.getValue() === "active" ? (
          <Tag>Active</Tag>
        ) : (
          <Tag tone="neutral">{c.getValue() === "revoked" ? "Revoked" : "Expired"}</Tag>
        ),
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "active", label: "Active" },
            { value: "revoked", label: "Revoked" },
            { value: "expired", label: "Expired" },
          ],
        },
        width: "w-32",
      },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      cell: (c) =>
        c.row.original.revoked_at ? null : (
          <Button
            variant="ghost"
            size="xs"
            className="text-danger hover:bg-danger-surface hover:text-danger"
            onClick={() =>
              void api
                .DELETE("/api/v1/me/api-tokens/{token_id}", {
                  params: { path: { token_id: c.row.original.id } },
                })
                .then(refresh)
                .then(() => {
                  toast("Token revoked");
                })
            }
          >
            Revoke
          </Button>
        ),
      meta: { align: "right", width: "w-28", fixed: true, label: "Actions" },
    },
  ];
  return (
    <div>
      <Dialog
        open={creating}
        onOpenChange={setCreating}
        title="New API token"
        description="For scripts and CI. The token is shown once."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setCreating(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" form="token-form" disabled={!form.name.trim()}>
              Create token
            </Button>
          </>
        }
      >
        <form id="token-form" onSubmit={(e) => void create(e)}>
          <div className="flex flex-col gap-4">
            <FormError message={error} />
            <Field label="Token name">
              {(p) => (
                <Input
                  {...p}
                  value={form.name}
                  maxLength={100}
                  onChange={(e) => {
                    setForm({ ...form, name: e.target.value });
                  }}
                />
              )}
            </Field>
            <Field label="Scope">
              {(p) => (
                <Select
                  {...p}
                  value={form.scope}
                  onChange={(e) => {
                    setForm({ ...form, scope: e.target.value as "read" | "read_write" });
                  }}
                >
                  <option value="read">Read only</option>
                  <option value="read_write">Read and write</option>
                </Select>
              )}
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Expires (days)">
                {(p) => (
                  <Input
                    {...p}
                    type="number"
                    min={1}
                    max={365}
                    value={form.days}
                    onChange={(e) => {
                      setForm({ ...form, days: Number(e.target.value) });
                    }}
                  />
                )}
              </Field>
              <Field label="Project">
                {(p) => (
                  <Select
                    {...p}
                    value={form.project}
                    onChange={(e) => {
                      setForm({ ...form, project: e.target.value });
                    }}
                  >
                    <option value="">All my projects</option>
                    {(me?.memberships ?? []).map((m) => (
                      <option key={m.project.id} value={m.project.id}>
                        {m.project.key}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            </div>
          </div>
        </form>
      </Dialog>
      <Dialog
        open={secret !== null}
        onOpenChange={(o) => {
          if (!o) setSecret(null);
        }}
        title="Copy your token now"
        description="It is shown only once."
      >
        <p
          className="break-all rounded-control bg-ground p-3 font-mono text-[13px]"
          aria-label="New API token"
        >
          {secret}
        </p>
        <Button
          className="mt-4"
          variant="secondary"
          onClick={() =>
            void navigator.clipboard.writeText(secret ?? "").then(() => {
              toast("Copied");
            })
          }
        >
          Copy
        </Button>
      </Dialog>
      {tokens.isError ? (
        <ErrorState error={tokens.error} />
      ) : (
        <DataTable
          label="API tokens"
          columns={columns}
          data={tokens.data ?? []}
          loading={tokens.isPending}
          getRowId={(tk) => tk.id}
          noun={["token", "tokens"]}
          emptyText="No tokens match these filters."
          toolbar={
            <Button
              size="sm"
              onClick={() => {
                setCreating(true);
              }}
            >
              <Plus aria-hidden="true" className="size-4" />
              New token
            </Button>
          }
          empty={<EmptyState text="No API tokens yet. Create one for scripts or CI." />}
        />
      )}
    </div>
  );
}

function SecurityTab() {
  const me = useMe().data;
  const qc = useQueryClient();
  const toast = useToast();
  const [enrolling, setEnrolling] = useState(false);
  const [form, setForm] = useState({ password: "", code: "" });
  const [codes, setCodes] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!me) return <Skeleton />;
  if (!me.mfa.enrolled) {
    return (
      <div className="grid gap-5 xl:grid-cols-2">
        <Card
          title="Two-step verification is off"
          description="Add an authenticator app (Google Authenticator, 1Password, Authy…) to protect your account."
          footer={
            enrolling ? undefined : (
              <Button
                onClick={() => {
                  setEnrolling(true);
                }}
              >
                Set up two-step verification
              </Button>
            )
          }
        >
          {enrolling ? (
            <div className="max-w-sm">
              <MfaEnrollment
                onDone={() => {
                  setEnrolling(false);
                  void qc.invalidateQueries({ queryKey: keys.me });
                  toast("Two-step verification enabled");
                }}
              />
            </div>
          ) : (
            <p className="text-[13px] text-ink-secondary">
              After setup, signing in asks for a 6-digit code from your app. You also get recovery codes for
              when the app is not available.
            </p>
          )}
        </Card>
      </div>
    );
  }
  return (
    <div className="grid gap-5 xl:grid-cols-3">
      <Card title="Status" className="h-full">
        <Facts
          items={[
            ["Two-step", <Tag key="on">On</Tag>],
            ["Required", me.mfa.required ? "Yes, by your organization" : "No"],
          ]}
        />
      </Card>
      <Card
        title="Recovery codes"
        description="Single-use codes for when your authenticator is not available. New codes replace the old ones."
        className="h-full"
        footer={
          <Button
            variant="secondary"
            disabled={!form.password}
            onClick={() =>
              void api
                .POST("/api/v1/auth/mfa/recovery-codes", { body: { password: form.password } })
                .then(({ data }) => {
                  setCodes(data?.recovery_codes ?? []);
                })
                .catch((e: unknown) => {
                  setError(errorMessage(e));
                })
            }
          >
            New recovery codes
          </Button>
        }
      >
        <div className="flex flex-col gap-4">
          <FormError message={error} />
          <Field label="Password" hint="Required to create codes or turn verification off.">
            {(p) => (
              <Input
                {...p}
                type="password"
                value={form.password}
                onChange={(e) => {
                  setForm({ ...form, password: e.target.value });
                }}
              />
            )}
          </Field>
          {codes ? (
            <ul
              aria-label="Recovery codes"
              className="grid grid-cols-2 gap-2 rounded-control border border-border bg-ground p-3 font-mono text-[13px]"
            >
              {codes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </Card>
      {!me.mfa.required ? (
        <Card
          tone="danger"
          title="Turn off"
          description="Your account will be protected by the password only."
          className="h-full"
          footer={
            <Button
              variant="destructive"
              disabled={!form.password || form.code.length !== 6}
              onClick={() =>
                void api
                  .POST("/api/v1/auth/mfa/disable", { body: { password: form.password, code: form.code } })
                  .then(() => qc.invalidateQueries({ queryKey: keys.me }))
                  .then(() => {
                    toast("Two-step verification turned off");
                  })
                  .catch((e: unknown) => {
                    setError(errorMessage(e));
                  })
              }
            >
              Turn off two-step verification
            </Button>
          }
        >
          <Field label="Authenticator code" hint="Enter your password in Recovery codes as well.">
            {(p) => (
              <Input
                {...p}
                inputMode="numeric"
                maxLength={6}
                className="font-mono tracking-[0.3em]"
                value={form.code}
                onChange={(e) => {
                  setForm({ ...form, code: e.target.value.replace(/\D/g, "") });
                }}
              />
            )}
          </Field>
        </Card>
      ) : null}
    </div>
  );
}

export function ProfilePage({ tab, onTab }: { tab: string; onTab: (t: string) => void }) {
  return (
    <Page
      title="Your account"
      subtitle="Profile, password, sessions, API tokens and two-step verification."
      width="full"
    >
      <Tabs
        contentClassName="pt-5"
        label="Account"
        value={tab}
        onValueChange={onTab}
        items={[
          { value: "profile", label: "Profile", content: <ProfileTab /> },
          { value: "sessions", label: "Sessions", content: <SessionsTab /> },
          { value: "tokens", label: "API tokens", content: <TokensTab /> },
          { value: "security", label: "Two-step verification", content: <SecurityTab /> },
        ]}
      />
    </Page>
  );
}
