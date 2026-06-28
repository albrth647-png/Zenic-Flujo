import * as React from "react"
import * as PopoverPrimitive from "@radix-ui/react-popover"
import { cn } from "@/lib/utils"

const PopoverRoot = PopoverPrimitive.Root
const PopoverTrigger = PopoverPrimitive.Trigger

const PopoverContent = React.forwardRef<
  React.ComponentRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "center", sideOffset = 4, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        "z-50 w-72 rounded-md border border-zinc-800 bg-zinc-900 p-4 text-zinc-200 shadow-md outline-none animate-in fade-in-0 zoom-in-95",
        className
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
))
PopoverContent.displayName = "PopoverContent"

export { PopoverRoot, PopoverTrigger, PopoverContent }

// Re-export shorthand
export const Popover = ({ children, content, ...props }: { children: React.ReactNode; content: React.ReactNode } & React.ComponentPropsWithoutRef<typeof PopoverRoot>) => (
  <PopoverRoot {...props}>
    <PopoverTrigger asChild>{children}</PopoverTrigger>
    <PopoverContent>{content}</PopoverContent>
  </PopoverRoot>
)
