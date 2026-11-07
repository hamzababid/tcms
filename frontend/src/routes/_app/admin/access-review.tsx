import { createFileRoute } from "@tanstack/react-router";

import { AccessReviewPage } from "@/features/admin/AccessReviewPage";

export const Route = createFileRoute("/_app/admin/access-review")({ component: AccessReviewPage });
