/** Import wizard and exports (docs/06 §4.13, docs/02 §15; M8a). */
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, readCookie, toApiError } from "@/api/client";
import type { components } from "@/api/schema";
import { saveBlob } from "@/features/reporting/api";

export type Uploaded = components["schemas"]["ImportUploaded"];
export type SheetRead = components["schemas"]["SheetRead"];
export type FieldInfo = components["schemas"]["FieldInfo"];
export type Transfer = components["schemas"]["TransferRead"];
export type ImportOptions = components["schemas"]["ImportOptions"];
export type Template = components["schemas"]["TemplateRead"];
export type Entity = Uploaded["entity"];

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export async function uploadImport(pid: string, entity: Entity, file: File): Promise<Uploaded> {
  const form = new FormData();
  form.append("file", file);
  form.append("entity", entity);
  const res = await fetch(`/api/v1/projects/${pid}/imports`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": readCookie("tcms_csrf") ?? "" },
    body: form,
  });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as Uploaded;
}

export async function validateImport(
  transferId: string,
  body: {
    sheet: string;
    mapping: Record<string, string>;
    value_maps: Record<string, Record<string, string>>;
    options: ImportOptions;
  },
) {
  return must(
    (
      await api.POST("/api/v1/data-transfers/{transfer_id}/validate", {
        params: { path: { transfer_id: transferId } },
        body,
      })
    ).data,
  );
}

export async function commitImport(transferId: string) {
  return must(
    (
      await api.POST("/api/v1/data-transfers/{transfer_id}/commit", {
        params: { path: { transfer_id: transferId } },
      })
    ).data,
  );
}

const BUSY = new Set(["validating", "committing", "generating"]);

/** Polls every second while the server works on it. */
export const useImportTransfer = (id: string | null) =>
  useQuery({
    queryKey: ["imports", "transfer", id],
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? 1000 : false),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/data-transfers/{transfer_id}", {
            params: { path: { transfer_id: id ?? "" } },
          })
        ).data,
      ),
  });

export const useTemplates = (pid: string, entity: Entity) =>
  useQuery({
    queryKey: ["imports", pid, "templates", entity],
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/import-mappings", {
            params: { path: { project_id: pid }, query: { entity } },
          })
        ).data,
      ),
  });

export async function saveTemplate(
  pid: string,
  entity: Entity,
  name: string,
  mapping: Record<string, unknown>,
) {
  return must(
    (
      await api.POST("/api/v1/projects/{project_id}/import-mappings", {
        params: { path: { project_id: pid } },
        body: { entity, name, mapping },
      })
    ).data,
  );
}

export function useInvalidateTemplates() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["imports"] });
  };
}

/** Cases (selected ids or the repository filters) or requirement references, as CSV/XLSX. A large file is
 * prepared on the server and announced in the bell. */
export async function exportEntity(
  pid: string,
  body: {
    entity: Entity;
    format: "csv" | "xlsx";
    filters?: Record<string, string>;
    case_ids?: string[];
    version?: "latest" | "approved";
  },
): Promise<{ downloaded: true } | { rows: number }> {
  const res = await fetch(`/api/v1/projects/${pid}/exports`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": readCookie("tcms_csrf") ?? "" },
    body: JSON.stringify(body),
  });
  if (res.status === 202) return { rows: ((await res.json()) as { rows: number }).rows };
  if (!res.ok) throw await toApiError(res);
  const name =
    /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `export.${body.format}`;
  saveBlob(await res.blob(), name);
  return { downloaded: true };
}
