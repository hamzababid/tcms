import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api } from "@/api/client";
import type { Me, ProjectMember } from "@/api/queries";
import { EmptyState, ErrorState, Skeleton, errorMessage } from "@/components/common/feedback";
import { MarkdownView, textareaClass } from "@/components/common/Markdown";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";

import { useComments, type Comment } from "./api";

const MENTION = /@\[([^\]]+)\]\(user:[0-9a-f-]{36}\)/g;

/** Mentions are stored as `@[Name](user:<uuid>)` (docs/06 §5.2) and shown as **@Name**. */
export function renderMentions(body: string): string {
  return body.replace(MENTION, (_m, name: string) => `**@${name}**`);
}

/** CommentThread (docs/07 §6.3): oldest first; authors edit or delete within 15 minutes. */
export function CommentThread({
  entityType,
  entityId,
  me,
  members,
  canComment,
}: {
  entityType: "test_case" | "test_case_version";
  entityId: string;
  me: Me;
  members: ProjectMember[];
  canComment: boolean;
}) {
  const comments = useComments(entityType, entityId);
  const add = useMutation({
    mutationFn: async (body: string) =>
      api.POST("/api/v1/comments", { body: { entity_type: entityType, entity_id: entityId, body } }),
    onSuccess: () => void comments.refetch(),
  });
  if (comments.isPending) return <Skeleton rows={2} />;
  if (comments.isError) return <ErrorState error={comments.error} onRetry={() => void comments.refetch()} />;
  return (
    <div className="flex flex-col gap-4">
      {comments.data.length === 0 ? <EmptyState text="No comments yet." /> : null}
      <ol className="flex flex-col gap-3">
        {comments.data.map((c) => (
          <CommentItem
            key={c.id}
            comment={c}
            me={me}
            members={members}
            onChanged={() => void comments.refetch()}
          />
        ))}
      </ol>
      {canComment ? (
        <Composer
          members={members}
          pending={add.isPending}
          error={add.error}
          onSubmit={(body, reset) => {
            add.mutate(body, { onSuccess: reset });
          }}
        />
      ) : null}
    </div>
  );
}

function CommentItem({
  comment,
  me,
  members,
  onChanged,
}: {
  comment: Comment;
  me: Me;
  members: ProjectMember[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const mine = comment.author?.id === me.user.id;
  const editable = mine && !comment.deleted && new Date(comment.editable_until) > new Date();
  const edit = useMutation({
    mutationFn: async (body: string) =>
      api.PATCH("/api/v1/comments/{comment_id}", {
        params: { path: { comment_id: comment.id } },
        body: { body },
      }),
    onSuccess: () => {
      setEditing(false);
      onChanged();
    },
  });
  const remove = useMutation({
    mutationFn: async () =>
      api.DELETE("/api/v1/comments/{comment_id}", { params: { path: { comment_id: comment.id } } }),
    onSuccess: onChanged,
  });
  return (
    <li className="rounded-card border border-border bg-surface p-3">
      <div className="mb-1 flex items-baseline gap-2 text-xs text-ink-muted">
        <span className="font-medium text-ink">{comment.author?.display_name ?? "Unknown"}</span>
        <time dateTime={comment.created_at}>{formatDateTime(comment.created_at)}</time>
        {comment.edited_at ? <span>(edited)</span> : null}
        <span className="flex-1" />
        {editable && !editing ? (
          <>
            <Button
              variant="link"
              size="sm"
              className="text-xs"
              onClick={() => {
                setEditing(true);
              }}
            >
              Edit
            </Button>
            <Button
              variant="link"
              size="sm"
              className="text-xs"
              onClick={() => {
                remove.mutate();
              }}
            >
              Delete
            </Button>
          </>
        ) : null}
      </div>
      {comment.deleted ? (
        <p className="text-[13px] italic text-ink-muted">Comment deleted</p>
      ) : editing ? (
        <Composer
          members={members}
          initial={comment.body ?? ""}
          pending={edit.isPending}
          error={edit.error}
          submitLabel="Save"
          onCancel={() => {
            setEditing(false);
          }}
          onSubmit={(body) => {
            edit.mutate(body);
          }}
        />
      ) : (
        <MarkdownView text={renderMentions(comment.body ?? "")} />
      )}
    </li>
  );
}

/** Textarea with an `@` member picker that inserts the mention token. */
function Composer({
  members,
  initial = "",
  pending,
  error,
  submitLabel = "Comment",
  onSubmit,
  onCancel,
}: {
  members: ProjectMember[];
  initial?: string;
  pending: boolean;
  error: unknown;
  submitLabel?: string;
  onSubmit: (body: string, reset: () => void) => void;
  onCancel?: () => void;
}) {
  const [body, setBody] = useState(initial);
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const matches = mention
    ? members
        .filter((m) => m.user.display_name.toLowerCase().includes(mention.query.toLowerCase()))
        .slice(0, 6)
    : [];

  const track = (value: string, caret: number) => {
    const before = value.slice(0, caret);
    const m = /(^|\s)@([\p{L}\p{N} ._-]{0,30})$/u.exec(before);
    const q = m?.[2];
    setMention(q !== undefined ? { start: caret - q.length - 1, query: q } : null);
  };
  const insert = (member: ProjectMember) => {
    if (!mention) return;
    const caret = area.current?.selectionStart ?? body.length;
    const token = `@[${member.user.display_name}](user:${member.user.id}) `;
    const next = body.slice(0, mention.start) + token + body.slice(caret);
    setBody(next);
    setMention(null);
    window.setTimeout(() => {
      const pos = mention.start + token.length;
      area.current?.focus();
      area.current?.setSelectionRange(pos, pos);
    }, 0);
  };
  const submit = () => {
    if (body.trim()) {
      onSubmit(body.trim(), () => {
        setBody("");
      });
    }
  };

  return (
    <div className="relative flex flex-col gap-2">
      <textarea
        ref={area}
        aria-label="Comment"
        rows={3}
        value={body}
        placeholder="Write a comment · @ to mention · Markdown supported"
        className={textareaClass}
        onChange={(e) => {
          setBody(e.target.value);
          track(e.target.value, e.target.selectionStart);
        }}
        onKeyDown={(e) => {
          if (mention && matches.length && (e.key === "Enter" || e.key === "Tab")) {
            e.preventDefault();
            insert(matches[0] as ProjectMember);
          } else if (e.key === "Escape" && mention) {
            setMention(null);
          } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            submit();
          }
        }}
      />
      {mention && matches.length ? (
        <div
          role="listbox"
          aria-label="Mention a member"
          className="absolute left-2 top-full z-20 mt-1 w-64 rounded-card border border-border bg-surface p-1 shadow-md"
        >
          {matches.map((m) => (
            <div key={m.user.id} role="option" aria-selected={false}>
              <button
                type="button"
                className="w-full rounded-control px-2 py-1.5 text-left text-[13px] hover:bg-ground"
                onMouseDown={(e) => {
                  e.preventDefault();
                  insert(m);
                }}
              >
                {m.user.display_name}
              </button>
            </div>
          ))}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-[13px] text-danger">
          {errorMessage(error)}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        {onCancel ? (
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
        <Button size="sm" disabled={pending || !body.trim()} onClick={submit}>
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
