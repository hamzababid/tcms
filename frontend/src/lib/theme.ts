import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useSyncExternalStore } from "react";

import { api } from "@/api/client";
import { keys, useMe } from "@/api/queries";

/**
 * Colour theme (docs/07 §6.1): the user picks Light, Dark or System (follow the device). The choice is
 * saved with the profile (`PATCH /auth/me {theme}`) so it follows the user to other browsers, and in
 * localStorage so public/theme-init.js can apply it before the first paint.
 */
export type ThemeChoice = "light" | "dark" | "system";
export type Theme = "light" | "dark";

export const THEME_KEY = "assay.theme";
export const THEME_CHOICES: { value: ThemeChoice; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

const darkQuery = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

export function isChoice(v: unknown): v is ThemeChoice {
  return v === "light" || v === "dark" || v === "system";
}

export function storedChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return isChoice(v) ? v : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(choice: ThemeChoice, systemDark = darkQuery()?.matches ?? false): Theme {
  return choice === "system" ? (systemDark ? "dark" : "light") : choice;
}

const listeners = new Set<() => void>();
const emit = () => {
  for (const l of listeners) l();
};

/** Applies a choice to the page now and remembers it in this browser. */
export function applyTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(THEME_KEY, choice);
  } catch {
    /* not remembered in this browser; the profile still has it */
  }
  const theme = resolveTheme(choice);
  const root = document.documentElement;
  // Swap all colours at once: without this, every element with a colour transition fades separately.
  root.dataset.themeSwitching = "";
  root.dataset.theme = theme;
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      delete root.dataset.themeSwitching;
    });
  });
  // The browser's address bar takes the page colour of the theme (the --ground token).
  const ground = getComputedStyle(root).getPropertyValue("--ground").trim();
  if (ground) document.querySelector('meta[name="theme-color"]')?.setAttribute("content", ground);
  emit();
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  // "System" follows the device when it switches (for example at sunset).
  const mq = darkQuery();
  const onSystem = () => {
    if (storedChoice() === "system") applyTheme("system");
  };
  mq?.addEventListener("change", onSystem);
  return () => {
    listeners.delete(onChange);
    mq?.removeEventListener("change", onSystem);
  };
}

/** The theme on screen now (signed-out pages too). */
export function useResolvedTheme(): Theme {
  return resolveTheme(useSyncExternalStore(subscribe, storedChoice, (): ThemeChoice => "system"));
}

/** The current choice and theme, and a setter that applies at once and saves to the profile. */
export function useTheme(): {
  choice: ThemeChoice;
  theme: Theme;
  setChoice: (c: ThemeChoice) => Promise<void>;
} {
  const qc = useQueryClient();
  const choice = useSyncExternalStore(subscribe, storedChoice, (): ThemeChoice => "system");
  const theme = resolveTheme(choice);
  const setChoice = useCallback(
    async (c: ThemeChoice) => {
      applyTheme(c);
      await api.PATCH("/api/v1/auth/me", { body: { theme: c } });
      await qc.invalidateQueries({ queryKey: keys.me });
    },
    [qc],
  );
  return { choice, theme, setChoice };
}

/** After sign-in the profile's choice wins over this browser's (a new device picks up the setting). */
export function useThemeFromProfile(): void {
  const saved = useMe().data?.theme;
  useEffect(() => {
    if (isChoice(saved) && saved !== storedChoice()) applyTheme(saved);
  }, [saved]);
}
