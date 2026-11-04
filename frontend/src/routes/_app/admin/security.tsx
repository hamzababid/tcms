import { createFileRoute } from "@tanstack/react-router";

import { SecurityPage } from "@/features/admin/AdminPages";

export const Route = createFileRoute("/_app/admin/security")({ component: SecurityPage });
