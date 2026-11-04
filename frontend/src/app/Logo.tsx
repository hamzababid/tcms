import { PRODUCT_NAME } from "./config";

/**
 * Assay logo from docs/brand (served from /brand by `make brand`). Loaded as images, never inlined:
 * the SVGs reuse mask ids. Sizes follow docs/brand/README.md (logo ≥ 92 px wide, mark ≥ 20 px).
 */
export function Logo({
  variant,
  className = "",
}: {
  variant: "light" | "dark" | "mark-dark";
  className?: string;
}) {
  const src = {
    light: "/brand/assay-logo.svg",
    dark: "/brand/assay-logo-on-dark.svg",
    "mark-dark": "/brand/assay-mark-on-dark.svg",
  }[variant];
  return <img src={src} alt={PRODUCT_NAME} className={className} draggable={false} />;
}
