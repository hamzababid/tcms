import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import { keys, useMe, useSessions, useTokens } from "@/api/queries";
import {
  EmptyState,
  ErrorState,
  errorMessage,
  PageHeader,
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
    <div className="grid max-w-3xl gap-10 md:grid-cols-2">
      <form className="flex flex-col gap-4" onSubmit={(e) => void saveProfile(e)}>
        <h2 className="text-base font-semibold">Profile</h2>
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
        <Field label="Time zone">
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
        <div>
          <Button type="submit">Save profile</Button>
        </div>
      </form>
      <form className="flex flex-col gap-4" onSubmit={(e) => void changePassword(e)}>
        <h2 className="text-base font-semibold">Password</h2>
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
        <div>
          <Button type="submit" disabled={!pw.current || !pw.next}>
            Change password
          </Button>
        </div>
      </form>
    </div>
  );
}

function SessionsTab() {
  const sessions = useSessions();
  const qc = useQueryClient();
  const toast = useToast();
  if (sessions.isPending) return <Skeleton />;
  if (sessions.isError) return <ErrorState error={sessions.error} />;
  return (
    <ul className="max-w-3xl divide-y divide-border rounded-card border border-border bg-surface">
      {sessions.data.map((s) => (
        <li key={s.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
          <div>
            <p className="text-ink">
              {s.user_agent ?? "Unknown device"}{" "}
              {s.current ? <span className="ml-1 text-xs font-medium text-accent">this session</span> : null}
            </p>
            <p className="text-xs text-ink-muted">
              {s.ip ?? "—"} · signed in {fmt(s.created_at)} · last active {fmt(s.last_seen_at)}
            </p>
          </div>
          {!s.current ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                void api
                  .DELETE("/api/v1/me/sessions/{session_id}", { params: { path: { session_id: s.id } } })
                  .then(() => qc.invalidateQueries({ queryKey: keys.sessions }))
                  .then(() => {
                    toast("Session signed out");
                  })
              }
            >
              Sign out
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
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
      setSecret(data?.token ?? null);
      setForm({ ...form, name: "" });
      await refresh();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => void create(e)}>
        <FormError message={error} />
        <div className="w-56">
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
        </div>
        <div className="w-40">
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
        </div>
        <div className="w-28">
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
        </div>
        <div className="w-48">
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
        <Button type="submit" disabled={!form.name.trim()}>
          Create token
        </Button>
      </form>
      <Dialog
        open={secret !== null}
        onOpenChange={(o) => {
          if (!o) setSecret(null);
        }}
        title="Copy your token now"
        description="It is shown only once."
      >
        <p className="break-all rounded-control bg-ground p-3 font-mono text-sm" aria-label="New API token">
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
      {tokens.isPending ? (
        <Skeleton />
      ) : tokens.isError ? (
        <ErrorState error={tokens.error} />
      ) : tokens.data.length === 0 ? (
        <EmptyState text="No API tokens." />
      ) : (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {tokens.data.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
              <div>
                <p className="text-ink">
                  {t.name} <span className="ml-2 font-mono text-xs text-ink-muted">{t.token_prefix}…</span>
                </p>
                <p className="text-xs text-ink-muted">
                  {t.scope === "read" ? "Read only" : "Read and write"} · expires {fmt(t.expires_at)} · last
                  used {fmt(t.last_used_at)}
                  {t.revoked_at ? ` · revoked ${fmt(t.revoked_at)}` : ""}
                </p>
              </div>
              {!t.revoked_at ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    void api
                      .DELETE("/api/v1/me/api-tokens/{token_id}", { params: { path: { token_id: t.id } } })
                      .then(refresh)
                      .then(() => {
                        toast("Token revoked");
                      })
                  }
                >
                  Revoke
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
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
    return enrolling ? (
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
      <div className="flex max-w-xl flex-col gap-3 text-sm">
        <p>Two-step verification is off. Add an authenticator app to protect your account.</p>
        <div>
          <Button
            onClick={() => {
              setEnrolling(true);
            }}
          >
            Set up two-step verification
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex max-w-xl flex-col gap-4 text-sm">
      <p>
        Two-step verification is on.
        {me.mfa.required ? " It is required for your account." : ""}
      </p>
      <FormError message={error} />
      <Field label="Password">
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
      <div className="flex gap-2">
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
      </div>
      {codes ? (
        <ul
          aria-label="Recovery codes"
          className="grid grid-cols-2 gap-2 rounded-control border border-border bg-ground p-3 font-mono"
        >
          {codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      ) : null}
      {!me.mfa.required ? (
        <>
          <Field label="Authenticator code (to turn off)">
            {(p) => (
              <Input
                {...p}
                inputMode="numeric"
                maxLength={6}
                value={form.code}
                onChange={(e) => {
                  setForm({ ...form, code: e.target.value.replace(/\D/g, "") });
                }}
              />
            )}
          </Field>
          <div>
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
          </div>
        </>
      ) : null}
    </div>
  );
}

export function ProfilePage({ tab, onTab }: { tab: string; onTab: (t: string) => void }) {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Your account" />
      <Tabs
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
    </div>
  );
}
