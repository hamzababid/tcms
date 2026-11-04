import { createFileRoute } from "@tanstack/react-router";

import { ForgotPage } from "@/features/auth/PasswordPages";

export const Route = createFileRoute("/forgot")({ component: ForgotPage });
