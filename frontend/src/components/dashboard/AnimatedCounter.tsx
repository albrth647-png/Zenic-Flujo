import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface AnimatedCounterProps {
  value: number
  duration?: number
  className?: string
  prefix?: string
  suffix?: string
}

export function AnimatedCounter({
  value,
  duration = 600,
  className,
  prefix = "",
  suffix = "",
}: AnimatedCounterProps) {
  const [displayValue, setDisplayValue] = useState(value)
  const prevValue = useRef(value)
  // requestAnimationFrame devuelve number en browser, pero useRef sin inicial
  // falla en strict mode. Usamos undefined como valor inicial explícito.
  const frameRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    const start = prevValue.current
    const end = value
    const diff = end - start
    if (diff === 0) return

    const startTime = performance.now()

    const animate = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = Math.round(start + diff * eased)

      setDisplayValue(current)

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate)
      } else {
        setDisplayValue(end)
        prevValue.current = end
      }
    }

    frameRef.current = requestAnimationFrame(animate)
    prevValue.current = end

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
    }
  }, [value, duration])

  return (
    <span className={cn("tabular-nums", className)}>
      {prefix}{displayValue.toLocaleString("es-ES")}{suffix}
    </span>
  )
}
