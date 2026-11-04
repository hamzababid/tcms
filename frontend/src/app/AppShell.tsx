import * as Menu from "@radix-ui/react-dropdown-menu";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  FolderKanban,
  FolderTree,
  Settings,
  Shield,
  UserPlus,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "@/api/client";
import { useMe, useProjects, type Me, type Project } from "@/api/queries";
import { can, projectPermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";

import { Logo } from "./Logo";

const COLLAPSED_KEY = "assay.sidebarCollapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

interface NavItem {
  to: string;
  params?: Record<string, string>;
  label: string;
  icon: LucideIcon;
}

function NavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  return (
    <Link
      to={item.to}
      params={item.params}
      className="flex h-[34px] items-center gap-2.5 rounded-control px-2.5 text-[13.5px] font-medium text-sidebar-ink hover:bg-white/5"
      activeProps={{ className: "bg-sidebar-active text-white" }}
      title={collapsed ? item.label : undefined}
    >
      <item.icon aria-hidden="true" className="size-4 shrink-0" />
      <span className={collapsed ? "sr-only" : ""}>{item.label}</span>
    </Link>
  );
}

function useCurrentProject(projects: Project[] | undefined): Project | undefined {
  const params: { projectKey?: string } = useParams({ strict: false });
  return projects?.find((p) => p.key === params.projectKey);
}

