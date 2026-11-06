import { createFileRoute } from "@tanstack/react-router";

import { ReleasesPage } from "@/features/reporting/ReleasesPage";

import { useRouteProject } from "../p.$projectKey";

export const Route = createFileRoute("/_app/p/$projectKey/releases/")({
  component: function Releases() {
    return <ReleasesPage project={useRouteProject()} />;
  },
});
