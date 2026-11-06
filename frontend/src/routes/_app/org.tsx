import { createFileRoute } from "@tanstack/react-router";

import { OrgDashboardPage } from "@/features/reporting/OrgDashboardPage";

export const Route = createFileRoute("/_app/org")({
  component: OrgDashboardPage,
});
