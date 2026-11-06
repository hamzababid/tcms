import { useEffect, useRef, useState } from "react";

import { saveStep, type StepFields, type StepResultRead, type StepStatus } from "../api";

export type SaveState = "saved" | "saving" | "error";

export interface StepLocal {
  status: StepStatus;
  actual_result: string;
  comment: string;
}

const TEXT_DEBOUNCE_MS = 600; // docs/04 §11.5
const RETRY_MS = 5000; // docs/02 §7.4

const local = (s: StepResultRead): StepLocal => ({
  status: s.status,
  actual_result: s.actual_result ?? "",
  comment: s.comment ?? "",
});

/**
 * Per-step auto-save for a draft attempt (US-090). Status changes save at once, text after 600 ms; a
 * failed save shows "not saved" and retries every 5 s. Steps are last-write-wins (docs/02 §2.4).
 */
export function useStepSaver(resultId: string, initial: StepResultRead[]) {
  const [values, setValues] = useState<Partial<Record<string, StepLocal>>>(() =>
    Object.fromEntries(initial.map((s) => [s.step_id, local(s)])),
  );
  const [state, setState] = useState<Partial<Record<string, SaveState>>>({});
  const pending = useRef(new Map<string, StepFields>());
  const inflight = useRef(new Map<string, Promise<void>>());
  const timers = useRef(new Map<string, number>());

  const mark = (stepId: string, s: SaveState) => {
    setState((cur) => ({ ...cur, [stepId]: s }));
  };

  /** Save the step's pending fields; a save already in flight is awaited first (no overlapping writes). */
  function flush(stepId: string): Promise<void> {
    const running = inflight.current.get(stepId);
    if (running) return running.then(() => flush(stepId));
    window.clearTimeout(timers.current.get(stepId));
    const fields = pending.current.get(stepId);
    if (!fields) return Promise.resolve();
    pending.current.delete(stepId);
    mark(stepId, "saving");
    const job = saveStep(resultId, stepId, fields).then(
      () => {
        inflight.current.delete(stepId);
        if (pending.current.has(stepId)) return flush(stepId);
        mark(stepId, "saved");
        return undefined;
      },
      () => {
        inflight.current.delete(stepId);
        pending.current.set(stepId, { ...fields, ...pending.current.get(stepId) });
        mark(stepId, "error");
        timers.current.set(
          stepId,
          window.setTimeout(() => void flush(stepId), RETRY_MS),
        );
      },
    );
    inflight.current.set(stepId, job);
    return job;
  }

  useEffect(() => {
    const t = timers.current;
    return () => {
      for (const id of t.values()) window.clearTimeout(id);
    };
  }, []);

  const update = (stepId: string, fields: Partial<StepLocal>, immediate: boolean) => {
    setValues((cur) => {
      const prev = cur[stepId] ?? { status: "not_run" as StepStatus, actual_result: "", comment: "" };
      return { ...cur, [stepId]: { ...prev, ...fields } };
    });
    pending.current.set(stepId, { ...pending.current.get(stepId), ...fields });
    mark(stepId, "saving");
    window.clearTimeout(timers.current.get(stepId));
    if (immediate) void flush(stepId);
    else
      timers.current.set(
        stepId,
        window.setTimeout(() => void flush(stepId), TEXT_DEBOUNCE_MS),
      );
  };

  /** Before Finish: every pending change is sent and every save in flight has answered. */
  const flushAll = async () => {
    const ids = new Set([...pending.current.keys(), ...inflight.current.keys()]);
    await Promise.all([...ids].map((id) => flush(id)));
  };

  /** After the server changed steps in bulk ("Pass all remaining"). */
  const applyServer = (steps: StepResultRead[]) => {
    setValues((cur) => {
      const next = { ...cur };
      for (const s of steps) if (!pending.current.has(s.step_id)) next[s.step_id] = local(s);
      return next;
    });
  };

  const states = Object.values(state);
  return {
    values,
    state,
    update,
    flushAll,
    applyServer,
    unsaved: states.some((s) => s !== "saved"),
    failing: states.some((s) => s === "error"),
  };
}
