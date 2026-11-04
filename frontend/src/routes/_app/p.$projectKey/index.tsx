import { createFileRoute, Navigate } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/p/$projectKey/")({
  component: function ProjectHome() {
    const { projectKey } = Route.useParams();
    return <Navigate to="/p/$projectKey/activity" params={{ projectKey }} replace />;
  },
});
