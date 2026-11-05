import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api, ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input } from "@/components/ui/field";

import { AuthCard, FormError } from "./AuthCard";

export const PASSWORD_HINT = "12–128 characters. Not your email and not a common password.";

export const newPasswordSchema = z
  .object({ password: z.string().min(12, "Use at least 12 characters").max(128), confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "Passwords do not match", path: ["confirm"] });

export function serverPasswordError(e: unknown): string {
  if (e instanceof ApiError) return e.errors[0]?.message ?? e.detail ?? e.code;
  return "Something went wrong";
}

export function ForgotPage() {
  const [sent, setSent] = useState(false);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <AuthCard title="Reset your password" subtitle="We'll email you a link that works once, for 60 minutes.">
      {sent ? (
        <div className="flex flex-col gap-4 text-sm text-ink-secondary">
          <p role="status">If an account exists for {email}, a reset link is on its way.</p>
          <Link to="/login" className="text-link hover:underline">
            Back to sign in
          </Link>
        </div>
      ) : (
        <form
          className="flex flex-col gap-[18px]"
          onSubmit={(e) => {
            e.preventDefault();
            void api
              .POST("/api/v1/auth/password/forgot", { body: { email } })
              .then(() => {
                setSent(true);
              })
              .catch((err: unknown) => {
                setError(err instanceof ApiError ? (err.detail ?? err.code) : "Try again.");
              });
          }}
        >
          <FormError message={error} />
          <Field label="Email">
            {(p) => (
              <Input
                {...p}
                className="h-10 px-3"
                type="email"
                required
                autoFocus
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                }}
              />
            )}
          </Field>
          <Button type="submit" size="lg" disabled={!email}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthCard>
  );
}

const resetSchema = newPasswordSchema.and(z.object({ revoke: z.boolean() }));
type ResetValues = z.infer<typeof resetSchema>;

export function ResetPage({ token }: { token: string }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<ResetValues>({
    resolver: zodResolver(resetSchema),
    defaultValues: { password: "", confirm: "", revoke: false },
  });
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      await api.POST("/api/v1/auth/password/reset", {
        body: { token, new_password: v.password, revoke_api_tokens: v.revoke },
      });
      await navigate({ to: "/login" });
    } catch (e) {
      setError(serverPasswordError(e));
    }
  });
  return (
    <AuthCard title="Choose a new password" subtitle="All your sessions will be signed out.">
      <form className="flex flex-col gap-[18px]" onSubmit={(e) => void onSubmit(e)} noValidate>
        <FormError message={error} />
        <Field label="New password" hint={PASSWORD_HINT} error={form.formState.errors.password?.message}>
          {(p) => (
            <Input
              {...p}
              className="h-10 px-3"
              type="password"
              autoComplete="new-password"
              {...form.register("password")}
            />
          )}
        </Field>
        <Field label="Confirm password" error={form.formState.errors.confirm?.message}>
          {(p) => (
            <Input
              {...p}
              className="h-10 px-3"
              type="password"
              autoComplete="new-password"
              {...form.register("confirm")}
            />
          )}
        </Field>
        <Checkbox label="Also revoke my API tokens" {...form.register("revoke")} />
        <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
          Set password
        </Button>
      </form>
    </AuthCard>
  );
}
