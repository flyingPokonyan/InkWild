type Tone = "default" | "success" | "warning" | "danger" | "info" | "accent";

interface Props {
  tone?: Tone;
  dot?: boolean;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export function Badge({ tone = "default", dot, children, style }: Props) {
  return (
    <span
      className="badge"
      data-tone={tone === "default" ? undefined : tone}
      style={style}
    >
      {dot && <span className="badge-dot" />}
      {children}
    </span>
  );
}
