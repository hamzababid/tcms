import { forwardRef, useState, type TextareaHTMLAttributes } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * Markdown read view (docs/07 §6.3 MarkdownView). Raw HTML is not rendered (react-markdown default),
 * so user content cannot inject markup; links open in a new tab without referrer.
 */
export function MarkdownView({ text, className }: { text: string | null | undefined; className?: string }) {
  if (!text) return null;
  return (
    <div className={cn("md text-sm leading-6 text-ink", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export const textareaClass =
  "w-full rounded-control border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] aria-[invalid=true]:border-[var(--status-fail-bar)]";

/**
 * Compact Markdown editor: a textarea while focused, the rendered preview on blur (docs/07 §5.5).
 * Clicking or focusing the preview returns to editing.
 */
export const MarkdownEditor = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & { value: string; preview?: boolean }
>(({ value, className, preview = true, onFocus, onBlur, ...props }, ref) => {
  const [editing, setEditing] = useState(false);
  const showPreview = preview && !editing && value.trim() !== "";
  return (
    <div className="relative">
      <textarea
        ref={ref}
        value={value}
        className={cn(textareaClass, showPreview && "sr-only", className)}
        onFocus={(e) => {
          setEditing(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setEditing(false);
          onBlur?.(e);
        }}
        {...props}
      />
      {showPreview ? (
        <div
          aria-hidden="true"
          onClick={(e) => {
            const area = e.currentTarget.previousElementSibling;
            if (area instanceof HTMLTextAreaElement) area.focus();
          }}
          className={cn(textareaClass, "min-h-9 cursor-text", className)}
        >
          <MarkdownView text={value} />
        </div>
      ) : null}
    </div>
  );
});
MarkdownEditor.displayName = "MarkdownEditor";