function ProjectSwitcher({ projects, current }: { projects: Project[]; current: Project | undefined }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    // `G` then `P` opens the switcher, `G` then `R` goes to the repository (docs/07 §10).
    let armed = false;
    let timer = 0;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (e.key.toLowerCase() === "g" && !e.metaKey && !e.ctrlKey) {
        armed = true;
        window.clearTimeout(timer);
        timer = window.setTimeout(() => (armed = false), 1000);
      } else if (armed && e.key.toLowerCase() === "p") {
        armed = false;
        setOpen(true);
      } else if (armed && e.key.toLowerCase() === "r" && current) {
        armed = false;
        void navigate({ to: "/p/$projectKey/repository", params: { projectKey: current.key } });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [current, navigate]);
  return (
    <Menu.Root open={open} onOpenChange={setOpen}>
      <Menu.Trigger className="flex h-8 items-center gap-1.5 rounded-control border border-border px-2.5 text-sm font-medium text-ink hover:bg-ground">
        <span className="font-mono">{current?.key ?? "Projects"}</span>
        <ChevronDown aria-hidden="true" className="size-4 text-ink-muted" />
        <span className="sr-only">Switch project</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content
          align="start"
          sideOffset={4}
          className="z-50 min-w-64 rounded-card border border-border bg-surface p-1 shadow-md"
        >
          {projects.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-muted">No projects yet</p>
          ) : (
            projects.map((p) => (
              <Menu.Item
                key={p.id}
                onSelect={() =>
                  void navigate({ to: "/p/$projectKey/activity", params: { projectKey: p.key } })
                }
                className="flex cursor-pointer items-center gap-3 rounded-control px-3 py-2 text-sm text-ink outline-none data-[highlighted]:bg-ground"
              >
                <span className="w-16 font-mono text-xs text-ink-secondary">{p.key}</span>
                <span className="truncate">{p.name}</span>
                {p.status === "archived" ? (
                  <span className="ml-auto text-xs text-ink-muted">archived</span>
                ) : null}
              </Menu.Item>
            ))
          )}
          <Menu.Separator className="my-1 h-px bg-border" />
          <Menu.Item
            onSelect={() => void navigate({ to: "/projects" })}
            className="cursor-pointer rounded-control px-3 py-2 text-sm text-accent outline-none data-[highlighted]:bg-ground"
          >
            All projects
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

function Breadcrumbs({ project }: { project: Project | undefined }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const crumbs: string[] = [];
  if (project) {
    crumbs.push(project.key);
    if (path.endsWith("/activity")) crumbs.push("Activity");
    if (path.includes("/repository") || path.includes("/cases/")) crumbs.push("Repository");
    const caseKey = /\/cases\/([^/]+)/.exec(path)?.[1];
    if (caseKey === "new") crumbs.push("New case");
    else if (caseKey) crumbs.push(decodeURIComponent(caseKey));
    if (caseKey && path.endsWith("/edit")) crumbs.push("Edit");
    if (path.includes("/settings")) crumbs.push("Settings");
  } else if (path.startsWith("/projects")) crumbs.push("Projects");
  else if (path.startsWith("/profile")) crumbs.push("Profile");
  else if (path.startsWith("/admin")) crumbs.push("Administration");
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-2 text-sm text-ink-secondary">
        {crumbs.map((c, i) => (
          <li
            key={c}
            className={cn("flex items-center gap-2", i === crumbs.length - 1 && "font-semibold text-ink")}
          >
            {i > 0 ? <span aria-hidden="true">›</span> : null}
            {c}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function UserMenu({ me }: { me: Me }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const item =
    "cursor-pointer rounded-control px-3 py-2 text-sm text-ink outline-none data-[highlighted]:bg-ground";
  return (
    <Menu.Root>
      <Menu.Trigger className="flex size-8 items-center justify-center rounded-full bg-accent-tint text-xs font-semibold text-accent">
        {initials(me.user.display_name)}
        <span className="sr-only"> Account menu for {me.user.display_name}</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content
          align="end"
          sideOffset={4}
          className="z-50 min-w-56 rounded-card border border-border bg-surface p-1 shadow-md"
        >
          <div className="px-3 py-2">
            <p className="text-sm font-medium text-ink">{me.user.display_name}</p>
            <p className="text-xs text-ink-muted">{me.user.email}</p>
          </div>
          <Menu.Separator className="my-1 h-px bg-border" />
          {(
            [
              ["profile", "Profile"],
              ["sessions", "Sessions"],
              ["tokens", "API tokens"],
              ["security", "Two-step verification"],
            ] as const
          ).map(([tab, label]) => (
            <Menu.Item
              key={tab}
              className={item}
              onSelect={() => void navigate({ to: "/profile", search: { tab } })}
            >
              {label}
            </Menu.Item>
          ))}
          <Menu.Separator className="my-1 h-px bg-border" />
          <Menu.Item
            className={item}
            onSelect={() =>
              void api.POST("/api/v1/auth/logout").finally(() => {
                qc.clear();
                void navigate({ to: "/login" });
              })
            }
          >
            Sign out
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

/**
 * Application shell (docs/07 §3). Only features that exist are shown in the navigation; later
 * milestones add their items here.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe().data;
  const projects = useProjects().data;
  const current = useCurrentProject(projects);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const perms = useMemo(
    () => (current ? projectPermissions(me, current.id) : new Set<string>()),
    [me, current],
  );
  const isAdmin = Boolean(me?.org_permissions.includes("org.users.manage"));

  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, c ? "0" : "1");
      } catch {
        /* preference not persisted */
      }
      return !c;
    });
  };

  const projectItems: NavItem[] = current
    ? [
        {
          to: "/p/$projectKey/repository",
          params: { projectKey: current.key },
          label: "Repository",
          icon: FolderTree,
        },
        {
          to: "/p/$projectKey/activity",
          params: { projectKey: current.key },
          label: "Activity",
          icon: Activity,
        },
        ...(can(perms, "project.configure") || can(perms, "project.members.manage")
          ? [
              {
                to: "/p/$projectKey/settings",
                params: { projectKey: current.key },
                label: "Settings",
                icon: Settings,
              },
            ]
          : []),
      ]
    : [];

  return (
    <div className="flex h-full">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <nav
        aria-label="Primary"
        className={cn(
          "flex shrink-0 flex-col gap-6 bg-sidebar px-3 py-4 text-sidebar-ink",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <Link to="/" className={cn("flex h-8 items-center px-2", collapsed && "justify-center px-0")}>
          {collapsed ? (
            <Logo variant="mark-dark" className="size-7" />
          ) : (
            <Logo variant="dark" className="h-7 w-auto" />
          )}
        </Link>
        <div className="flex flex-col gap-1">
          <NavLink item={{ to: "/projects", label: "Projects", icon: FolderKanban }} collapsed={collapsed} />
        </div>
        {current ? (
          <div className="flex flex-col gap-1">
            <p
              className={cn(
                "px-2.5 text-[11px] font-semibold uppercase tracking-wide text-sidebar-ink/60",
                collapsed && "sr-only",
              )}
            >
              {current.key}
            </p>
            {projectItems.map((i) => (
              <NavLink key={i.label} item={i} collapsed={collapsed} />
            ))}
          </div>
        ) : null}
        {isAdmin ? (
          <div className="flex flex-col gap-1">
            <p
              className={cn(
                "px-2.5 text-[11px] font-semibold uppercase tracking-wide text-sidebar-ink/60",
                collapsed && "sr-only",
              )}
            >
              Organization
            </p>
            <NavLink
              item={{ to: "/admin/invitations", label: "Invitations", icon: UserPlus }}
              collapsed={collapsed}
            />
            <NavLink
              item={{ to: "/admin/security", label: "Security policy", icon: Shield }}
              collapsed={collapsed}
            />
          </div>
        ) : null}
        <button
          type="button"
          onClick={toggle}
          className="mt-auto flex h-8 items-center gap-2 rounded-control px-2.5 text-xs text-sidebar-ink hover:bg-white/5"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronsRight aria-hidden="true" className="size-4" />
          ) : (
            <ChevronsLeft aria-hidden="true" className="size-4" />
          )}
          {collapsed ? null : "Collapse"}
        </button>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface px-6">
          {projects ? <ProjectSwitcher projects={projects} current={current} /> : null}
          <Breadcrumbs project={current} />
          <div className="ml-auto">{me ? <UserMenu me={me} /> : null}</div>
        </header>
        <main id="main" className="min-h-0 flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
