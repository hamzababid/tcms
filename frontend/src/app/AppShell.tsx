import * as M from "@radix-ui/react-dropdown-menu";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  Bug,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronsUpDown,
  BarChart3,
  ClipboardList,
  FileText,
  Flag,
  LayoutDashboard,
  GitCompare,
  FolderKanban,
  FolderTree,
  ListTodo,
  PlayCircle,
  Settings,
  Shield,
  UserPlus,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "@/api/client";
import { useMe, useProjects, type Me, type Project } from "@/api/queries";
import { MenuContent, MenuItem, MenuSeparator, MenuShortcut } from "@/components/ui/menu";
import { can, projectPermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";

import { GlobalSearch } from "@/features/search/GlobalSearch";

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
  /** Active only on this exact path (the project Overview is the parent of every project route). */
  exact?: boolean;
}

/** Sidebar item (docs/design/Sidebar.dc.html): 34 px, 13.5/500, 18 px icon, active #312E81. */
function NavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  return (
    <Link
      to={item.to}
      params={item.params}
      className={cn(
        "flex h-[34px] items-center gap-2.5 rounded-control px-2.5 text-[13.5px] font-medium text-sidebar-ink transition-colors hover:bg-sidebar-raised hover:text-sidebar-ink-strong",
        collapsed && "justify-center px-0",
      )}
      activeProps={{ className: "!bg-sidebar-active !text-white" }}
      activeOptions={{ exact: item.exact ?? false }}
      title={collapsed ? item.label : undefined}
    >
      <item.icon aria-hidden="true" className="size-[18px] shrink-0" strokeWidth={2} />
      <span className={collapsed ? "sr-only" : "truncate"}>{item.label}</span>
    </Link>
  );
}

function NavSection({
  label,
  collapsed,
  children,
}: {
  label?: string;
  collapsed: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      {label ? (
        <p
          className={cn(
            "px-2.5 pb-1.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-sidebar-label",
            collapsed && "sr-only",
          )}
        >
          {label}
        </p>
      ) : null}
      {children}
    </div>
  );
}

function useCurrentProject(projects: Project[] | undefined): Project | undefined {
  const params: { projectKey?: string } = useParams({ strict: false });
  return projects?.find((p) => p.key === params.projectKey);
}

