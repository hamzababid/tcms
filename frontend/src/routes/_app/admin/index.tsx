import { createFileRoute, Navigate } from "@tanstack/react-router";

import { useMe } from "@/api/queries";
import { EmptyState, Skeleton } from "@/components/common/feedback";
import { adminTabsFor } from "@/features/admin/AdminTabs";

export const Route = createFileRoute("/_app/admin/")({
  component: function AdminIndex() {
    const me = useMe();
    if (me.isPending) return <Skeleton />;
    const first = adminTabsFor(me.data?.org_permissions ?? [])[0];
    if (!first)
      return (
        <div className="p-6">
          <EmptyState text="Administration is for organization administrators." />
        </div>
      );
    return <Navigate to={first.to} replace />;
  },
});
