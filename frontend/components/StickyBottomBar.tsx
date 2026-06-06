"use client";

interface StickyBottomBarProps {
  summary: string;
  canStart: boolean;
  starting: boolean;
  onStart: () => void;
  buttonLabel: string;
}

export function StickyBottomBar({
  summary,
  canStart,
  starting,
  onStart,
  buttonLabel,
}: StickyBottomBarProps) {
  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-border bg-bg-primary/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <p className="min-w-0 truncate text-body-sm text-text-secondary">{summary}</p>
        <button
          type="button"
          onClick={onStart}
          disabled={!canStart || starting}
          className="shrink-0 rounded-md bg-accent px-6 py-2 text-body-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          style={{ transitionDuration: "var(--duration-fast)" }}
        >
          {starting ? "启动中…" : buttonLabel}
        </button>
      </div>
    </div>
  );
}
