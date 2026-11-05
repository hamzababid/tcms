import { createFileRoute } from "@tanstack/react-router";

import { MyWorkPage } from "@/features/execution/MyWorkPage";

export const Route = createFileRoute("/_app/my-work")({
  component: MyWorkPage,
});
