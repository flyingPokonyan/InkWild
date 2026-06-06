interface WorldModeCardProps {
  title: string;
  summary: string;
  selected: boolean;
  onSelect: () => void;
  badge?: string;
}

export function WorldModeCard({ title, summary, selected, onSelect, badge }: WorldModeCardProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={`card rounded-lg p-6 text-left transition ${
        selected
          ? "border-state-selected-border bg-state-selected-bg shadow-[--color-state-selected-glow]"
          : "hover:border-state-hover-border hover:bg-state-hover-bg"
      }`}
      style={{ transitionDuration: "var(--duration-fast)" }}
    >
      <div className="flex min-h-[11rem] flex-col justify-between gap-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-caption uppercase tracking-[0.28em] text-text-muted">
              {selected ? "当前已选" : "进入方式"}
            </div>
            <div className="display-type mt-4 text-heading text-text-primary">{title}</div>
            <div className="mt-3 max-w-md text-body-sm leading-7 text-text-secondary">{summary}</div>
          </div>
          {badge && (
            <span className={`rounded-full px-3 py-1 text-caption ${selected ? "bg-accent text-bg-primary" : "bg-bg-primary/60 text-text-muted"}`}>
              {badge}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/6 pt-4 text-body-sm">
          <span className="text-text-muted">
            {selected ? "继续向下查看这一模式的内容" : "点击后展开这一模式"}
          </span>
          <span className="text-accent">{selected ? "继续查看 →" : "进入 →"}</span>
        </div>
      </div>
    </button>
  );
}
