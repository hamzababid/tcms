import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";

import { api, ApiError } from "@/api/client";
import {
  keys,
  useEnvironments,
  useMe,
  useMembers,
  useReleases,
  type Environment,
  type Project,
  type Release,
} from "@/api/queries";
import { EmptyState, ErrorState, errorMessage, Page, Skeleton, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input, Select } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { FormError } from "@/features/auth/AuthCard";
import { can, projectPermissions, ROLE_LABELS } from "@/lib/permissions";

const ROLE_CODES = ["qa_manager", "qa_lead", "qa_engineer", "developer", "pm_ba", "viewer"] as const;
type RoleCode = (typeof ROLE_CODES)[number];

const th = "";
const td = "";

function useInvalidateProject(projectId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.project(projectId) });
}

/** Stale row_version → "changed by someone else" with Reload (docs/02 §2.4, docs/07 §4.4). */
function StaleNotice({ onReload }: { onReload: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between rounded-control border border-border bg-ground px-3 py-2 text-sm"
    >
      <span>This item was changed by someone else.</span>
      <Button size="sm" variant="secondary" onClick={onReload}>
        Reload
      </Button>
    </div>
  );
}

// -- General --------------------------------------------------------------------------------------

function General({ project, editable }: { project: Project; editable: boolean }) {
  const toast = useToast();
  const invalidate = useInvalidateProject(project.id);
  const qc = useQueryClient();
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.PATCH("/api/v1/projects/{project_id}", {
        params: { path: { project_id: project.id } },
        body: { name, description: description || null, row_version: project.row_version },
      });
      await Promise.all([invalidate(), qc.invalidateQueries({ queryKey: keys.projects })]);
      toast("Project saved");
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale_row_version") setStale(true);
      else setError(errorMessage(err));
    }
  }
  return (
    <form className="flex max-w-xl flex-col gap-4" onSubmit={(e) => void save(e)}>
      {stale ? (
        <StaleNotice
          onReload={() =>
            void invalidate().then(() => {
              setStale(false);
            })
          }
        />
      ) : null}
      <FormError message={error} />
      <Field label="Key" hint="The project key never changes (BR-27).">
        {(p) => <Input {...p} value={project.key} readOnly className="font-mono" />}
      </Field>
      <Field label="Name" required>
        {(p) => (
          <Input
            {...p}
            value={name}
            disabled={!editable}
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
        )}
      </Field>
      <Field label="Description">
        {(p) => (
          <Input
            {...p}
            value={description}
            disabled={!editable}
            onChange={(e) => {
              setDescription(e.target.value);
            }}
          />
        )}
      </Field>
      {editable ? (
        <div>
          <Button type="submit">Save</Button>
        </div>
      ) : null}
    </form>
  );
}

// -- Options --------------------------------------------------------------------------------------

function Options({ project, editable }: { project: Project; editable: boolean }) {
  const toast = useToast();
  const invalidate = useInvalidateProject(project.id);
  const [settings, setSettings] = useState(project.settings);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [stale, setStale] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    try {
      await api.PATCH("/api/v1/projects/{project_id}", {
        params: { path: { project_id: project.id } },
        body: { settings, row_version: project.row_version },
      });
      await invalidate();
      toast("Options saved");
    } catch (err) {
      if (err instanceof ApiError && err.code === "stale_row_version") setStale(true);
      else if (err instanceof ApiError)
        setErrors(Object.fromEntries(err.errors.map((x) => [x.field, x.message])));
    }
  }
  const flag = (
    k: "approval_required" | "allow_self_approval" | "only_assignee_executes" | "require_defect_for_failure",
    label: string,
  ) => (
    <Checkbox
      label={label}
      checked={settings[k]}
      disabled={!editable}
      onChange={(e) => {
        setSettings({ ...settings, [k]: e.target.checked });
      }}
    />
  );
  return (
    <form className="flex max-w-xl flex-col gap-4" onSubmit={(e) => void save(e)}>
      {stale ? (
        <StaleNotice
          onReload={() =>
            void invalidate().then(() => {
              setStale(false);
            })
          }
        />
      ) : null}
      {flag("approval_required", "Test cases need approval before cycles use them")}
      {flag("allow_self_approval", "Authors may approve their own versions")}
      {flag("only_assignee_executes", "Only the assignee may execute a run")}
      {flag("require_defect_for_failure", "A failed result needs a linked defect")}
      <Field
        label="Module depth for reports"
        hint="Folder level used as “module” (1–5)."
        error={errors["settings.report_module_depth"]}
      >
        {(p) => (
          <Input
            {...p}
            type="number"
            min={1}
            max={5}
            disabled={!editable}
            value={settings.report_module_depth}
            onChange={(e) => {
              setSettings({ ...settings, report_module_depth: Number(e.target.value) });
            }}
          />
        )}
      </Field>
      <Field label="Attachment size limit (MB)" error={errors["settings.attachment_max_mb"]}>
        {(p) => (
          <Input
            {...p}
            type="number"
            min={1}
            disabled={!editable}
            value={settings.attachment_max_mb}
            onChange={(e) => {
              setSettings({ ...settings, attachment_max_mb: Number(e.target.value) });
            }}
          />
        )}
      </Field>
      {editable ? (
        <div>
          <Button type="submit">Save options</Button>
        </div>
      ) : null}
    </form>
  );
}

