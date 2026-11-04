import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { api, ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";

import { AuthCard, FormError } from "./AuthCard";

export function MfaPage({ returnTo }: { returnTo: string | undefined }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [useRecovery, setUseRecovery] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(code: string) {
    setBusy(true);
    setError(null);
    try {
      await api.POST("/api/v1/auth/mfa/verify", { body: useRecovery ? { recovery_code: code } : { code } });
      qc.clear();
      await navigate({ to: returnTo ?? "/" });
    } catch (e) {
      if (e instanceof ApiError && e.code === "session_expired") {
        setError(e.detail ?? "Your sign-in expired. Sign in again.");
      } else {
        setError("The verification code is not valid.");
      }
      setValue("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Two-step verification"
      subtitle={
        useRecovery
          ? "Enter one of your recovery codes."
          : "Enter the 6-digit code from your authenticator app."
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(value.trim());
        }}
      >
        <FormError message={error} />
        <Field label={useRecovery ? "Recovery code" : "Verification code"}>
          {(p) => (
            <Input
              {...p}
              autoFocus
              autoComplete="one-time-code"
              inputMode={useRecovery ? "text" : "numeric"}
              maxLength={useRecovery ? 20 : 6}
              className="font-mono tracking-widest"
              value={value}
              onChange={(e) => {
                const v = useRecovery ? e.target.value : e.target.value.replace(/\D/g, "");
                setValue(v);
                if (!useRecovery && v.length === 6) void submit(v); // auto-submit on 6 digits (docs/07 §5.1)
              }}
            />
          )}
        </Field>
        <Button type="submit" disabled={busy || value.length === 0}>
          Verify
        </Button>
        <Button
          variant="link"
          onClick={() => {
            setUseRecovery((r) => !r);
            setValue("");
          }}
        >
          {useRecovery ? "Use the authenticator code" : "Use a recovery code"}
        </Button>
        {error?.includes("Sign in again") ? (
          <Link to="/login" className="text-center text-sm text-accent hover:underline">
            Back to sign in
          </Link>
        ) : null}
      </form>
    </AuthCard>
  );
}
