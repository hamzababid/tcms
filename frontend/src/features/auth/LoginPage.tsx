import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api, ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";

import { AuthCard, FormError } from "./AuthCard";

const schema = z.object({
  email: z.string().min(1, "Enter your email"),
  password: z.string().min(1, "Enter your password"),
});
type Values = z.infer<typeof schema>;

export function LoginPage({ returnTo }: { returnTo: string | undefined }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const { data } = await api.POST("/api/v1/auth/login", { body: values });
      qc.clear();
      if (data?.mfa_required) await navigate({ to: "/login/mfa", search: { returnTo } });
      else if (data?.mfa_enrollment_required) await navigate({ to: "/setup-mfa" });
      else await navigate({ to: returnTo ?? "/" });
    } catch (e) {
      // Generic messages only (docs/02 §3.3): never reveal whether the email exists.
      setError(
        e instanceof ApiError && e.status !== 401 ? (e.detail ?? e.code) : "Email or password is incorrect.",
      );
    }
  });

  return (
    <AuthCard title="Sign in">
      <form onSubmit={(e) => void onSubmit(e)} className="flex flex-col gap-4" noValidate>
        <FormError message={error} />
        <Field label="Email" error={form.formState.errors.email?.message}>
          {(p) => <Input {...p} type="email" autoComplete="username" autoFocus {...form.register("email")} />}
        </Field>
        <Field label="Password" error={form.formState.errors.password?.message}>
          {(p) => (
            <Input {...p} type="password" autoComplete="current-password" {...form.register("password")} />
          )}
        </Field>
        <Button type="submit" disabled={form.formState.isSubmitting}>
          Sign in
        </Button>
        <Link to="/forgot" className="text-center text-sm text-accent hover:underline">
          Forgot password?
        </Link>
      </form>
    </AuthCard>
  );
}
