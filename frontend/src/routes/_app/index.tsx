import { createFileRoute, Navigate } from "@tanstack/react-router";

import { useProjects } from "@/api/queries";
import { Skeleton } from "@/components/common/feedback";
import { lastProject } from "@/lib/permissions";

/** Until My Work exists (M4): last project's activity, else the project list (review K5). */
export const Route = createFileRoute("/_app/")({
  component: function Home() {
    const projects = useProjects();
    if (projects.isPending) return <Skeleton />;
    const remembered = lastProject();
    const target =
      projects.data?.find((p) => p.key === remembered) ??
      (projects.data?.length === 1 ? projects.data[0] : undefined);
    return target ? (
      <Navigate to="/p/$projectKey/activity" params={{ projectKey: target.key }} replace />
    ) : (
      <Navigate to="/projects" replace />
    );
  },
});
