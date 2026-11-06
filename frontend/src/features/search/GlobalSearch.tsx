import * as D from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import type { Project } from "@/api/queries";
import { Kbd } from "@/components/common/Tag";
import { Checkbox } from "@/components/ui/field";
import { safeUrl } from "@/features/bugs/api";
import { cn } from "@/lib/utils";

type Item = components["schemas"]["SearchItem"];
type Hit = { kind: "item"; item: Item } | { kind: "action"; label: string; run: () => void };

const GROUP_LABEL: Record<Item["type"], string> = {
  test_case: "Test cases",
  requirement: "Requirements",
  bug: "Bugs",
  cycle: "Cycles",
  plan: "Plans",
  folder: "Folders",
};

/**
 * Global search and command palette (docs/02 §12, docs/07 §4.3; US-130/133): `/` opens it, an exact key opens
 * the record on Enter, `>` lists actions. Scoped to the current project unless "All projects" is ticked.
 */
export function GlobalSearch({ project }: { project: Project | undefined }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [everywhere, setEverywhere] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !document.querySelector("[role=dialog]")) {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => {
      setQ(text.trim());
    }, 200);
    return () => {
      window.clearTimeout(t);
    };
  }, [text]);

  const command = text.trimStart().startsWith(">");
  const results = useQuery({
    queryKey: ["search", q, everywhere ? null : (project?.id ?? null)],
    enabled: open && !command && q.length > 0,
    queryFn: async () =>
      (
        await api.GET("/api/v1/search", {
          params: { query: { q, ...(project && !everywhere ? { project_id: project.id } : {}) } },
        })
      ).data,
  });

  const close = () => {
    setOpen(false);
    setText("");
    setActive(0);
  };
  const go = (to: string, params: Record<string, string>, search?: Record<string, string>) => {
    close();
    void navigate({ to, params, ...(search ? { search } : {}) } as never);
  };
  const openItem = (i: Item) => {
    const projectKey = i.project.key;
    if (i.type === "test_case") go("/p/$projectKey/cases/$caseKey", { projectKey, caseKey: i.key });
    else if (i.type === "cycle") go("/p/$projectKey/cycles/$cycleKey", { projectKey, cycleKey: i.key });
    else if (i.type === "plan") go("/p/$projectKey/plans/$planKey", { projectKey, planKey: i.key });
    else if (i.type === "folder") go("/p/$projectKey/repository", { projectKey }, { folder: i.id });
    else if (i.type === "requirement") go("/p/$projectKey/traceability", { projectKey });
    else go("/p/$projectKey/bugs", { projectKey });
  };

  const actions: Hit[] = [
    {
      kind: "action",
      label: "Go to My Work",
      run: () => {
        go("/my-work", {});
      },
    },
    ...(project
      ? (
          [
            ["Go to Overview", "/p/$projectKey"],
            ["Go to Repository", "/p/$projectKey/repository"],
            ["New test case", "/p/$projectKey/cases/new"],
            ["Go to Plans", "/p/$projectKey/plans"],
            ["Go to Cycles", "/p/$projectKey/cycles"],
            ["Go to Bugs", "/p/$projectKey/bugs"],
            ["Go to Requirements", "/p/$projectKey/requirements"],
            ["Go to Traceability", "/p/$projectKey/traceability"],
            ["Go to Releases", "/p/$projectKey/releases"],
            ["Go to Reports", "/p/$projectKey/reports"],
            ["Go to Activity", "/p/$projectKey/activity"],
          ] as const
        ).map(([label, to]): Hit => ({
          kind: "action",
          label,
          run: () => {
            go(to, { projectKey: project.key });
          },
        }))
      : []),
    {
      kind: "action",
      label: "Go to Organization dashboard",
      run: () => {
        go("/org", {});
      },
    },
    {
      kind: "action",
      label: "Go to Projects",
      run: () => {
        go("/projects", {});
      },
    },
  ];
  const needle = text.trimStart().slice(1).trim().toLowerCase();
  const hits: Hit[] = command
    ? actions.filter((a) => a.kind === "action" && a.label.toLowerCase().includes(needle))
    : (results.data?.groups ?? []).flatMap((g) => g.items.map((item): Hit => ({ kind: "item", item })));
  const pick = (h: Hit | undefined) => {
    if (!h) return;
    if (h.kind === "action") h.run();
    else openItem(h.item);
  };

  return (
    <D.Root
      open={open}
      onOpenChange={(o) => {
        if (o) setOpen(true);
        else close();
      }}
    >
      <D.Trigger asChild>
        <button
          type="button"
          className="flex h-8 w-72 items-center gap-2 rounded-control border border-border-control bg-ground px-2.5 text-[13px] text-ink-muted hover:border-ink-faint"
        >
          <Search aria-hidden="true" className="size-4" />
          <span className="flex-1 text-left">Search or type &gt; for actions</span>
          <Kbd>/</Kbd>
        </button>
      </D.Trigger>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-[rgb(15_23_42/0.35)]" />
        <D.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[12vh] z-50 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 rounded-[var(--radius-auth)] border border-border bg-surface shadow-[var(--shadow-dialog)] focus:outline-none"
        >
          <D.Title className="sr-only">Search</D.Title>
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <Search aria-hidden="true" className="size-4 text-ink-muted" />
            <input
              aria-label="Search"
              className="flex-1 bg-transparent text-[14px] text-ink outline-none placeholder:text-ink-muted"
              placeholder={project ? `Search ${project.key}: keys, titles, requirements, bugs…` : "Search…"}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((a) => Math.min(a + 1, Math.max(hits.length - 1, 0)));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((a) => Math.max(a - 1, 0));
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  pick(hits[active]);
                }
              }}
            />
            {project ? (
              <Checkbox
                label="All projects"
                checked={everywhere}
                onChange={(e) => {
                  setEverywhere(e.target.checked);
                }}
              />
            ) : null}
          </div>
          <div role="listbox" aria-label="Results" className="max-h-[60vh] overflow-y-auto p-2 text-[13px]">
            {!command && q && results.isFetching && !results.data ? (
              <p className="px-2 py-3 text-ink-secondary">Searching…</p>
            ) : null}
            {!command && q && results.data && hits.length === 0 ? (
              <p className="px-2 py-3 text-ink-secondary">Nothing found for “{q}”.</p>
            ) : null}
            {!text ? (
              <p className="px-2 py-3 text-ink-secondary">
                Type a key (SPARK-TC-12, TC-12, 12), a title, or &gt; for actions.
              </p>
            ) : null}
            {hits.map((h, i) => {
              const prev = hits[i - 1];
              const header =
                h.kind === "item" && (prev?.kind !== "item" || prev.item.type !== h.item.type)
                  ? GROUP_LABEL[h.item.type]
                  : h.kind === "action" && i === 0
                    ? "Actions"
                    : null;
              return (
                <div key={h.kind === "item" ? `${h.item.type}:${h.item.project.key}:${h.item.id}` : h.label}>
                  {header ? (
                    <p className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">
                      {header}
                    </p>
                  ) : null}
                  <div
                    role="option"
                    aria-selected={i === active}
                    tabIndex={-1}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-control px-2 py-1.5",
                      i === active ? "bg-accent-tint text-accent-ink" : "hover:bg-surface-muted",
                    )}
                    onMouseEnter={() => {
                      setActive(i);
                    }}
                    onClick={() => {
                      pick(h);
                    }}
                    onKeyDown={() => undefined}
                  >
                    {h.kind === "action" ? (
                      <span>{h.label}</span>
                    ) : (
                      <>
                        <span className="font-mono text-[12.5px] font-medium">{h.item.key}</span>
                        <span className="min-w-0 flex-1 truncate">{h.item.title}</span>
                        {everywhere ? (
                          <span className="text-xs text-ink-muted">{h.item.project.key}</span>
                        ) : null}
                        {safeUrl(h.item.url) ? <span className="text-xs text-ink-muted">↗</span> : null}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
