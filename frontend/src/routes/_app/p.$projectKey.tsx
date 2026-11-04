import { createFileRoute, Outlet } from "@tanstack/react-router";
import { useEffect } from "react";

import { useProjects } from "@/api/queries";
import { EmptyState, Skeleton } from "@/components/common/feedback";
import { rememberProject } from "@/lib/permissions";

export const Route = createFileRoute("/_app/p/$projectKey")({
  component: function ProjectLayout() {
    const { projectKey } = Route.useParams();
    const projects = useProjects();
    const project = projects.data?.find((p) => p.key === projectKey);
    useEffect(() => {
      if (project) rememberProject(project.key);
    }, [project]);
    if (projects.isPending) return <Skeleton />;
    if (!project) return <EmptyState text={`Project ${projectKey} was not found or you are not a member.`} />;
    return <Outlet />;
  },
});

export function useRouteProject() {
  const { projectKey } = Route.useParams();
  const project = useProjects().data?.find((p) => p.key === projectKey);
  if (!project) throw new Error("project layout renders children only when the project exists");
  return project;
}