/** Project switcher in the sidebar (docs/design/Sidebar.dc.html); `G` then `P` opens it. */
function ProjectSwitcher({
  projects,
  current,
  collapsed,
}: {
  projects: Project[];
  current: Project | undefined;
  collapsed: boolean;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    // `G` then `P` opens the switcher, `G R` the repository, `G C` the cycles, `G D` the bugs (docs/07 §10).
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
      } else if (armed && e.key.toLowerCase() === "c" && current) {
        armed = false;
        // Consumed here so page shortcuts (C = new case in the repository) do not also fire.
        e.preventDefault();
        void navigate({ to: "/p/$projectKey/cycles", params: { projectKey: current.key } });
      } else if (armed && (e.key.toLowerCase() === "q" || e.key.toLowerCase() === "t") && current) {
        armed = false;
        e.preventDefault();
        const to =
          e.key.toLowerCase() === "q" ? "/p/$projectKey/requirements" : "/p/$projectKey/traceability";
        void navigate({ to, params: { projectKey: current.key } });
      } else if (armed && e.key.toLowerCase() === "o" && current) {
        armed = false;
        e.preventDefault();
        void navigate({ to: "/p/$projectKey", params: { projectKey: current.key } });
      } else if (armed && e.key.toLowerCase() === "w") {
        armed = false;
        e.preventDefault();
        void navigate({ to: "/my-work" });
      } else if (armed && e.key.toLowerCase() === "d" && current) {
        armed = false;
        e.preventDefault(); // the runner's D (link a bug) checks defaultPrevented
        void navigate({ to: "/p/$projectKey/bugs", params: { projectKey: current.key } });
      }
    };
    // Capture phase: runs before page-level shortcut listeners on window.
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
    };
  }, [current, navigate]);
  return (
    <M.Root open={open} onOpenChange={setOpen}>
      <M.Trigger
        className={cn(
          "flex h-9 w-full items-center gap-2 rounded-control border border-sidebar-line bg-sidebar-raised px-2.5 text-left text-[13px] font-semibold text-sidebar-ink-strong transition-colors hover:border-[#4b5563] data-[state=open]:border-[#4b5563]",
          collapsed && "justify-center px-0",
        )}
        title={collapsed ? (current?.name ?? "Select a project") : undefined}
      >
        <span className="shrink-0 rounded bg-sidebar-line px-1.5 font-mono text-[11.5px] font-medium leading-[18px] text-[#e5e7eb]">
          {current?.key ?? (collapsed ? "—" : "Project")}
        </span>
        {collapsed ? null : (
          <>
            <span className="min-w-0 flex-1 truncate">{current?.name ?? "Select a project"}</span>
            <ChevronsUpDown aria-hidden="true" className="size-3.5 shrink-0 text-sidebar-label" />
          </>
        )}
        <span className="sr-only">Switch project</span>
      </M.Trigger>
      <MenuContent align="start" className="w-[264px]">
        <p className="px-2.5 pb-1 pt-1.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-muted">
          Projects
        </p>
        {projects.length === 0 ? (
          <p className="px-2.5 py-2 text-ink-muted">No projects yet</p>
        ) : (
          projects.map((p) => (
            <MenuItem
              key={p.id}
              onSelect={() => void navigate({ to: "/p/$projectKey", params: { projectKey: p.key } })}
              className={cn(p.id === current?.id && "bg-accent-tint text-accent-ink")}
            >
              <span className="w-[72px] shrink-0 truncate font-mono text-xs font-medium text-ink-secondary">
                {p.key}
              </span>
              <span className="truncate">{p.name}</span>
              {p.status === "archived" ? (
                <span className="ml-auto text-xs text-ink-muted">archived</span>
              ) : null}
            </MenuItem>
          ))
        )}
        <MenuSeparator />
        <MenuItem onSelect={() => void navigate({ to: "/projects" })} className="text-link">
          All projects
          <MenuShortcut>G P</MenuShortcut>
        </MenuItem>
      </MenuContent>
    </M.Root>
  );
}

interface Crumb {
  label: string;
  to?: string;
  params?: Record<string, string>;
  mono?: boolean;
}

function useCrumbs(project: Project | undefined): Crumb[] {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const crumbs: Crumb[] = [];
  if (project) {
    const params = { projectKey: project.key };
    crumbs.push({ label: project.key, to: "/p/$projectKey", params, mono: true });
    if (/^\/p\/[^/]+\/?$/.test(path)) crumbs.push({ label: "Overview" });
    if (path.endsWith("/activity")) crumbs.push({ label: "Activity" });
    if (path.endsWith("/reports")) crumbs.push({ label: "Reports" });
    if (path.includes("/releases")) {
      crumbs.push({ label: "Releases", to: "/p/$projectKey/releases", params });
      if (/\/releases\/[^/]+/.test(path)) crumbs.push({ label: "Release" });
    }
    if (path.endsWith("/bugs")) crumbs.push({ label: "Bugs" });
    if (path.endsWith("/requirements")) crumbs.push({ label: "Requirements" });
    if (path.endsWith("/traceability")) crumbs.push({ label: "Traceability" });
    if (path.includes("/plans")) {
      crumbs.push({ label: "Plans", to: "/p/$projectKey/plans", params });
      const planKey = /\/plans\/([^/]+)/.exec(path)?.[1];
      if (planKey) crumbs.push({ label: decodeURIComponent(planKey), mono: true });
    }
    if (path.includes("/cycles")) {
      crumbs.push({ label: "Cycles", to: "/p/$projectKey/cycles", params });
      const cycleKey = /\/cycles\/([^/]+)/.exec(path)?.[1];
      if (cycleKey) {
        const key = decodeURIComponent(cycleKey);
        crumbs.push({
          label: key,
          to: "/p/$projectKey/cycles/$cycleKey",
          params: { ...params, cycleKey: key },
          mono: true,
        });
        if (path.includes("/run/")) crumbs.push({ label: "Runner" });
      }
    }
    if (path.includes("/settings")) crumbs.push({ label: "Settings" });
    if (path.includes("/repository") || path.includes("/cases/")) {
      crumbs.push({ label: "Repository", to: "/p/$projectKey/repository", params });
    }
    const caseKey = /\/cases\/([^/]+)/.exec(path)?.[1];
    if (caseKey === "new") crumbs.push({ label: "New case" });
    else if (caseKey) {
      const key = decodeURIComponent(caseKey);
      crumbs.push(
        path.endsWith("/edit")
          ? {
              label: key,
              to: "/p/$projectKey/cases/$caseKey",
              params: { ...params, caseKey: key },
              mono: true,
            }
          : { label: key, mono: true },
      );
      if (path.endsWith("/edit")) crumbs.push({ label: "Edit" });
    }
  } else if (path.startsWith("/projects")) crumbs.push({ label: "Projects" });
  else if (path.startsWith("/my-work")) crumbs.push({ label: "My Work" });
  else if (path.startsWith("/org")) crumbs.push({ label: "Organization dashboard" });
  else if (path.startsWith("/profile")) crumbs.push({ label: "Your account" });
  else if (path.startsWith("/admin")) {
    crumbs.push({ label: "Administration" });
    crumbs.push({ label: path.includes("security") ? "Security policy" : "Invitations" });
  }
  // The last crumb is the current page.
  const last = crumbs.at(-1);
  if (last) delete last.to;
  return crumbs;
}

