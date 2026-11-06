import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnFiltersState, SortingState } from "@tanstack/react-table";
import { Bookmark, ChevronDown } from "lucide-react";
import { useState } from "react";

import { ApiError, api } from "@/api/client";
import type { components } from "@/api/schema";
import { errorMessage, useToast } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input } from "@/components/ui/field";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";

export type SavedView = components["schemas"]["SavedViewRead"];
export type ViewEntity = "test_case" | "test_run" | "test_plan" | "test_cycle" | "bug" | "requirement";

interface UiState {
  filters: ColumnFiltersState;
  sorting: SortingState;
  extra?: Record<string, unknown>;
}

export interface ViewsState {
  list: SavedView[];
  current: SavedView | null;
  apply: (v: SavedView | null) => void;
  save: (name: string, shared: boolean, isDefault: boolean) => Promise<void>;
  setDefault: (v: SavedView, on: boolean) => Promise<void>;
  remove: (v: SavedView) => Promise<void>;
}

/**
 * Saved views of one list (docs/02 §12, US-132). The screen's own filter state is kept in the reserved
 * `_ui` filter; `params` (when given) are the list's API query parameters, so the server can resolve the
 * view too (the plan's "Add cases › Saved view").
 */
export function useSavedViews(
  projectId: string,
  entity: ViewEntity,
  state: {
    filters: ColumnFiltersState;
    setFilters: (f: ColumnFiltersState) => void;
    sorting: SortingState;
    setSorting: (s: SortingState) => void;
    extra?: Record<string, unknown>;
    setExtra?: (e: Record<string, unknown>) => void;
    params?: Record<string, string>;
  },
): ViewsState {
  const qc = useQueryClient();
  const key = ["saved-views", projectId, entity];
  const views = useQuery({
    queryKey: key,
    queryFn: async () =>
      (
        await api.GET("/api/v1/projects/{project_id}/saved-views", {
          params: { path: { project_id: projectId }, query: { entity_type: entity } },
        })
      ).data ?? [],
  });
  const [current, setCurrent] = useState<SavedView | null>(null);
  const [applied, setApplied] = useState(false);
  const apply = (v: SavedView | null) => {
    setCurrent(v);
    if (!v) {
      state.setFilters([]);
      return;
    }
    try {
      const ui = JSON.parse(v.definition.filters?._ui ?? "{}") as Partial<UiState>;
      state.setFilters(ui.filters ?? []);
      state.setSorting(ui.sorting ?? []);
      if (ui.extra && state.setExtra) state.setExtra(ui.extra);
    } catch {
      state.setFilters([]);
    }
  };
  // Open the list with the default view: my private default first, then the project's (docs/02 §12).
  // Adjusted during render once the views arrive (no effect: React's "adjusting state" pattern).
  if (!applied && views.data) {
    setApplied(true);
    const d = views.data.find((v) => v.is_default);
    if (d) apply(d);
  }
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const definition = () => ({
    filters: {
      ...(state.params ?? {}),
      _ui: JSON.stringify({
        filters: state.filters,
        sorting: state.sorting,
        extra: state.extra,
      } satisfies UiState),
    },
    sort: null,
    columns: null,
  });
  return {
    list: views.data ?? [],
    current,
    apply,
    save: async (name, shared, isDefault) => {
      const { data } = await api.POST("/api/v1/projects/{project_id}/saved-views", {
        params: { path: { project_id: projectId } },
        body: {
          entity_type: entity,
          name,
          visibility: shared ? "project" : "private",
          definition: definition(),
          is_default: isDefault,
        },
      });
      await refresh();
      setCurrent(data ?? null);
    },
    setDefault: async (v, on) => {
      await api.PATCH("/api/v1/saved-views/{view_id}", {
        params: { path: { view_id: v.id } },
        body: { is_default: on },
      });
      await refresh();
    },
    remove: async (v) => {
      await api.DELETE("/api/v1/saved-views/{view_id}", { params: { path: { view_id: v.id } } });
      if (current?.id === v.id) setCurrent(null);
      await refresh();
    },
  };
}

/** "Views ▾": apply a saved view, save the current filters, set a default, delete (US-132). */
export function SavedViewsMenu({ views, canShare }: { views: ViewsState; canShare: boolean }) {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const run = (p: Promise<void>, message: string) => {
    p.then(() => {
      toast(message);
    }).catch((e: unknown) => {
      toast(errorMessage(e), "error");
    });
  };
  const cur = views.current;
  return (
    <>
      <Menu>
        <MenuTrigger asChild>
          <Button variant="secondary" size="xs" aria-label={cur ? `Saved views: ${cur.name}` : "Saved views"}>
            <Bookmark aria-hidden="true" className="size-3.5" />
            {cur ? cur.name : "Views"}
            <ChevronDown aria-hidden="true" className="size-3.5" />
          </Button>
        </MenuTrigger>
        <MenuContent align="start">
          <MenuItem
            onSelect={() => {
              views.apply(null);
            }}
          >
            All (no view)
          </MenuItem>
          {views.list.map((v) => (
            <MenuItem
              key={v.id}
              onSelect={() => {
                views.apply(v);
              }}
            >
              <span className="flex-1">{v.name}</span>
              <span className="text-[11px] text-ink-muted">
                {v.visibility === "project" ? "shared" : "private"}
                {v.is_default ? " · default" : ""}
              </span>
            </MenuItem>
          ))}
          <MenuSeparator />
          <MenuItem
            onSelect={() => {
              setSaving(true);
            }}
          >
            Save current view…
          </MenuItem>
          {cur?.mine ? (
            <>
              <MenuItem
                onSelect={() => {
                  run(
                    views.setDefault(cur, !cur.is_default),
                    cur.is_default ? "No longer the default" : "Set as default",
                  );
                }}
              >
                {cur.is_default ? "Unset default" : "Set as default"}
              </MenuItem>
              <MenuItem
                danger
                onSelect={() => {
                  run(views.remove(cur), `Deleted ${cur.name}`);
                }}
              >
                Delete “{cur.name}”
              </MenuItem>
            </>
          ) : null}
        </MenuContent>
      </Menu>
      {saving ? (
        <SaveViewDialog
          canShare={canShare}
          onSave={views.save}
          onClose={() => {
            setSaving(false);
          }}
        />
      ) : null}
    </>
  );
}

function SaveViewDialog({
  canShare,
  onSave,
  onClose,
}: {
  canShare: boolean;
  onSave: (name: string, shared: boolean, isDefault: boolean) => Promise<void>;
  onClose: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="Save view"
      description="Saves the current filters and sort of this list."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="save-view" disabled={!name.trim()}>
            Save
          </Button>
        </>
      }
    >
      <form
        id="save-view"
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(name.trim(), shared, isDefault)
            .then(() => {
              toast(`Saved ${name.trim()}`);
              onClose();
            })
            .catch(setError);
        }}
      >
        <Field
          label="Name"
          required
          error={error instanceof ApiError ? (error.errors[0]?.message ?? errorMessage(error)) : undefined}
        >
          {(p) => (
            <Input
              {...p}
              maxLength={100}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          )}
        </Field>
        {canShare ? (
          <Checkbox
            label="Share with the project"
            checked={shared}
            onChange={(e) => {
              setShared(e.target.checked);
            }}
          />
        ) : null}
        <Checkbox
          label={shared ? "Open this list with this view for everyone" : "Open this list with this view"}
          checked={isDefault}
          onChange={(e) => {
            setIsDefault(e.target.checked);
          }}
        />
      </form>
    </Dialog>
  );
}
