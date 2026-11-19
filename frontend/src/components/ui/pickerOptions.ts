import type { ComboOption } from "./combobox";

/**
 * Options for the searchable pickers built from the lists that grow large (docs/07 §4.5). Folders show
 * their path as the hint, so "Login" under two areas can be told apart and found by area name.
 */
export function folderOptions(
  folders: { id: string; name: string; parent_id?: string | null; archived?: boolean }[],
  keep?: string,
): ComboOption[] {
  const byId = new Map(folders.map((f) => [f.id, f]));
  const path = (id: string | null | undefined): string[] => {
    const out: string[] = [];
    for (let f = id ? byId.get(id) : undefined; f; f = f.parent_id ? byId.get(f.parent_id) : undefined) {
      out.unshift(f.name);
      if (out.length > 20) break; // never loop on bad data
    }
    return out;
  };
  return folders
    .filter((f) => !f.archived || f.id === keep)
    .map((f) => {
      const parents = path(f.parent_id).join(" › ");
      return {
        value: f.id,
        label: f.name,
        ...(parents ? { hint: parents } : {}),
        ...(f.archived ? { keywords: "archived" } : {}),
      };
    });
}

export function peopleOptions(
  people: { id: string; display_name: string; email?: string | null }[],
): ComboOption[] {
  return [...people]
    .sort((a, b) => a.display_name.localeCompare(b.display_name))
    .map((u) => ({ value: u.id, label: u.display_name, ...(u.email ? { hint: u.email } : {}) }));
}

export function projectOptions(projects: { id: string; key: string; name: string }[]): ComboOption[] {
  return [...projects]
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((p) => ({ value: p.id, label: `${p.key} · ${p.name}` }));
}
