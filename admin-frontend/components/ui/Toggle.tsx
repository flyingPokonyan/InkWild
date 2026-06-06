interface Props {
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  ariaLabel?: string;
  title?: string;
}

export function Toggle({ value, onChange, disabled, ariaLabel, title }: Props) {
  return (
    <button
      type="button"
      className="tgl"
      data-on={value || undefined}
      data-disabled={disabled || undefined}
      onClick={() => !disabled && onChange(!value)}
      aria-label={ariaLabel}
      title={title}
    />
  );
}
