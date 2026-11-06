import { createFileRoute, Navigate } from "@tanstack/react-router";

/** Sign-in lands on My Work (docs/02 §3.3 step 7, review K5; M4). */
export const Route = createFileRoute("/_app/")({
  component: function Home() {
    return <Navigate to="/my-work" replace />;
  },
});
