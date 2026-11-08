import { createFileRoute, Outlet } from "@tanstack/react-router";

import { AdminTabs } from "@/features/admin/AdminTabs";

export const Route = createFileRoute("/_app/admin")({
  component: function AdminLayout() {
    return (
      <div className="flex min-h-full flex-col">
        <AdminTabs />
        <Outlet />
      </div>
    );
  },
});
