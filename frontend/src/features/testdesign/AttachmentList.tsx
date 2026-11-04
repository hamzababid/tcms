import { useMutation } from "@tanstack/react-query";
import { FileText, Paperclip, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { api } from "@/api/client";
import { errorMessage, useToast } from "@/components/common/feedback";
import { formatBytes, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { uploadAttachment, type Attachment } from "./api";

/** AttachmentList + FileDropzone (docs/07 §6.3). Upload is shown only when `canUpload`. */
export function AttachmentList({
  attachments,
  entityType,
  entityId,
  canUpload,
  canRemove,
  maxMb,
  onChanged,
  compact = false,
  label,
}: {
  attachments: Attachment[];
  entityType: "test_case" | "test_case_step";
  entityId: string;
  canUpload: boolean;
  canRemove: (a: Attachment) => boolean;
  maxMb: number;
  onChanged: () => void;
  /** Small "Attach" button instead of the drop zone (step rows). */
  compact?: boolean;
  /** What the files attach to, for the button's accessible name (e.g. "step 2"). */
  label?: string;
}) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) await uploadAttachment(entityType, entityId, f);
    },
    onSuccess: () => {
      onChanged();
    },
    onError: (e) => {
      toast(errorMessage(e), "error");
      onChanged();
    },
  });
  const remove = useMutation({
    mutationFn: async (a: Attachment) =>
      api.DELETE("/api/v1/attachments/{attachment_id}/links/{entity_type}/{entity_id}", {
        params: { path: { attachment_id: a.id, entity_type: entityType, entity_id: entityId } },
      }),
    onSuccess: () => {
      onChanged();
    },
    onError: (e) => {
      toast(errorMessage(e), "error");
    },
  });
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (e.dataTransfer.files.length) upload.mutate([...e.dataTransfer.files]);
  };
  return (
    <div className="flex flex-col gap-2">
      {attachments.length ? (
        <ul className="flex flex-col gap-1">
          {attachments.map((a) => (
            <li key={a.id} className="flex items-center gap-2 text-sm">
              {a.content_type.startsWith("image/") ? (
                <img src={a.url} alt="" className="size-8 rounded border border-border object-cover" />
              ) : (
                <FileText aria-hidden="true" className="size-4 text-ink-muted" />
              )}
              <a
                href={a.url}
                target="_blank"
                rel="noreferrer"
                className="min-w-0 flex-1 truncate text-accent hover:underline"
              >
                {a.file_name}
              </a>
              <span className="text-xs text-ink-muted" title={formatDateTime(a.uploaded_at)}>
                {formatBytes(a.size_bytes)}
              </span>
              {canRemove(a) ? (
                <button
                  type="button"
                  aria-label={`Remove ${a.file_name}`}
                  onClick={() => {
                    remove.mutate(a);
                  }}
                  className="rounded p-0.5 text-ink-muted hover:bg-ground hover:text-ink"
                >
                  <X className="size-3.5" />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {canUpload && compact ? (
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label={`Attach a file to ${label ?? "this item"}`}
            title={`Attach a file · max ${maxMb} MB`}
            className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-xs text-ink-muted hover:bg-ground hover:text-ink"
            onClick={() => input.current?.click()}
          >
            <Paperclip aria-hidden="true" className="size-3.5" />
            Attach
          </button>
          <input
            ref={input}
            type="file"
            multiple
            tabIndex={-1}
            className="sr-only"
            aria-hidden="true"
            onChange={(e) => {
              if (e.target.files?.length) upload.mutate([...e.target.files]);
              e.target.value = "";
            }}
          />
          {upload.isPending ? <span role="status">Uploading…</span> : null}
        </div>
      ) : canUpload ? (
        // Drop target for files; the "browse" button is the keyboard alternative.
        // eslint-disable-next-line jsx-a11y/no-static-element-interactions
        <div
          onDragOver={(e) => {
            if (e.dataTransfer.types.includes("Files")) {
              e.preventDefault();
              setOver(true);
            }
          }}
          onDragLeave={() => {
            setOver(false);
          }}
          onDrop={onDrop}
          className={cn(
            "flex items-center justify-center gap-2 rounded-control border border-dashed border-border px-3 py-3 text-xs text-ink-muted",
            over && "border-accent bg-accent-tint",
          )}
        >
          <Paperclip aria-hidden="true" className="size-3.5" />
          <span>
            Drop files or{" "}
            <button
              type="button"
              className="text-accent hover:underline"
              onClick={() => input.current?.click()}
            >
              browse
            </button>{" "}
            · max {maxMb} MB
          </span>
          <input
            ref={input}
            type="file"
            multiple
            className="sr-only"
            aria-label="Attach files"
            onChange={(e) => {
              if (e.target.files?.length) upload.mutate([...e.target.files]);
              e.target.value = "";
            }}
          />
          {upload.isPending ? <span role="status">Uploading…</span> : null}
        </div>
      ) : null}
    </div>
  );
}
