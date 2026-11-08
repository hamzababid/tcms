import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal, UserPlus } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { keys, useMe, useOrgMembers, type OrgMember } from "@/api/queries";
import { DataTable } from "@/components/common/DataTable";
import { ConfirmDialog, PromptDialog } from "@/components/common/dialogs";
import { ErrorState, Page, useToast } from "@/components/common/feedback";
import { Tag } from "@/components/common/Tag";
import { Button } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { formatDateTime } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/permissions";

type Action =
  | { kind: "deactivate" | "reactivate" | "revoke" | "grant_admin" | "revoke_admin"; member: OrgMember }
  | { kind: "reset_mfa"; member: OrgMember };

const CONFIRM: Record<
  Exclude<Action["kind"], "reset_mfa">,
  { title: string; label: string; body: string; destructive: boolean }
> = {
  deactivate: {
    title: "Deactivate",
    label: "Deactivate",
    body: "They are signed out everywhere and their API tokens stop working. Their name stays on history and assignments.",
    destructive: true,
  },
  reactivate: {
    title: "Reactivate",
    label: "Reactivate",
    body: "They can sign in again with their password. Project roles are kept.",
    destructive: false,
  },
  revoke: {
    title: "Sign out everywhere",
    label: "Sign out",
    body: "Every session of this person ends now. They can sign in again.",
    destructive: false,
  },
  grant_admin: {
    title: "Make organization administrator",
    label: "Make administrator",
    body: "Administrators manage users, the security policy, the audit log and every project. Two-step verification becomes required for them.",
    destructive: false,
  },
  revoke_admin: {
    title: "Remove organization administrator",
    label: "Remove administrator",
    body: "They keep their project roles.",
    destructive: true,
  },
};

