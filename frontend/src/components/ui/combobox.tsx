import * as P from "@radix-ui/react-popover";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { controlClass } from "./field";

export interface ComboOption {
  value: string;
  label: string;
  /** Second line or right-hand text (project key, email, folder path). */
  hint?: string;
  /** Extra words that match the search but are not shown. */
  keywords?: string;
  disabled?: boolean;
}

/** Above this many options the search box is shown. */
const SEARCH_FROM = 8;
/** Options rendered at once; typing narrows the rest (1,000+ folders stay fast). */
const RENDER_LIMIT = 200;

export function matches(o: ComboOption, needle: string): boolean {
  if (!needle) return true;
  return `${o.label} ${o.hint ?? ""} ${o.keywords ?? ""}`.toLowerCase().includes(needle);
}

/**
 * Search box plus a scrollable list of options, for use inside a popover (Combobox, the project
 * switcher). ↑/↓/Home/End move, Enter picks; typing filters by label, hint and keywords.
 */
export function SearchList({
  options,
  value,
  onPick,
  label,
  searchPlaceholder = "Search…",
  searchable = options.length > SEARCH_FROM,
  renderOption,
  footer,
}: {
  options: ComboOption[];
  value: string;
  onPick: (o: ComboOption) => void;
  label: string;
  searchPlaceholder?: string;
  searchable?: boolean;
  renderOption?: (o: ComboOption) => ReactNode;
  footer?: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(() =>
    Math.max(
      0,
      options.findIndex((x) => x.value === value),
    ),
  );
  const listId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const needle = query.trim().toLowerCase();
  const found = useMemo(() => options.filter((o) => matches(o, needle)), [options, needle]);
  const shown = found.slice(0, RENDER_LIMIT);

  const pick = (o: ComboOption | undefined) => {
    if (o && !o.disabled) onPick(o);
  };
  const move = (i: number) => {
    const next = Math.max(0, Math.min(i, shown.length - 1));
    setActive(next);
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${next}"]`)
      ?.scrollIntoView({ block: "nearest" });
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") move(active + 1);
    else if (e.key === "ArrowUp") move(active - 1);
    else if (e.key === "Home" && !searchable) move(0);
    else if (e.key === "End" && !searchable) move(shown.length - 1);
    else if (e.key === "Enter") pick(shown[active]);
    else return;
    e.preventDefault();
  };
  // Scroll the current choice into view when the list opens.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[aria-selected="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, []);

  return (
    <>
      {searchable ? (
        <label className="flex shrink-0 items-center gap-2 border-b border-border px-2.5">
          <Search aria-hidden="true" className="size-3.5 text-ink-muted" />
          <input
            type="search"
            role="combobox"
            // eslint-disable-next-line jsx-a11y/no-autofocus -- the popover opened for searching
            autoFocus
            aria-label={searchPlaceholder}
            aria-controls={listId}
            aria-expanded
            aria-autocomplete="list"
            aria-activedescendant={shown[active] ? `${listId}-${active}` : undefined}
            placeholder={searchPlaceholder}
            className="h-9 min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-muted"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKey}
          />
        </label>
      ) : null}
      <div
        ref={listRef}
        id={listId}
        role="listbox"
        tabIndex={searchable ? -1 : 0}
        // eslint-disable-next-line jsx-a11y/no-autofocus -- the popover opened for choosing
        autoFocus={!searchable}
        aria-label={label}
        aria-activedescendant={!searchable && shown[active] ? `${listId}-${active}` : undefined}
        onKeyDown={searchable ? undefined : onKey}
        className="min-h-0 flex-1 overflow-y-auto p-1 outline-none"
      >
        {shown.map((o, i) => (
          <div
            key={o.value || "__empty"}
            id={`${listId}-${i}`}
            data-index={i}
            role="option"
            tabIndex={-1}
            aria-selected={o.value === value}
            aria-disabled={o.disabled || undefined}
            onMouseEnter={() => {
              setActive(i);
            }}
            onMouseDown={(e) => {
              e.preventDefault(); // keep focus in the search box
            }}
            onClick={() => {
              pick(o);
            }}
            // Keys are handled by the search box or the listbox (aria-activedescendant pattern).
            onKeyDown={() => undefined}
            className={cn(
              "flex min-h-8 cursor-pointer select-none items-center gap-2 rounded-[5px] px-2.5 py-1",
              i === active && "bg-surface-muted",
              o.value === value && "font-medium text-accent-ink",
              o.disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <span className="min-w-0 flex-1">
              {renderOption ? (
                renderOption(o)
              ) : (
                <>
                  <span className="block truncate">{o.label}</span>
                  {o.hint ? <span className="block truncate text-xs text-ink-muted">{o.hint}</span> : null}
                </>
              )}
            </span>
            {o.value === value ? <Check aria-hidden="true" className="size-4 shrink-0" /> : null}
          </div>
        ))}
        {found.length === 0 ? <p className="px-2.5 py-3 text-ink-muted">No matches</p> : null}
      </div>
      {found.length > shown.length ? (
        <p className="shrink-0 border-t border-border px-2.5 py-1.5 text-xs text-ink-secondary">
          {shown.length} of {found.length.toLocaleString()} shown. Type to narrow the list.
        </p>
      ) : null}
      {footer}
    </>
  );
}

/** Popover panel for SearchList: as wide as its trigger, never taller than the space on screen. */
export const popoverPanel =
  "z-50 flex min-w-56 max-w-[min(32rem,calc(100vw-16px))] flex-col overflow-hidden rounded-card border border-border bg-surface text-[13px] text-ink shadow-[var(--shadow-popover)]";
export const popoverHeight = { maxHeight: "min(420px, var(--radix-popover-content-available-height))" };

/**
 * Searchable, scrollable select for lists that can grow large (projects, folders, people, plans;
 * docs/07 §4.5). Drop-in for `Select` inside `Field`: takes the field's id and aria props on the button.
 * The list is capped to the space on screen and scrolls; Esc closes.
 */
export function Combobox({
  options,
  value,
  onChange,
  placeholder = "Choose…",
  emptyOption,
  searchPlaceholder,
  className,
  disabled,
  renderOption,
  ...aria
}: {
  options: ComboOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** A first entry that clears the value ("All", "Unassigned", "None"). */
  emptyOption?: string;
  searchPlaceholder?: string;
  className?: string;
  disabled?: boolean;
  renderOption?: (o: ComboOption) => ReactNode;
  id?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}) {
  const [open, setOpen] = useState(false);
  const nameId = useId();
  const { "aria-label": ariaLabel, ...rest } = aria;
  const all = useMemo(
    () => (emptyOption !== undefined ? [{ value: "", label: emptyOption }, ...options] : options),
    [options, emptyOption],
  );
  const selected = all.find((o) => o.value === value);
  return (
    <P.Root open={open} onOpenChange={setOpen}>
      <P.Trigger
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        className={cn(
          controlClass,
          "flex h-9 items-center gap-2 pl-2.5 pr-2 text-left",
          !selected && "text-ink-muted",
          className,
        )}
        {...rest}
        // A picker named by aria-label is announced as "label, value" (axe label-content-name-mismatch:
        // the name must contain the visible text). Inside a Field the <label for> names it.
        {...(ariaLabel ? { "aria-labelledby": `${nameId}-l ${nameId}-v` } : {})}
      >
        {ariaLabel ? (
          <span id={`${nameId}-l`} className="sr-only">
            {ariaLabel}
          </span>
        ) : null}
        <span id={`${nameId}-v`} className="min-w-0 flex-1 truncate">
          {selected ? selected.label : placeholder}
        </span>
        <ChevronsUpDown aria-hidden="true" className="size-3.5 shrink-0 text-ink-muted" />
      </P.Trigger>
      <P.Portal>
        <P.Content
          align="start"
          sideOffset={4}
          collisionPadding={8}
          className={cn(popoverPanel, "w-[var(--radix-popover-trigger-width)]")}
          style={popoverHeight}
        >
          <SearchList
            options={all}
            value={value}
            label={ariaLabel ?? placeholder}
            searchable={options.length > SEARCH_FROM}
            {...(searchPlaceholder ? { searchPlaceholder } : {})}
            {...(renderOption ? { renderOption } : {})}
            onPick={(o) => {
              onChange(o.value);
              setOpen(false);
            }}
          />
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}
