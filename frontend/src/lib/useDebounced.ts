import { useEffect, useState } from "react";

/** `value` after it has not changed for `ms` (search boxes: one request when typing stops, not per key). */
export function useDebounced<T>(value: T, ms = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => {
      setSettled(value);
    }, ms);
    return () => {
      window.clearTimeout(t);
    };
  }, [value, ms]);
  return settled;
}
