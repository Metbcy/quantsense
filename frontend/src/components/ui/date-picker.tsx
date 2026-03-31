"use client"

import { format } from "date-fns"
import { CalendarIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"
import { Calendar } from "./calendar"
import { Popover, PopoverContent, PopoverTrigger } from "./popover"

interface DatePickerProps {
  date: Date | undefined
  onDateChange: (date: Date | undefined) => void
  placeholder?: string
}

export function DatePicker({
  date,
  onDateChange,
  placeholder = "Pick a date",
}: DatePickerProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "w-full justify-start text-left font-normal border-zinc-700 bg-zinc-950 hover:bg-zinc-900",
            !date && "text-zinc-500"
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4 text-zinc-400" />
          {date ? (
            <span className="text-zinc-100">
              {format(date, "MMM d, yyyy")}
            </span>
          ) : (
            <span>{placeholder}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={date}
          onSelect={onDateChange}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  )
}