// -- Members --------------------------------------------------------------------------------------

function Members({ project, manage }: { project: Project; manage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const members = useMembers(project.id);
  const candidates = useQuery({
    queryKey: ["projects", project.id, "member-candidates"],
    enabled: manage,
    queryFn: async () =>
      (
        await api.GET("/api/v1/projects/{project_id}/member-candidates", {
          params: { path: { project_id: project.id } },
        })
      ).data ?? [],
  });
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<RoleCode>("viewer");
  const [error, setError] = useState<string | null>(null);
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.members(project.id) }),
      qc.invalidateQueries({ queryKey: ["projects", project.id, "member-candidates"] }),
      qc.invalidateQueries({ queryKey: keys.me }),
    ]);

  async function act(fn: () => Promise<unknown>, message: string) {
    setError(null);
    try {
      await fn();
      await refresh();
      toast(message);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  if (members.isPending) return <Skeleton />;
  if (members.isError) return <ErrorState error={members.error} />;
  return (
    <div className="flex flex-col gap-4">
      <FormError message={error} />
      {manage ? (
        <form
          className="flex items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void act(
              () =>
                api.POST("/api/v1/projects/{project_id}/members", {
                  params: { path: { project_id: project.id } },
                  body: { user_id: userId, role_code: role },
                }),
              "Member added",
            ).then(() => {
              setUserId("");
            });
          }}
        >
          <div className="w-72">
            <Field label="Add a person">
              {(p) => (
                <Select
                  {...p}
                  value={userId}
                  onChange={(e) => {
                    setUserId(e.target.value);
                  }}
                >
                  <option value="">Choose…</option>
                  {(candidates.data ?? []).map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.display_name} · {u.email}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <div className="w-44">
            <Field label="Role">
              {(p) => (
                <Select
                  {...p}
                  value={role}
                  onChange={(e) => {
                    setRole(e.target.value as RoleCode);
                  }}
                >
                  {ROLE_CODES.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABELS[r]}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Button type="submit" disabled={!userId}>
            Add
          </Button>
        </form>
      ) : null}
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col" className={th}>
              Name
            </th>
            <th scope="col" className={th}>
              Email
            </th>
            <th scope="col" className={th}>
              Role
            </th>
            {manage ? (
              <th scope="col" className={th}>
                <span className="sr-only">Actions</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {members.data.map((m) => (
            <tr key={m.user.id}>
              <td className={td}>
                {m.user.display_name}
                {!m.user.is_active ? <span className="ml-2 text-xs text-ink-muted">deactivated</span> : null}
              </td>
              <td className={`${td} text-ink-secondary`}>{m.user.email}</td>
              <td className={td}>
                {manage ? (
                  <Select
                    aria-label={`Role of ${m.user.display_name}`}
                    value={m.role.code}
                    className="h-8 w-40"
                    onChange={(e) =>
                      void act(
                        () =>
                          api.PATCH("/api/v1/projects/{project_id}/members/{user_id}", {
                            params: { path: { project_id: project.id, user_id: m.user.id } },
                            body: { role_code: e.target.value as RoleCode },
                          }),
                        "Role changed",
                      )
                    }
                  >
                    {ROLE_CODES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABELS[r]}
                      </option>
                    ))}
                  </Select>
                ) : (
                  m.role.name
                )}
              </td>
              {manage ? (
                <td className={`${td} text-right`}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      void act(
                        () =>
                          api.DELETE("/api/v1/projects/{project_id}/members/{user_id}", {
                            params: { path: { project_id: project.id, user_id: m.user.id } },
                          }),
                        "Member removed",
                      )
                    }
                  >
                    Remove
                  </Button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// -- Environments ---------------------------------------------------------------------------------

function Environments({ project, editable }: { project: Project; editable: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const envs = useEnvironments(project.id);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.environments(project.id) });

  async function act(fn: () => Promise<unknown>, message: string) {
    setError(null);
    try {
      await fn();
      await refresh();
      toast(message);
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  const toggle = (e: Environment) =>
    act(
      () =>
        e.archived
          ? api.POST("/api/v1/environments/{environment_id}/restore", {
              params: { path: { environment_id: e.id } },
            })
          : api.POST("/api/v1/environments/{environment_id}/archive", {
              params: { path: { environment_id: e.id } },
            }),
      e.archived ? `${e.name} restored` : `${e.name} archived`,
    );

  if (envs.isPending) return <Skeleton />;
  if (envs.isError) return <ErrorState error={envs.error} />;
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <FormError message={error} />
      {editable ? (
        <form
          className="flex items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void act(
              () =>
                api.POST("/api/v1/projects/{project_id}/environments", {
                  params: { path: { project_id: project.id } },
                  body: { name },
                }),
              "Environment added",
            ).then(() => {
              setName("");
            });
          }}
        >
          <div className="w-64">
            <Field label="New environment">
              {(p) => (
                <Input
                  {...p}
                  value={name}
                  maxLength={50}
                  onChange={(e) => {
                    setName(e.target.value);
                  }}
                />
              )}
            </Field>
          </div>
          <Button type="submit" disabled={!name.trim()}>
            Add
          </Button>
        </form>
      ) : null}
      <ul className="data-list">
        {envs.data.map((e) => (
          <li key={e.id} className="flex h-10 items-center justify-between px-4 text-sm">
            <span className={e.archived ? "text-ink-muted" : "text-ink"}>
              {e.name}
              {e.archived ? (
                <span className="ml-2 text-xs">archived · not selectable for new cycles</span>
              ) : null}
            </span>
            {editable ? (
              <Button variant="ghost" size="sm" onClick={() => void toggle(e)}>
                {e.archived ? "Restore" : "Archive"}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

// -- Releases -------------------------------------------------------------------------------------

const RELEASE_LABEL: Record<string, string> = {
  planned: "Planned",
  active: "Active",
  released: "Released",
  archived: "Archived",
};

function ReleaseRow({
  release,
  editable,
  onChanged,
}: {
  release: Release;
  editable: boolean;
  onChanged: (msg: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  return (
    <tr>
      <td className={td}>{release.name}</td>
      <td className={`${td} text-ink-secondary`}>
        {release.start_date ?? "—"} → {release.target_date ?? "—"}
      </td>
      <td className={td}>
        {editable && release.allowed_transitions.length > 0 ? (
          <Select
            aria-label={`Status of ${release.name}`}
            className="h-8 w-40"
            value={release.status}
            onChange={(e) => {
              setError(null);
              api
                .PATCH("/api/v1/releases/{release_id}", {
                  params: { path: { release_id: release.id } },
                  body: { status: e.target.value as Release["status"], row_version: release.row_version },
                })
                .then(() => {
                  onChanged(`${release.name} is now ${RELEASE_LABEL[e.target.value] ?? e.target.value}`);
                })
                .catch((err: unknown) => {
                  setError(errorMessage(err));
                });
            }}
          >
            <option value={release.status}>{RELEASE_LABEL[release.status]}</option>
            {release.allowed_transitions.map((s) => (
              <option key={s} value={s}>
                {RELEASE_LABEL[s]}
              </option>
            ))}
          </Select>
        ) : (
          RELEASE_LABEL[release.status]
        )}
        {error ? (
          <span role="alert" className="ml-2 text-xs text-danger">
            {error}
          </span>
        ) : null}
      </td>
    </tr>
  );
}

function Releases({ project, editable }: { project: Project; editable: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const releases = useReleases(project.id);
  const [form, setForm] = useState({ name: "", start_date: "", target_date: "" });
  const [error, setError] = useState<string | null>(null);
  const changed = (msg: string) => {
    void qc.invalidateQueries({ queryKey: keys.releases(project.id) });
    toast(msg);
  };
  if (releases.isPending) return <Skeleton />;
  if (releases.isError) return <ErrorState error={releases.error} />;
  return (
    <div className="flex flex-col gap-4">
      <FormError message={error} />
      {editable ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            api
              .POST("/api/v1/projects/{project_id}/releases", {
                params: { path: { project_id: project.id } },
                body: {
                  name: form.name,
                  start_date: form.start_date || null,
                  target_date: form.target_date || null,
                },
              })
              .then(() => {
                setForm({ name: "", start_date: "", target_date: "" });
                changed("Release added");
              })
              .catch((err: unknown) => {
                setError(errorMessage(err));
              });
          }}
        >
          <div className="w-56">
            <Field label="New release">
              {(p) => (
                <Input
                  {...p}
                  value={form.name}
                  maxLength={50}
                  onChange={(e) => {
                    setForm({ ...form, name: e.target.value });
                  }}
                />
              )}
            </Field>
          </div>
          <div className="w-40">
            <Field label="Start">
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  value={form.start_date}
                  onChange={(e) => {
                    setForm({ ...form, start_date: e.target.value });
                  }}
                />
              )}
            </Field>
          </div>
          <div className="w-40">
            <Field label="Target">
              {(p) => (
                <Input
                  {...p}
                  type="date"
                  value={form.target_date}
                  onChange={(e) => {
                    setForm({ ...form, target_date: e.target.value });
                  }}
                />
              )}
            </Field>
          </div>
          <Button type="submit" disabled={!form.name.trim()}>
            Add
          </Button>
        </form>
      ) : null}
      {releases.data.length === 0 ? (
        <EmptyState text="No releases yet." />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col" className={th}>
                Release
              </th>
              <th scope="col" className={th}>
                Dates
              </th>
              <th scope="col" className={th}>
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {releases.data.map((r) => (
              <ReleaseRow key={r.id} release={r} editable={editable} onChanged={changed} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// -- Danger zone ----------------------------------------------------------------------------------

function DangerZone({ project }: { project: Project }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.projects }),
      qc.invalidateQueries({ queryKey: keys.project(project.id) }),
    ]);
  if (project.status === "archived") {
    return (
      <div className="flex max-w-xl flex-col gap-3 text-sm">
        <p>This project is archived: it is read-only and still appears in reports.</p>
        <div>
          <Button
            variant="secondary"
            onClick={() =>
              void api
                .POST("/api/v1/projects/{project_id}/restore", {
                  params: { path: { project_id: project.id } },
                })
                .then(refresh)
                .then(() => {
                  toast("Project restored");
                })
                .catch((e: unknown) => {
                  setError(errorMessage(e));
                })
            }
          >
            Restore project
          </Button>
        </div>
        <FormError message={error} />
      </div>
    );
  }
  return (
    <div className="flex max-w-xl flex-col gap-3 text-sm">
      <p>
        Archiving makes the project read-only for everyone. Reports keep working; you can restore it later.
      </p>
      <div>
        <Button
          variant="destructive"
          onClick={() => {
            setOpen(true);
          }}
        >
          Archive project
        </Button>
      </div>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={`Archive ${project.name}?`}
        description={`Type the project key ${project.key} to confirm.`}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setOpen(false);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={confirm.trim().toUpperCase() !== project.key}
              onClick={() =>
                void api
                  .POST("/api/v1/projects/{project_id}/archive", {
                    params: { path: { project_id: project.id } },
                    body: { confirm_key: confirm },
                  })
                  .then(refresh)
                  .then(() => {
                    setOpen(false);
                    toast("Project archived");
                    void navigate({ to: "/projects" });
                  })
                  .catch((e: unknown) => {
                    setError(errorMessage(e));
                  })
              }
            >
              Archive
            </Button>
          </>
        }
      >
        <FormError message={error} />
        <Field label="Project key">
          {(p) => (
            <Input
              {...p}
              className="font-mono"
              value={confirm}
              onChange={(e) => {
                setConfirm(e.target.value);
              }}
            />
          )}
        </Field>
      </Dialog>
    </div>
  );
}

// -- page -----------------------------------------------------------------------------------------

export function SettingsPage({
  project,
  tab,
  onTab,
}: {
  project: Project;
  tab: string;
  onTab: (t: string) => void;
}) {
  const me = useMe().data;
  const perms = projectPermissions(me, project.id);
  const writable = project.status === "active";
  const configure = writable && can(perms, "project.configure");
  const manageMembers = writable && can(perms, "project.members.manage");
  const releases = writable && can(perms, "release.manage");
  const items = [
    {
      value: "general",
      label: "General",
      content: <General key={project.row_version} project={project} editable={configure} />,
    },
    {
      value: "options",
      label: "Options",
      content: <Options key={project.row_version} project={project} editable={configure} />,
    },
    { value: "members", label: "Members", content: <Members project={project} manage={manageMembers} /> },
    {
      value: "environments",
      label: "Environments",
      content: <Environments project={project} editable={configure} />,
    },
    { value: "releases", label: "Releases", content: <Releases project={project} editable={releases} /> },
    ...(can(perms, "project.configure")
      ? [{ value: "danger", label: "Danger zone", content: <DangerZone project={project} /> }]
      : []),
  ];
  return (
    <Page
      title="Settings"
      eyebrow={project.name}
      subtitle={writable ? undefined : "This project is archived and read-only."}
    >
      <Tabs
        label="Project settings"
        value={items.some((i) => i.value === tab) ? tab : "general"}
        onValueChange={onTab}
        items={items}
      />
    </Page>
  );
}
