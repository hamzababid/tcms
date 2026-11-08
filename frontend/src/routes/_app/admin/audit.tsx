import { createFileRoute } from "@tanstack/react-router";

import { OrgAuditLogPage } from "@/features/admin/AuditLog";

export const Route = createFileRoute("/_app/admin/audit")({ component: OrgAuditLogPage });
