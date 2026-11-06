import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
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
  type ProjectMember,
  type Release,
} from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { Card, ErrorState, Facts, Page, errorMessage, useToast } from "@/components/common/feedback";
import { Tag } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea, ToggleField } from "@/components/ui/field";
import { Tabs } from "@/components/ui/tabs";
import { FormError } from "@/features/auth/AuthCard";
import { formatDate, formatDateTime } from "@/lib/format";
import { can, projectPermissions, ROLE_LABELS } from "@/lib/permissions";

const ROLE_CODES = ["qa_manager", "qa_lead", "qa_engineer", "developer", "pm_ba", "viewer"] as const;
type RoleCode = (typeof ROLE_CODES)[number];
const ROLE_OPTIONS = ROLE_CODES.map((r) => ({ value: r, label: ROLE_LABELS[r] ?? r }));

function useInvalidateProject(projectId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.project(projectId) });
}

/** Stale row_version → "changed by someone else" with Reload (docs/02 §2.4, docs/07 §4.4). */
function StaleNotice({ onReload }: { onReload: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between rounded-control border border-border bg-ground px-3 py-2 text-[13px]"
    >
      <span>This item was changed by someone else.</span>
      <Button size="xs" variant="secondary" onClick={onReload}>
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
  const members = useMembers(project.id);
  const envs = useEnvironments(project.id);
  const releases = useReleases(project.id);
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
  const s = project.settings;
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
      <form onSubmit={(e) => void save(e)}>
        <Card
          title="Project details"
          description="Name and description shown across the project."
          footer={editable ? <Button type="submit">Save changes</Button> : undefined}
        >
          <div className="flex flex-col gap-4">
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
            <div className="grid gap-4 md:grid-cols-[200px_minmax(0,1fr)]">
              <Field label="Key" hint="The key never changes.">
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
            </div>
            <Field label="Description">
              {(p) => (
                <Textarea
                  {...p}
                  rows={4}
                  value={description}
                  disabled={!editable}
                  onChange={(e) => {
                    setDescription(e.target.value);
                  }}
                />
              )}
            </Field>
          </div>
        </Card>
      </form>
      <div className="flex flex-col gap-5">
        <Card title="Summary">
          <Facts
            items={[
              [
                "Status",
                project.status === "archived" ? (
                  <Tag tone="neutral">Archived · read-only</Tag>
                ) : (
                  <Tag>Active</Tag>
                ),
              ],
              ["Members", members.data?.length ?? "—"],
              ["Environments", envs.data?.filter((e) => !e.archived).length ?? "—"],
              ["Releases", releases.data?.length ?? "—"],
              ["Created", formatDateTime(project.created_at)],
              ["Last changed", formatDateTime(project.updated_at)],
            ]}
          />
        </Card>
        <Card title="Options in effect">
          <Facts
            items={[
              ["Case approval", s.approval_required ? "Required" : "Off (auto-approved)"],
              ["Self-approval", s.allow_self_approval ? "Allowed" : "Not allowed"],
              ["Execution", s.only_assignee_executes ? "Assignee only" : "Any tester"],
              ["Failed results", s.require_bug_link_for_failure ? "Need a bug link" : "Bug link optional"],
              ["Bug tracker", s.bug_tracker_name + (s.bug_url_template ? " (links from references)" : "")],
              ["Report module", `Folder level ${s.report_module_depth}`],
              ["Attachments", `Up to ${s.attachment_max_mb} MB`],
            ]}
          />
        </Card>
      </div>
    </div>
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
    k:
      "approval_required" | "allow_self_approval" | "only_assignee_executes" | "require_bug_link_for_failure",
    label: string,
    description: string,
  ) => (
    <ToggleField
      label={label}
      description={description}
      checked={settings[k]}
      disabled={!editable}
      onChange={(e) => {
        setSettings({ ...settings, [k]: e.target.checked });
      }}
    />
  );
  return (
    <form onSubmit={(e) => void save(e)} className="flex flex-col gap-5">
      {stale ? (
        <StaleNotice
          onReload={() =>
            void invalidate().then(() => {
              setStale(false);
            })
          }
        />
      ) : null}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Review workflow" description="How test case versions become usable in cycles.">
          <div className="flex flex-col gap-4">
            {flag(
              "approval_required",
              "Test cases need approval before cycles use them",
              "New versions start as Draft and are reviewed. Turning this on keeps existing cases approved.",
            )}
            {flag(
              "allow_self_approval",
              "Authors may approve their own versions",
              "When off, a different person with approval rights must approve.",
            )}
          </div>
        </Card>
        <Card title="Execution" description="Rules applied while running tests.">
          <div className="flex flex-col gap-4">
            {flag(
              "only_assignee_executes",
              "Only the assignee may execute a run",
              "Other testers can view the run but not record results.",
            )}
            {flag(
              "require_bug_link_for_failure",
              "A failed result needs a bug link",
              "Finishing a failed run asks for the bug's reference in your tracker.",
            )}
          </div>
        </Card>
        <Card
          title="Bug tracker"
          description="Bugs live in your team's tracker (Jira, Azure DevOps, GitHub…); Assay links to them."
        >
          <div className="flex flex-col gap-4">
            <Field
              label="Tracker name"
              hint="Shown on buttons, e.g. “Open in Jira”."
              error={errors["settings.bug_tracker_name"]}
            >
              {(p) => (
                <Input
                  {...p}
                  className="max-w-64"
                  maxLength={40}
                  disabled={!editable}
                  value={settings.bug_tracker_name}
                  onChange={(e) => {
                    setSettings({ ...settings, bug_tracker_name: e.target.value });
                  }}
                />
              )}
            </Field>
            <Field
              label="Bug address"
              hint="Optional. Put {ref} where the reference goes, e.g. https://acme.atlassian.net/browse/{ref}"
              error={errors["settings.bug_url_template"]}
            >
              {(p) => (
                <Input
                  {...p}
                  type="url"
                  disabled={!editable}
                  placeholder="https://tracker.example.com/issues/{ref}"
                  value={settings.bug_url_template ?? ""}
                  onChange={(e) => {
                    setSettings({ ...settings, bug_url_template: e.target.value });
                  }}
                />
              )}
            </Field>
          </div>
        </Card>
        <Card title="Reporting" description="How folders roll up in reports.">
          <Field
            label="Module depth"
            hint="Folder level used as “module” in reports (1–5)."
            error={errors["settings.report_module_depth"]}
          >
            {(p) => (
              <Input
                {...p}
                type="number"
                min={1}
                max={5}
                className="max-w-40"
                disabled={!editable}
                value={settings.report_module_depth}
                onChange={(e) => {
                  setSettings({ ...settings, report_module_depth: Number(e.target.value) });
                }}
              />
            )}
          </Field>
        </Card>
        <Card title="Attachments" description="Applies to cases, steps and results.">
          <Field
            label="Size limit (MB)"
            hint="Up to the organization limit."
            error={errors["settings.attachment_max_mb"]}
          >
            {(p) => (
              <Input
                {...p}
                type="number"
                min={1}
                className="max-w-40"
                disabled={!editable}
                value={settings.attachment_max_mb}
                onChange={(e) => {
                  setSettings({ ...settings, attachment_max_mb: Number(e.target.value) });
                }}
              />
            )}
          </Field>
        </Card>
      </div>
      {editable ? (
        <div className="flex justify-end">
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

  const columns: ColumnDef<ProjectMember>[] = [
    {
      id: "name",
      accessorFn: (m) => m.user.display_name,
      header: "Name",
      cell: (c) => (
        <span className="font-medium">
          {c.row.original.user.display_name}
          {!c.row.original.user.is_active ? (
            <Tag tone="neutral" className="ml-2">
              Deactivated
            </Tag>
          ) : null}
        </span>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      id: "email",
      accessorFn: (m) => m.user.email,
      header: "Email",
      cell: (c) => <span className="text-ink-secondary">{c.getValue() as string}</span>,
      meta: { filter: { kind: "text" } },
    },
    {
      id: "role",
      accessorFn: (m) => m.role.code,
      header: "Role",
      cell: (c) => {
        const m = c.row.original;
        return manage ? (
          <Select
            aria-label={`Role of ${m.user.display_name}`}
            value={m.role.code}
            className="h-8 w-44"
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
            {ROLE_OPTIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        ) : (
          m.role.name
        );
      },
      meta: { filter: { kind: "select", options: ROLE_OPTIONS }, width: "w-56" },
    },
    {
      id: "granted_at",
      accessorKey: "granted_at",
      header: "Member since",
      cell: (c) => <span className="text-ink-secondary">{formatDate(c.getValue() as string)}</span>,
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    ...(manage
      ? [
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
                  void act(
                    () =>
                      api.DELETE("/api/v1/projects/{project_id}/members/{user_id}", {
                        params: { path: { project_id: project.id, user_id: c.row.original.user.id } },
                      }),
                    "Member removed",
                  )
                }
              >
                Remove
              </Button>
            ),
            meta: { align: "right", width: "w-28", fixed: true, label: "Actions" },
          } satisfies ColumnDef<ProjectMember>,
        ]
      : []),
  ];

  if (members.isError) return <ErrorState error={members.error} />;
  return (
    <div className="flex flex-col gap-3">
      <FormError message={error} />
      <DataTable
        label="Project members"
        columns={columns}
        data={members.data ?? []}
        loading={members.isPending}
        getRowId={(m) => m.user.id}
        noun={["member", "members"]}
        initialSorting={[{ id: "name", desc: false }]}
        toolbar={
          manage ? (
            <form
              className="flex flex-wrap items-center gap-2"
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
              <Select
                aria-label="Add a person"
                className="h-8 w-72 text-[13px]"
                value={userId}
                onChange={(e) => {
                  setUserId(e.target.value);
                }}
              >
                <option value="">Add a person…</option>
                {(candidates.data ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.display_name} · {u.email}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Role"
                className="h-8 w-40 text-[13px]"
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as RoleCode);
                }}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </Select>
              <Button type="submit" size="sm" disabled={!userId}>
                <Plus aria-hidden="true" className="size-4" />
                Add
              </Button>
            </form>
          ) : undefined
        }
      />
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

  const columns: ColumnDef<Environment>[] = [
    {
      accessorKey: "name",
      header: "Environment",
      cell: (c) => <span className="font-medium">{c.row.original.name}</span>,
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      accessorKey: "description",
      header: "Description",
      cell: (c) => <span className="text-ink-secondary">{(c.getValue() as string | null) ?? "—"}</span>,
      meta: { filter: { kind: "text" } },
    },
    {
      id: "status",
      accessorFn: (e) => (e.archived ? "archived" : "active"),
      header: "Status",
      cell: (c) =>
        c.row.original.archived ? (
          <Tag tone="neutral">Archived · not selectable for new cycles</Tag>
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
        width: "w-80",
      },
    },
    ...(editable
      ? [
          {
            id: "actions",
            header: () => <span className="sr-only">Actions</span>,
            enableSorting: false,
            cell: (c) => (
              <Button variant="ghost" size="xs" onClick={() => void toggle(c.row.original)}>
                {c.row.original.archived ? "Restore" : "Archive"}
              </Button>
            ),
            meta: { align: "right", width: "w-28", fixed: true, label: "Actions" },
          } satisfies ColumnDef<Environment>,
        ]
      : []),
  ];

  if (envs.isError) return <ErrorState error={envs.error} />;
  return (
    <div className="flex flex-col gap-3">
      <FormError message={error} />
      <DataTable
        label="Environments"
        columns={columns}
        data={envs.data ?? []}
        loading={envs.isPending}
        getRowId={(e) => e.id}
        noun={["environment", "environments"]}
        initialSorting={[{ id: "name", desc: false }]}
        toolbar={
          editable ? (
            <form
              className="flex items-center gap-2"
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
              <Input
                aria-label="New environment"
                placeholder="New environment name"
                className="h-8 w-64 text-[13px]"
                value={name}
                maxLength={50}
                onChange={(e) => {
                  setName(e.target.value);
                }}
              />
              <Button type="submit" size="sm" disabled={!name.trim()}>
                <Plus aria-hidden="true" className="size-4" />
                Add
              </Button>
            </form>
          ) : undefined
        }
      />
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
const RELEASE_OPTIONS = Object.entries(RELEASE_LABEL).map(([value, label]) => ({ value, label }));

function ReleaseStatus({
  release,
  editable,
  onChanged,
}: {
  release: Release;
  editable: boolean;
  onChanged: (msg: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  if (!editable || release.allowed_transitions.length === 0) {
    return (
      <Tag tone={release.status === "active" ? "accent" : "neutral"}>{RELEASE_LABEL[release.status]}</Tag>
    );
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Select
        aria-label={`Status of ${release.name}`}
        className="h-8 w-36"
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
      {error ? (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      ) : null}
    </span>
  );
}

function NewReleaseDialog({
  project,
  open,
  onOpenChange,
  onCreated,
}: {
  project: Project;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onCreated: (msg: string) => void;
}) {
  const [form, setForm] = useState({ name: "", start_date: "", target_date: "", description: "" });
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New release"
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
          <Button type="submit" form="new-release" disabled={!form.name.trim()}>
            Create release
          </Button>
        </>
      }
    >
      <form
        id="new-release"
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          api
            .POST("/api/v1/projects/{project_id}/releases", {
              params: { path: { project_id: project.id } },
              body: {
                name: form.name,
                description: form.description || null,
                start_date: form.start_date || null,
                target_date: form.target_date || null,
              },
            })
            .then(() => {
              setForm({ name: "", start_date: "", target_date: "", description: "" });
              onOpenChange(false);
              onCreated("Release added");
            })
            .catch((err: unknown) => {
              setError(errorMessage(err));
            });
        }}
      >
        <FormError message={error} />
        <Field label="Name" required>
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
        <div className="grid grid-cols-2 gap-4">
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
        <Field label="Description">
          {(p) => (
            <Textarea
              {...p}
              rows={3}
              value={form.description}
              onChange={(e) => {
                setForm({ ...form, description: e.target.value });
              }}
            />
          )}
        </Field>
      </form>
    </Dialog>
  );
}

function Releases({ project, editable }: { project: Project; editable: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const releases = useReleases(project.id);
  const [open, setOpen] = useState(false);
  const changed = (msg: string) => {
    void qc.invalidateQueries({ queryKey: keys.releases(project.id) });
    toast(msg);
  };
  const columns: ColumnDef<Release>[] = [
    {
      accessorKey: "name",
      header: "Release",
      cell: (c) => (
        <div className="min-w-0">
          <p className="font-medium">{c.row.original.name}</p>
          {c.row.original.description ? (
            <p className="truncate text-xs text-ink-secondary">{c.row.original.description}</p>
          ) : null}
        </div>
      ),
      meta: { filter: { kind: "text" }, fixed: true },
    },
    {
      accessorKey: "start_date",
      header: "Start",
      cell: (c) => <span className="text-ink-secondary">{formatDate(c.getValue() as string | null)}</span>,
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      accessorKey: "target_date",
      header: "Target",
      cell: (c) => <span className="text-ink-secondary">{formatDate(c.getValue() as string | null)}</span>,
      meta: { filter: { kind: "daterange" }, width: "w-44" },
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: (c) => <ReleaseStatus release={c.row.original} editable={editable} onChanged={changed} />,
      meta: { filter: { kind: "select", options: RELEASE_OPTIONS }, width: "w-56" },
    },
  ];
  if (releases.isError) return <ErrorState error={releases.error} />;
  return (
    <>
      <DataTable
        label="Releases"
        columns={columns}
        data={releases.data ?? []}
        loading={releases.isPending}
        getRowId={(r) => r.id}
        noun={["release", "releases"]}
        emptyText="No releases match these filters."
        toolbar={
          editable ? (
            <Button
              size="sm"
              onClick={() => {
                setOpen(true);
              }}
            >
              <Plus aria-hidden="true" className="size-4" />
              New release
            </Button>
          ) : undefined
        }
      />
      <NewReleaseDialog project={project} open={open} onOpenChange={setOpen} onCreated={changed} />
    </>
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
  // 409 invalid_status lists planned/active cycles; archiving then offers to close them (docs/02 §4.2).
  const [openCycles, setOpenCycles] = useState<{ key: string; name: string }[]>([]);
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.projects }),
      qc.invalidateQueries({ queryKey: keys.project(project.id) }),
    ]);
  if (project.status === "archived") {
    return (
      <Card
        title="Restore project"
        description="This project is archived: it is read-only and still appears in reports."
        footer={
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
        }
      >
        <FormError message={error} />
        <p className="text-[13px] text-ink-secondary">
          Restoring makes the project editable again for its members.
        </p>
      </Card>
    );
  }
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card
        tone="danger"
        title="Archive project"
        description="Archiving makes the project read-only for everyone."
        footer={
          <Button
            variant="destructive"
            onClick={() => {
              setOpen(true);
            }}
          >
            Archive project
          </Button>
        }
      >
        <ul className="list-disc space-y-1 pl-5 text-[13px] text-ink-secondary">
          <li>Cases, cycles and results stay visible; nothing is deleted.</li>
          <li>Reports keep working and include the project.</li>
          <li>A QA Manager can restore it later.</li>
        </ul>
      </Card>
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
                    body: { confirm_key: confirm, close_open_cycles: openCycles.length > 0 },
                  })
                  .then(refresh)
                  .then(() => {
                    setOpen(false);
                    toast("Project archived");
                    void navigate({ to: "/projects" });
                  })
                  .catch((e: unknown) => {
                    const listed = e instanceof ApiError ? e.body.open_cycles : undefined;
                    if (Array.isArray(listed) && listed.length > 0) {
                      setError(null);
                      setOpenCycles(listed as { key: string; name: string }[]);
                    } else setError(errorMessage(e));
                  })
              }
            >
              {openCycles.length > 0 ? "Close cycles and archive" : "Archive"}
            </Button>
          </>
        }
      >
        <FormError message={error} />
        {openCycles.length > 0 ? (
          <div role="alert" className="mb-4 text-[13px] text-ink-secondary">
            <p className="mb-1.5 font-medium text-ink">
              {openCycles.length === 1 ? "1 cycle is" : `${openCycles.length} cycles are`} still open.
              Archiving closes {openCycles.length === 1 ? "it" : "them"} and discards unsaved draft results.
            </p>
            <ul className="list-disc pl-5">
              {openCycles.map((c) => (
                <li key={c.key}>
                  <span className="font-mono">{c.key}</span> {c.name}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
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
      subtitle={
        writable
          ? "Project details, options, people, environments and releases."
          : "This project is archived and read-only."
      }
      width="full"
    >
      <Tabs
        label="Project settings"
        value={items.some((i) => i.value === tab) ? tab : "general"}
        onValueChange={onTab}
        items={items}
        contentClassName="pt-5"
      />
    </Page>
  );
}
