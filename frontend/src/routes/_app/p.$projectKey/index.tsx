import { createFileRoute } from "@tanstack/react-router";

import { OverviewPage } from "@/features/reporting/OverviewPage";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/")({
  component: function ProjectOverview() {
    const project = useRouteProject();
    return <OverviewPage key={project.id} project={project} />;
  },
});
