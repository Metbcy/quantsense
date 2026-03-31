"use client"

import * as React from "react"
import { DayPicker } from "react-day-picker"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"

export type CalendarProps = React.ComponentProps<typeof DayPicker>

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: CalendarProps) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-3", className)}
      classNames={{
        months: "flex flex-col sm:flex-row gap-4",
        month: "flex flex-col gap-4",
        month_caption: "flex justify-center pt-1 relative items-center",
        caption_label: "text-sm font-medium text-zinc-100",
        nav: "flex items-center gap-1",
        button_previous: cn(
          buttonVariants({ variant: "outline" }),
          "absolute left-1 h-7 w-7 bg-transparent p-0 text-zinc-400 hover:text-zinc-100 border-zinc-700 hover:bg-zinc-800"
        ),
        button_next: cn(
          buttonVariants({ variant: "outline" }),
          "absolute right-1 h-7 w-7 bg-transparent p-0 text-zinc-400 hover:text-zinc-100 border-zinc-700 hover:bg-zinc-800"
        ),
        month_grid: "w-full border-collapse",
        weekdays: "flex",
        weekday: "text-zinc-500 rounded-md w-9 font-normal text-[0.8rem]",
        week: "flex w-full mt-2",
        day: "h-9 w-9 text-center text-sm p-0 relative",
        day_button: cn(
          buttonVariants({ variant: "ghost" }),
          "h-9 w-9 p-0 font-normal text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 aria-selected:opacity-100"
        ),
        selected:
          "bg-blue-600 text-white rounded-md hover:bg-blue-600 hover:text-white focus:bg-blue-600 focus:text-white [&>button]:text-white [&>button]:hover:text-white [&>button]:hover:bg-blue-600",
        today: "bg-zinc-800 rounded-md text-zinc-100",
        outside: "text-zinc-600 aria-selected:bg-zinc-800/50 aria-selected:text-zinc-500",
        disabled: "text-zinc-700 opacity-50",
        hidden: "invisible",
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation }) =>
          orientation === "left" ? (
            <ChevronLeft className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          ),
      }}
      {...props}
    />
  )
}
Calendar.displayName = "Calendar"

export { Calendar }