/** US-164 (docs/02 §3.5, docs/07 §5.13): people in the organization and what an admin can do to them. */
export function UsersPage() {
  const me = useMe();
  const members = useOrgMembers();
  const qc = useQueryClient();
  const toast = useToast();
  const [action, setAction] = useState<Action | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const rows = members.data ?? [];
  const activeAdmins = rows.filter((m) => m.is_org_admin && m.user.is_active).length;
  const selfId = me.data?.user.id;
  const lastAdmin = (m: OrgMember) => m.is_org_admin && m.user.is_active && activeAdmins <= 1;

  function close() {
    setAction(null);
    setError(null);
  }

  async function run(a: Action, reason?: string) {
    setPending(true);
    setError(null);
    const path = { params: { path: { user_id: a.member.user.id } } };
    try {
      if (a.kind === "deactivate") await api.POST("/api/v1/organization/members/{user_id}/deactivate", path);
      else if (a.kind === "reactivate")
        await api.POST("/api/v1/organization/members/{user_id}/reactivate", path);
      else if (a.kind === "revoke") {
        const { data } = await api.POST("/api/v1/organization/members/{user_id}/revoke-sessions", path);
        toast(`${data?.revoked ?? 0} session(s) ended`);
      } else if (a.kind === "reset_mfa")
        await api.POST("/api/v1/organization/members/{user_id}/reset-mfa", {
          ...path,
          body: { reason: reason ?? "" },
        });
      else
        await api.PATCH("/api/v1/organization/members/{user_id}", {
          ...path,
          body: { is_org_admin: a.kind === "grant_admin" },
        });
      if (a.kind !== "revoke") toast(`${a.member.user.display_name}: done`);
      await qc.invalidateQueries({ queryKey: keys.orgMembers });
      close();
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }

  const columns: ColumnDef<OrgMember>[] = [
    {
      id: "name",
      accessorFn: (m) => m.user.display_name,
      header: "Name",
      cell: (c) => {
        const m = c.row.original;
        return (
          <span className="flex flex-wrap items-center gap-1.5 font-medium">
            {m.user.display_name}
            {m.user.id === selfId ? <Tag tone="neutral">You</Tag> : null}
            {m.is_org_admin ? <Tag>Org admin</Tag> : null}
          </span>
        );
      },
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
      id: "status",
      accessorFn: (m) => (m.user.is_active ? "active" : "deactivated"),
      header: "Status",
      cell: (c) =>
        c.row.original.user.is_active ? (
          <span className="text-ink-secondary">Active</span>
        ) : (
          <Tag tone="neutral">Deactivated</Tag>
        ),
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "active", label: "Active" },
            { value: "deactivated", label: "Deactivated" },
          ],
        },
        width: "w-36",
      },
    },
    {
      id: "mfa",
      accessorFn: (m) => (m.mfa_enrolled ? "on" : "off"),
      header: "Two-step",
      cell: (c) =>
        c.row.original.mfa_enrolled ? (
          <span className="text-success">On</span>
        ) : (
          <span className="text-ink-muted">Off</span>
        ),
      meta: {
        filter: {
          kind: "select",
          options: [
            { value: "on", label: "On" },
            { value: "off", label: "Off" },
          ],
        },
        width: "w-28",
      },
    },
    {
      id: "projects",
      accessorFn: (m) =>
        (m.project_roles ?? [])
          .map((r) => `${r.project_key} ${ROLE_LABELS[r.role_code] ?? r.role_name}`)
          .join(" "),
      header: "Projects",
      enableSorting: false,
      cell: (c) => {
        const roles = c.row.original.project_roles ?? [];
        if (!roles.length) return <span className="text-ink-muted">—</span>;
        return (
          <span className="flex flex-wrap gap-1">
            {roles.map((r) => (
              <Tag
                key={r.project_id}
                tone="neutral"
                className={r.project_status === "archived" ? "opacity-70" : ""}
              >
                <span className="font-mono text-[11.5px] font-medium">{r.project_key}</span>
                {ROLE_LABELS[r.role_code] ?? r.role_name}
              </Tag>
            ))}
          </span>
        );
      },
      meta: { filter: { kind: "text", placeholder: "Project or role" } },
    },
    {
      id: "last_login_at",
      accessorKey: "last_login_at",
      header: "Last sign-in",
      cell: (c) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {c.getValue() ? formatDateTime(c.getValue() as string) : "Never"}
        </span>
      ),
      meta: { width: "w-44" },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      enableSorting: false,
      cell: (c) => (
        <UserActions
          member={c.row.original}
          isSelf={c.row.original.user.id === selfId}
          lastAdmin={lastAdmin(c.row.original)}
          onPick={setAction}
        />
      ),
      meta: { align: "right", width: "w-16", fixed: true, label: "Actions" },
    },
  ];

  const confirm = action && action.kind !== "reset_mfa" ? CONFIRM[action.kind] : null;
  return (
    <Page
      title="Users"
      subtitle="Everyone in the organization, their projects and two-step verification."
      width="full"
      actions={
        <Button size="sm" asChild>
          <Link to="/admin/invitations">
            <UserPlus aria-hidden="true" className="size-4" />
            Invite someone
          </Link>
        </Button>
      }
    >
      {members.isError ? (
        <ErrorState error={members.error} />
      ) : (
        <DataTable
          label="Users"
          columns={columns}
          data={rows}
          loading={members.isPending}
          getRowId={(m) => m.user.id}
          noun={["person", "people"]}
          initialSorting={[{ id: "name", desc: false }]}
        />
      )}
      {confirm && action ? (
        <ConfirmDialog
          open
          onOpenChange={(o) => {
            if (!o) close();
          }}
          title={`${confirm.title}: ${action.member.user.display_name}`}
          description={confirm.body}
          confirmLabel={confirm.label}
          destructive={confirm.destructive}
          pending={pending}
          error={error}
          onConfirm={() => void run(action)}
        />
      ) : null}
      {action?.kind === "reset_mfa" ? (
        <PromptDialog
          open
          onOpenChange={(o) => {
            if (!o) close();
          }}
          title={`Reset two-step verification: ${action.member.user.display_name}`}
          label="Reason (kept in the audit log)"
          submitLabel="Reset"
          multiline
          pending={pending}
          error={error}
          onSubmit={(reason) => void run(action, reason)}
        />
      ) : null}
    </Page>
  );
}

function UserActions({
  member,
  isSelf,
  lastAdmin,
  onPick,
}: {
  member: OrgMember;
  isSelf: boolean;
  lastAdmin: boolean;
  onPick: (a: Action) => void;
}) {
  const active = member.user.is_active;
  const item = (kind: Action["kind"], label: string, why: string | null, danger = false) => (
    <MenuItem
      disabled={why !== null}
      danger={danger}
      className="h-auto min-h-8 flex-col items-start justify-center gap-0 py-1.5"
      onSelect={() => {
        onPick({ kind, member });
      }}
    >
      <span>{label}</span>
      {why ? <span className="text-[11.5px] text-ink-muted">{why}</span> : null}
    </MenuItem>
  );
  const lastAdminWhy = lastAdmin ? "The last organization administrator" : null;
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size="xs" aria-label={`Actions for ${member.user.display_name}`}>
          <MoreHorizontal aria-hidden="true" className="size-4" />
        </Button>
      </MenuTrigger>
      <MenuContent align="end" className="w-64">
        {member.is_org_admin
          ? item("revoke_admin", "Remove organization admin", lastAdminWhy)
          : item("grant_admin", "Make organization admin", active ? null : "Reactivate them first")}
        {item("reset_mfa", "Reset two-step verification…", member.mfa_enrolled ? null : "Not set up")}
        {item("revoke", "Sign out everywhere", active ? null : "Deactivated: no sessions")}
        <MenuSeparator />
        {active
          ? item("deactivate", "Deactivate…", isSelf ? "You cannot deactivate yourself" : lastAdminWhy, true)
          : item("reactivate", "Reactivate", null)}
      </MenuContent>
    </Menu>
  );
}
