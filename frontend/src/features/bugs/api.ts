/**
 * Bug links (docs/02 §8, docs/06 §4.8; ADR-023): references to bugs in each team's own tracker.
 * TanStack Query only; keys live here.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";

export type BugLink = components["schemas"]["BugLinkRead"];
export type BugSummary = components["schemas"]["BugSummaryRead"];
export type RetestResponse = components["schemas"]["RetestResponse"];

export interface BugQuery {
  q?: string;
  cycle_id?: string;
  failing?: boolean;
  page: number;
  page_size: number;
}

export const bugKeys = {
  all: ["bugs"] as const,
  run: (id: string) => ["bugs", "run", id] as const,
  cycle: (id: string, recent = false) => ["bugs", "cycle", id, recent] as const,
  testCase: (id: string) => ["bugs", "case", id] as const,
  list: (pid: string, query: BugQuery) => ["bugs", "project", pid, query] as const,
  reference: (pid: string, ref: string) => ["bugs", "project", pid, "ref", ref] as const,
};

function must<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("empty response");
  return data;
}

export const useRunBugLinks = (runId: string | undefined) =>
  useQuery({
    queryKey: bugKeys.run(runId ?? ""),
    enabled: Boolean(runId),
    queryFn: async () =>
      must(
        (await api.GET("/api/v1/runs/{run_id}/bug-links", { params: { path: { run_id: runId ?? "" } } }))
          .data,
      ),
  });

export const useCycleBugLinks = (cycleId: string | undefined, recent = false) =>
  useQuery({
    queryKey: bugKeys.cycle(cycleId ?? "", recent),
    enabled: Boolean(cycleId),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/cycles/{cycle_id}/bug-links", {
            params: { path: { cycle_id: cycleId ?? "" }, query: { recent } },
          })
        ).data,
      ),
  });

export const useCaseBugLinks = (caseId: string | undefined) =>
  useQuery({
    queryKey: bugKeys.testCase(caseId ?? ""),
    enabled: Boolean(caseId),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/test-cases/{case_id}/bug-links", {
            params: { path: { case_id: caseId ?? "" } },
          })
        ).data,
      ),
  });

export const useBugs = (pid: string, query: BugQuery) =>
  useQuery({
    queryKey: bugKeys.list(pid, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/bugs", {
            params: { path: { project_id: pid }, query },
          })
        ).data,
      ),
  });

export const useReferenceLinks = (pid: string, reference: string | null) =>
  useQuery({
    queryKey: bugKeys.reference(pid, reference ?? ""),
    enabled: Boolean(reference),
    queryFn: async () =>
      must(
        (
          await api.GET("/api/v1/projects/{project_id}/bugs/links", {
            params: { path: { project_id: pid }, query: { reference: reference ?? "" } },
          })
        ).data,
      ),
  });

export interface LinkInput {
  reference: string;
  url?: string | null;
  title?: string | null;
}

export async function linkBugToResult(resultId: string, body: LinkInput & { step_id?: string | null }) {
  return must(
    (
      await api.POST("/api/v1/results/{result_id}/bug-links", {
        params: { path: { result_id: resultId } },
        body: {
          reference: body.reference,
          url: body.url ?? null,
          title: body.title ?? null,
          step_id: body.step_id ?? null,
        },
      })
    ).data,
  );
}

export async function linkBugToCase(caseId: string, body: LinkInput) {
  return must(
    (
      await api.POST("/api/v1/test-cases/{case_id}/bug-links", {
        params: { path: { case_id: caseId } },
        body: { reference: body.reference, url: body.url ?? null, title: body.title ?? null },
      })
    ).data,
  );
}

export async function updateBugLink(id: string, body: { url?: string | null; title?: string | null }) {
  return must(
    (await api.PATCH("/api/v1/bug-links/{link_id}", { params: { path: { link_id: id } }, body })).data,
  );
}

export async function removeBugLink(id: string): Promise<void> {
  await api.DELETE("/api/v1/bug-links/{link_id}", { params: { path: { link_id: id } } });
}

export async function requestRetest(
  pid: string,
  reference: string,
  dryRun: boolean,
): Promise<RetestResponse> {
  return must(
    (
      await api.POST("/api/v1/projects/{project_id}/bugs/retest", {
        params: { path: { project_id: pid } },
        body: { reference, dry_run: dryRun },
      })
    ).data,
  );
}

export async function getBugReport(resultId: string, stepId?: string | null): Promise<string> {
  const query = stepId ? { step_id: stepId } : {};
  return must(
    (
      await api.GET("/api/v1/results/{result_id}/bug-report", {
        params: { path: { result_id: resultId }, query },
      })
    ).data,
  ).text;
}

/** After a bug-link write: every bug list, plus runs and cycles (retest flags). */
export function useInvalidateBugs() {
  const qc = useQueryClient();
  return (opts: { runs?: boolean } = {}) => {
    void qc.invalidateQueries({ queryKey: bugKeys.all });
    if (opts.runs) {
      void qc.invalidateQueries({ queryKey: ["run"] });
      void qc.invalidateQueries({ queryKey: ["cycle"] });
      void qc.invalidateQueries({ queryKey: ["me", "work"] });
    }
  };
}

/** Distinct references in order of first appearance (chips). */
export function distinctReferences(links: BugLink[]): BugLink[] {
  const seen = new Map<string, BugLink>();
  for (const l of links) {
    const k = l.reference.toUpperCase();
    if (!seen.has(k)) seen.set(k, l);
  }
  return [...seen.values()];
}

/** The URL to open: only http(s) is ever rendered as a link (AC-BUG-05). */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return /^https?:\/\//i.test(url) ? url : null;
}