/** Breadcrumbs (docs/design/Topbar.dc.html): 13.5 px, chevron separators, current page in ink. */
function Breadcrumbs({ project }: { project: Project | undefined }) {
  const crumbs = useCrumbs(project);
  return (
    <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
      <ol className="flex min-w-0 items-center gap-2 text-[13.5px] text-ink-secondary">
        {crumbs.map((c, i) => (
          <li key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-2">
            {i > 0 ? <ChevronRight aria-hidden="true" className="size-3.5 shrink-0 text-ink-faint" /> : null}
            {c.to ? (
              <Link
                to={c.to}
                params={c.params}
                className={cn(
                  "truncate text-ink-secondary hover:text-ink",
                  c.mono && "font-mono text-[13px]",
                )}
              >
                {c.label}
              </Link>
            ) : (
              <span
                aria-current={i === crumbs.length - 1 ? "page" : undefined}
                className={cn(
                  "truncate",
                  i === crumbs.length - 1 && "font-medium text-ink",
                  c.mono && "font-mono text-[13px]",
                )}
              >
                {c.label}
              </span>
            )}
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
  return (
    <M.Root>
      <M.Trigger className="flex size-8 items-center justify-center rounded-full bg-avatar text-[12.5px] font-semibold text-accent-ink ring-offset-2 transition-shadow hover:ring-2 hover:ring-accent-border data-[state=open]:ring-2 data-[state=open]:ring-accent-border">
        {initials(me.user.display_name)}
        <span className="sr-only"> Account menu for {me.user.display_name}</span>
      </M.Trigger>
      <MenuContent align="end" className="w-60">
        <div className="flex items-center gap-2.5 px-2.5 py-2">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-avatar text-[12.5px] font-semibold text-accent-ink">
            {initials(me.user.display_name)}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium text-ink">{me.user.display_name}</p>
            <p className="truncate text-xs text-ink-muted">{me.user.email}</p>
          </div>
        </div>
        <MenuSeparator />
        {(
          [
            ["profile", "Profile"],
            ["sessions", "Sessions"],
            ["tokens", "API tokens"],
            ["security", "Two-step verification"],
          ] as const
        ).map(([tab, label]) => (
          <MenuItem key={tab} onSelect={() => void navigate({ to: "/profile", search: { tab } })}>
            {label}
          </MenuItem>
        ))}
        <MenuSeparator />
        <MenuItem
          onSelect={() =>
            void api.POST("/api/v1/auth/logout").finally(() => {
              qc.clear();
              void navigate({ to: "/login" });
            })
          }
        >
          Sign out
        </MenuItem>
      </MenuContent>
    </M.Root>
  );
}

/**
 * Application shell (docs/07 §3, docs/design/Sidebar + Topbar). Only features that exist are shown
 * in the navigation; later milestones add their items here.
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
          to: "/p/$projectKey",
          params: { projectKey: current.key },
          label: "Overview",
          icon: LayoutDashboard,
          exact: true,
        },
        {
          to: "/p/$projectKey/repository",
          params: { projectKey: current.key },
          label: "Repository",
          icon: FolderTree,
        },
        {
          to: "/p/$projectKey/plans",
          params: { projectKey: current.key },
          label: "Plans",
          icon: ClipboardList,
        },
        {
          to: "/p/$projectKey/cycles",
          params: { projectKey: current.key },
          label: "Cycles",
          icon: PlayCircle,
        },
        {
          to: "/p/$projectKey/bugs",
          params: { projectKey: current.key },
          label: "Bugs",
          icon: Bug,
        },
        {
          to: "/p/$projectKey/requirements",
          params: { projectKey: current.key },
          label: "Requirements",
          icon: FileText,
        },
        {
          to: "/p/$projectKey/traceability",
          params: { projectKey: current.key },
          label: "Traceability",
          icon: GitCompare,
        },
        {
          to: "/p/$projectKey/releases",
          params: { projectKey: current.key },
          label: "Releases",
          icon: Flag,
        },
        {
          to: "/p/$projectKey/reports",
          params: { projectKey: current.key },
          label: "Reports",
          icon: BarChart3,
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
          "flex shrink-0 flex-col gap-5 bg-sidebar px-3 py-4 text-sidebar-ink transition-[width] duration-150",
          collapsed ? "w-16" : "w-[var(--sidebar-width)]",
        )}
      >
        <Link to="/" className={cn("flex h-8 items-center px-2", collapsed && "justify-center px-0")}>
          {collapsed ? (
            <Logo variant="mark-dark" className="size-7" />
          ) : (
            <Logo variant="dark" className="h-7 w-auto" />
          )}
        </Link>
        <NavSection collapsed={collapsed}>
          <NavLink item={{ to: "/my-work", label: "My Work", icon: ListTodo }} collapsed={collapsed} />
        </NavSection>
        {projects ? (
          <NavSection collapsed={collapsed}>
            <ProjectSwitcher projects={projects} current={current} collapsed={collapsed} />
            {projectItems.length ? <div className="h-2" /> : null}
            {projectItems.map((i) => (
              <NavLink key={i.label} item={i} collapsed={collapsed} />
            ))}
          </NavSection>
        ) : null}
        <NavSection label="Organization" collapsed={collapsed}>
          <NavLink item={{ to: "/org", label: "Dashboard", icon: LayoutDashboard }} collapsed={collapsed} />
          <NavLink item={{ to: "/projects", label: "Projects", icon: FolderKanban }} collapsed={collapsed} />
          {isAdmin ? (
            <>
              <NavLink
                item={{ to: "/admin/invitations", label: "Invitations", icon: UserPlus }}
                collapsed={collapsed}
              />
              <NavLink
                item={{ to: "/admin/security", label: "Security policy", icon: Shield }}
                collapsed={collapsed}
              />
            </>
          ) : null}
        </NavSection>
        <div className="mt-auto border-t border-sidebar-raised pt-2">
          <button
            type="button"
            onClick={toggle}
            className={cn(
              "flex h-8 w-full items-center gap-2 rounded-control px-2.5 text-xs text-sidebar-label transition-colors hover:bg-sidebar-raised hover:text-sidebar-ink",
              collapsed && "justify-center px-0",
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronsRight aria-hidden="true" className="size-4" />
            ) : (
              <ChevronsLeft aria-hidden="true" className="size-4" />
            )}
            {collapsed ? null : "Collapse"}
          </button>
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[var(--topbar-height)] shrink-0 items-center gap-4 border-b border-border bg-surface px-6">
          <Breadcrumbs project={current} />
          <GlobalSearch project={current} />
          {me ? <UserMenu me={me} /> : null}
        </header>
        <main id="main" className="min-h-0 flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
