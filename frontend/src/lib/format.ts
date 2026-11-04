/** A rate as returned by the API (docs/06 §5.7): value is null when the denominator is 0. */
export interface Rate {
  numerator: number;
  denominator: number;
  value: number | null;
}

const integer = new Intl.NumberFormat("en-US");

export function formatCount(n: number): string {
  return integer.format(n);
}

/** Whole-percent display; never rounds a non-zero/non-total value to 0% or 100%. */
export function formatPercent(value: number | null): string {
  if (value === null) return "—";
  const pct = value * 100;
  let rounded = Math.round(pct);
  if (rounded === 0 && pct > 0) rounded = 1;
  if (rounded === 100 && pct < 100) rounded = 99;
  return `${rounded}%`;
}

/** "180 of 205 (88%)", or "—" when undefined (docs/02 §11.2). */
export function formatRate(rate: Rate): string {
  if (rate.value === null) return "—";
  return `${formatCount(rate.numerator)} of ${formatCount(rate.denominator)} (${formatPercent(rate.value)})`;
}
