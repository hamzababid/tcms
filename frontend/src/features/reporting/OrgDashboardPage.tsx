/** Organization dashboard (docs/07 §5.2; FR-WS-008, US-146): one row per project. Org Admins see every
 * project; others see the projects they belong to. "Open crit/high" became failed runs (ADR-023). */
import { Link } from "@tanstack/react-router";

import { EmptyState, ErrorState, Page, Skeleton } from "@/components/common/feedback";
import { ProgressBar } from "@/components/common/ProgressBar";
import { formatCount, formatDateTime, formatRate } from "@/lib/format";

import { useOrgDashboard } from "./api";

export function OrgDashboardPage() {
  const d = useOrgDashboard();
  return (
    <Page
      title="Organization dashboard"
      subtitle="Planned and active cycles of every project you can see."
      width="6xl"
    >
      {d.isPending ? (
        <Skeleton rows={4} />
      ) : d.isError ? (
        <ErrorState error={d.error} onRetry={() => void d.refetch()} />
      ) : d.data.projects.length === 0 ? (
        <EmptyState text="You are not a member of any active project." />
      ) : (
        <div className="overflow-x-auto rounded-card border border-border bg-surface">
          <table aria-label="Projects" className="w-full text-left text-[13px]">
            <thead className="bg-ground text-xs text-ink-secondary">
              <tr>
                <th className="px-4 py-2 font-medium">Project</th>
                <th className="px-3 py-2 text-right font-medium">Active cycles</th>
                <th className="w-64 px-3 py-2 font-medium">Execution progress</th>
                <th className="px-3 py-2 font-medium">Pass rate</th>
                <th className="px-3 py-2 text-right font-medium">Failed runs</th>
                <th className="px-3 py-2 text-right font-medium">Bugs on failing runs</th>
                <th className="px-3 py-2 font-medium">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {d.data.projects.map((p) => (
                <tr key={p.project.id} className="h-12 border-t border-border">
                  <td className="px-4">
                    <Link
                      to="/p/$projectKey"
                      params={{ projectKey: p.project.key }}
                      className="font-medium text-accent-ink hover:underline"
                    >
                      {p.project.key}
                    </Link>{" "}
                    <span className="text-ink-secondary">{p.project.title}</span>
                  </td>
                  <td className="tabular px-3 text-right">{formatCount(p.active_cycles)}</td>
                  <td className="px-3">
                    <ProgressBar counts={p.summary} />
                    <div className="tabular mt-1 text-xs text-ink-secondary">
                      {formatRate(p.summary.execution_progress)}
                    </div>
                  </td>
                  <td className="tabular px-3">{formatRate(p.summary.pass_rate)}</td>
                  <td className="tabular px-3 text-right">{formatCount(p.failed)}</td>
                  <td className="tabular px-3 text-right">{formatCount(p.bugs_on_failing_runs)}</td>
                  <td className="px-3 text-ink-secondary">{formatDateTime(p.last_activity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}
