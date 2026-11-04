import type { ReactNode } from "react";

import { PRODUCT_NAME } from "./config";

/**
 * Application shell (docs/07 §3). Navigation, project switcher, search, notifications and the user
 * menu are added by the features that provide them; nothing is rendered before it works.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <nav aria-label="Primary" className="flex w-60 shrink-0 flex-col bg-sidebar px-3 py-4 text-sidebar-ink">
        <div className="px-2 text-base font-semibold text-white">{PRODUCT_NAME}</div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="h-14 shrink-0 border-b border-border bg-surface" />
        <main id="main" className="min-h-0 flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
