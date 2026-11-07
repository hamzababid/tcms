import { Link } from "@tanstack/react-router";

import { useMe } from "@/api/queries";

/** Administration tab bar (docs/07 §5.13). A tab shows when the user holds its permission. */
const TABS = [
  { to: "/admin/users", label: "Users", perm: "org.users.manage" },
  { to: "/admin/invitations", label: "Invitations", perm: "org.users.manage" },
  { to: "/admin/roles", label: "Roles", perm: "org.users.manage" },
  { to: "/admin/security", label: "Security", perm: "org.manage" },
  { to: "/admin/audit", label: "Audit log", perm: "org.audit.view" },
  { to: "/admin/access-review", label: "Access review", perm: "org.audit.view" },
  { to: "/admin/system", label: "System", perm: "org.manage" },
] as const;

export type AdminPath = (typeof TABS)[number]["to"];

export function adminTabsFor(perms: readonly string[]) {
  return TABS.filter((t) => perms.includes(t.perm));
}

export function AdminTabs() {
  const me = useMe();
  const tabs = adminTabsFor(me.data?.org_permissions ?? []);
  return (
    <nav aria-label="Administration" className="border-b border-border bg-surface px-6">
      <ul className="flex gap-1 overflow-x-auto">
        {tabs.map((t) => (
          <li key={t.to}>
            <Link
              to={t.to}
              className="-mb-px inline-flex h-[38px] items-center whitespace-nowrap rounded-t-[4px] border-b-2 border-transparent px-2.5 text-[13px] font-medium text-ink-secondary transition-colors hover:text-ink focus-visible:bg-accent-tint focus-visible:outline-none"
              activeProps={{ className: "!border-accent font-semibold !text-ink" }}
            >
              {t.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
