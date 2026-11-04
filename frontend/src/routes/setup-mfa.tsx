import { createFileRoute, useNavigate } from "@tanstack/react-router";

import { AuthCard } from "@/features/auth/AuthCard";
import { MfaEnrollment } from "@/features/auth/MfaEnrollment";

/** Forced enrolment (AC-AUTH-04): shown before any other page when MFA is required. */
export const Route = createFileRoute("/setup-mfa")({
  component: function SetupMfa() {
    const navigate = useNavigate();
    return (
      <AuthCard
        title="Set up two-step verification"
        subtitle="Required for your account before you continue."
      >
        <MfaEnrollment onDone={() => void navigate({ to: "/" })} />
      </AuthCard>
    );
  },
});
