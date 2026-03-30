"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-blue-600 text-white shadow hover:bg-blue-600/90",
        destructive:
          "bg-red-500/10 text-red-500 hover:bg-red-500/20 dark:bg-red-500/20 dark:hover:bg-red-500/30",
        outline:
          "border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-sm hover:bg-zinc-800 hover:text-zinc-100",
        secondary:
          "bg-zinc-800 text-zinc-100 shadow-sm hover:bg-zinc-800/80",
        ghost:
          "text-zinc-100 hover:bg-zinc-800 hover:text-zinc-100",
        link: "text-blue-500 underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 gap-1.5 px-3 py-2",
        xs: "h-6 gap-1 rounded px-2 text-xs",
        sm: "h-7 gap-1 rounded-md px-2.5 text-xs",
        lg: "h-9 gap-1.5 rounded-md px-4",
        icon: "size-8",
        "icon-xs": "size-6 rounded",
        "icon-sm": "size-7 rounded-md",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> &
    VariantProps<typeof buttonVariants>
>(({ className, variant, size, ...props }, ref) => (
  <button
    className={cn(buttonVariants({ variant, size, className }))}
    ref={ref}
    {...props}
  />
))
Button.displayName = "Button"

export { Button, buttonVariants }
