import { createFileRoute } from "@tanstack/react-router";

/** Home. Sign-in and the post-login landing page arrive in M1 (docs/ops/00-review.md K5). */
export const Route = createFileRoute("/")({
  component: () => null,
});
