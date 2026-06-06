import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "default" | "primary";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const sizeClass: Record<Size, string> = {
  sm: "lv-btn-sm",
  md: "",
  lg: "lv-btn-lg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "default", size = "md", className = "", ...rest }, ref) => {
    const variantClass = variant === "primary" ? "lv-btn lv-btn-primary" : "lv-btn";
    const composed = [variantClass, sizeClass[size], className].filter(Boolean).join(" ");
    return <button ref={ref} className={composed} {...rest} />;
  },
);
Button.displayName = "Button";
