import * as React from "react"
import { cn } from "@/lib/utils"

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number
  max?: number
  variant?: "default" | "success" | "warning" | "danger"
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value = 0, max = 100, variant = "default", ...props }, ref) => {
    const pct = Math.min(Math.max((value / max) * 100, 0), 100)

    const variantStyles: Record<string, string> = {
      default: "bg-indigo-500",
      success: "bg-emerald-500",
      warning: "bg-amber-500",
      danger: "bg-red-500",
    }

    return (
      <div
        ref={ref}
        className={cn("relative h-2 w-full overflow-hidden rounded-full bg-zinc-800", className)}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        {...props}
      >
        <div
          className={cn(
            "h-full w-full flex-1 rounded-full transition-all duration-500",
            variantStyles[variant] || variantStyles.default
          )}
          style={{ transform: `translateX(-${100 - pct}%)` }}
        />
      </div>
    )
  }
)
Progress.displayName = "Progress"

export { Progress }
