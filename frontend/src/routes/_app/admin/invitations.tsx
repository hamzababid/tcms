import { createFileRoute } from "@tanstack/react-router";

import { InvitationsPage } from "@/features/admin/AdminPages";

export const Route = createFileRoute("/_app/admin/invitations")({ component: InvitationsPage });
