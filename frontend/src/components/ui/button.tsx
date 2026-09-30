import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-[var(--r-sm)] text-[14px] font-bold tracking-[-0.005em] transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/45 disabled:pointer-events-none disabled:opacity-40 active:translate-y-px",
  {
    variants: {
      variant: {
        default:
          "border border-[var(--color-accent)]/35 bg-[var(--color-accent)]/14 text-[var(--color-accent)] shadow-[0_1px_0_rgba(255,255,255,0.05)_inset] hover:bg-[var(--color-accent)]/22 hover:border-[var(--color-accent)]/55",
        outline:
          "border border-[var(--hairline)] bg-[var(--veil-1)] text-[var(--text-dim)] hover:text-[var(--text-ink)] hover:bg-[var(--veil-1)] hover:border-[var(--hairline)] hover:brightness-125",
        ghost:
          "text-[var(--text-dim)] hover:text-[var(--text-ink)] hover:bg-[var(--veil-1)]",
        verify:
          "border border-[var(--color-st-verified)]/40 bg-[var(--color-st-verified)]/14 text-[var(--color-st-verified)] hover:bg-[var(--color-st-verified)]/24 hover:border-[var(--color-st-verified)]/60",
        reject:
          "border border-[var(--color-st-rejected)]/40 bg-[var(--color-st-rejected)]/14 text-[var(--color-st-rejected)] hover:bg-[var(--color-st-rejected)]/24 hover:border-[var(--color-st-rejected)]/60",
      },
      size: {
        sm: "h-8 px-3",
        md: "h-9 px-4",
        lg: "h-11 px-5 text-[15.5px] rounded-[var(--r-md)]",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";
