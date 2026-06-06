import clsx from "clsx";
import type { LucideIcon } from "lucide-react";

type Variant = "default" | "primary" | "ghost" | "danger";
type Size = "default" | "sm" | "xs";

interface Props extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "size"> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
}

export function Btn({
  variant = "default",
  size = "default",
  icon: Icon,
  children,
  className,
  ...rest
}: Props) {
  const iconOnly = !children;
  const iconSize = size === "xs" ? 11 : size === "sm" ? 12 : 13;
  return (
    <button
      type="button"
      className={clsx(
        "btn",
        variant === "primary" && "btn-primary",
        variant === "ghost" && "btn-ghost",
        variant === "danger" && "btn-danger",
        size === "sm" && "btn-sm",
        size === "xs" && "btn-xs",
        iconOnly && "btn-icon",
        className,
      )}
      {...rest}
    >
      {Icon && <Icon size={iconSize} />}
      {children}
    </button>
  );
}
