import { createFileRoute } from "@tanstack/react-router";

import { SystemPage } from "@/features/admin/SystemPage";

export const Route = createFileRoute("/_app/admin/system")({ component: SystemPage });
