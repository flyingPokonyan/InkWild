interface TabOption<T extends string> {
  value: T;
  label: React.ReactNode;
  count?: number;
}

interface Props<T extends string> {
  value: T;
  options: TabOption<T>[];
  onChange: (v: T) => void;
}

export function Tabs<T extends string>({ value, options, onChange }: Props<T>) {
  return (
    <div className="tabs">
      {options.map((o) => (
        <button
          key={o.value}
          className="tab"
          data-active={o.value === value || undefined}
          onClick={() => onChange(o.value)}
          type="button"
        >
          {o.label}
          {o.count != null && <span className="tab-count">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
