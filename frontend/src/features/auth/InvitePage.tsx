import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { ErrorState, Skeleton } from "@/components/common/feedback";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";

import { AuthCard, browserTimeZone, FormError } from "./AuthCard";
import { newPasswordSchema, PASSWORD_HINT, serverPasswordError } from "./PasswordPages";

const schema = newPasswordSchema.and(
  z.object({ display_name: z.string().trim().min(1, "Enter your name").max(100) }),
);
type Values = z.infer<typeof schema>;

export function InvitePage({ token }: { token: string }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const info = useQuery({
    queryKey: ["invitation", token],
    retry: false,
    queryFn: async () =>
      (await api.GET("/api/v1/auth/invitations/{token}", { params: { path: { token } } })).data,
  });
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: "", password: "", confirm: "" },
  });
  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      const { data } = await api.POST("/api/v1/auth/invitations/{token}/accept", {
        params: { path: { token } },
        body: { display_name: v.display_name, password: v.password, time_zone: browserTimeZone() },
      });
      qc.clear();
      await navigate({ to: data?.mfa_enrollment_required ? "/setup-mfa" : "/" });
    } catch (e) {
      setError(serverPasswordError(e));
    }
  });

  if (info.isPending)
    return (
      <AuthCard title="Accept invitation">
        <Skeleton rows={2} />
      </AuthCard>
    );
  if (info.isError || !info.data)
    return (
      <AuthCard title="Invitation">
        <ErrorState error={info.error} />
      </AuthCard>
    );
  const inv = info.data;
  return (
    <AuthCard
      title={`Join ${inv.organization.name}`}
      subtitle={`${inv.inviter ?? "An administrator"} invited ${inv.email}${inv.project ? ` to ${inv.project.name}` : ""}.`}
    >
      <form className="flex flex-col gap-[18px]" onSubmit={(e) => void onSubmit(e)} noValidate>
        <FormError message={error} />
        <Field label="Your name" required error={form.formState.errors.display_name?.message}>
          {(p) => (
            <Input
              {...p}
              className="h-10 px-3"
              autoComplete="name"
              autoFocus
              {...form.register("display_name")}
            />
          )}
        </Field>
        <Field label="Password" required hint={PASSWORD_HINT} error={form.formState.errors.password?.message}>
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
        <Field label="Confirm password" required error={form.formState.errors.confirm?.message}>
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
        <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
          Accept and continue
        </Button>
      </form>
    </AuthCard>
  );
}
