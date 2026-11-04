import { createFileRoute } from "@tanstack/react-router";

import { ResetPage } from "@/features/auth/PasswordPages";

export const Route = createFileRoute("/reset/$token")({
  component: function Reset() {
    return <ResetPage token={Route.useParams().token} />;
  },
});
