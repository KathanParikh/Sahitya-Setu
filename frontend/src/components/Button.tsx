import type { ButtonHTMLAttributes } from "react";

type Variant = "default" | "primary" | "quiet";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  block?: boolean;
}

export function Button({ variant = "default", block, className, type, ...rest }: ButtonProps) {
  const classes = [
    "button",
    variant !== "default" && `button--${variant}`,
    block && "button--block",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <button type={type ?? "button"} className={classes} {...rest} />;
}
