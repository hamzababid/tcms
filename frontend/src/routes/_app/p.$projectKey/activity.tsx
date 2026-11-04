import { createFileRoute } from "@tanstack/react-router";

import { ActivityPage } from "@/features/projects/ActivityPage";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/activity")({
  component: function Activity() {
    return <ActivityPage project={useRouteProject()} />;
  },
});
