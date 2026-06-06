interface SegmentedOption<T extends string> {
  value: T;
  label: React.ReactNode;
}

interface Props<T extends string> {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (v: T) => void;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: Props<T>) {
  return (
    <div className="segmented">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          data-active={o.value === value || undefined}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
