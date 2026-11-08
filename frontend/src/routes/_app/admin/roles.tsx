import { createFileRoute } from "@tanstack/react-router";

import { RolesPage } from "@/features/admin/RolesPage";

export const Route = createFileRoute("/_app/admin/roles")({ component: RolesPage });
