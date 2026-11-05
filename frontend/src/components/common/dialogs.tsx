import { useState, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/field";

import { errorMessage } from "./feedback";

/** Confirmation; with `confirmText` the user must type it (hard deletes, docs/07 §4.4). */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  confirmText,
  destructive = false,
  pending = false,
  error,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel: string;
  confirmText?: string;
  destructive?: boolean;
  pending?: boolean;
  error?: unknown;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  const [typed, setTyped] = useState("");
  const ready = !confirmText || typed.trim() === confirmText;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setTyped("");
        onOpenChange(o);
      }}
      title={title}
      {...(description ? { description } : {})}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            disabled={!ready || pending}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
      {confirmText ? (
        <Field label={`Type ${confirmText} to confirm`}>
          {(p) => (
            <Input
              {...p}
              value={typed}
              autoComplete="off"
              onChange={(e) => {
                setTyped(e.target.value);
              }}
            />
          )}
        </Field>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-[13px] text-danger">
          {errorMessage(error)}
        </p>
      ) : null}
    </Dialog>
  );
}

/** Single text value (folder name, return comment, reason). */
export function PromptDialog({
  open,
  onOpenChange,
  title,
  label,
  initial = "",
  submitLabel,
  multiline = false,
  required = true,
  pending = false,
  error,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  label: string;
  initial?: string;
  submitLabel: string;
  multiline?: boolean;
  required?: boolean;
  pending?: boolean;
  error?: unknown;
  onSubmit: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);
  const fieldError = error instanceof ApiError ? error.errors[0]?.message : undefined;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (o) setValue(initial);
        onOpenChange(o);
      }}
      title={title}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button type="submit" form="prompt-dialog" disabled={pending || (required && value.trim() === "")}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <form
        id="prompt-dialog"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(value.trim());
        }}
      >
        <Field
          label={label}
          required={required}
          error={fieldError ?? (error ? errorMessage(error) : undefined)}
        >
          {(p) =>
            multiline ? (
              <textarea
                {...p}
                rows={4}
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    e.currentTarget.form?.requestSubmit();
                  }
                }}
                className="w-full rounded-control border border-border bg-surface px-3 py-2 text-sm"
              />
            ) : (
              <Input
                {...p}
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                }}
              />
            )
          }
        </Field>
      </form>
    </Dialog>
  );
}

/** `409 stale_row_version` (docs/07 §4.4): who changed it, then Reload or keep editing. */
export function ConflictDialog({
  error,
  onReload,
  onClose,
}: {
  error: unknown;
  onReload: () => void;
  onClose: () => void;
}) {
  const open = error instanceof ApiError && error.code === "stale_row_version";
  const current = open ? (error.body.current as { updated_at?: string } | null | undefined) : null;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title="Someone else changed this"
      description={
        current?.updated_at
          ? `It was changed at ${new Date(current.updated_at).toLocaleString()} while you were editing.`
          : "It was changed while you were editing."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Keep my edits
          </Button>
          <Button onClick={onReload}>Reload latest</Button>
        </>
      }
    >
      <p className="text-sm text-ink-secondary">
        Reloading discards your unsaved changes. Keeping your edits lets you copy them before reloading.
      </p>
    </Dialog>
  );
}
