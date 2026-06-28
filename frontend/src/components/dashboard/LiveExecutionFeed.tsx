import { useEffect, useState, useRef, useCallback } from "react"
import { StatusBadge } from "@/components/StatusBadge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface LiveEvent {
  id: string
  workflow_id: number
  name: string
  status: "started" | "completed" | "failed"
  duration_ms?: number
  error?: string
  timestamp: string
}

interface LiveExecutionFeedProps {
  onEvent?: (event: LiveEvent) => void
}

export function LiveExecutionFeed({ onEvent }: LiveExecutionFeedProps) {
  const [events, setEvents] = useState<LiveEvent[]>([])
  const maxEvents = 20
  const containerRef = useRef<HTMLDivElement>(null)

  const addEvent = useCallback((event: LiveEvent) => {
    setEvents((prev) => [event, ...prev].slice(0, maxEvents))
    onEvent?.(event)
  }, [onEvent])

  // Expose addEvent for the SSE handler to call
  useEffect(() => {
    const handler = (e: CustomEvent<LiveEvent>) => addEvent(e.detail)
    window.addEventListener("dashboard-live-event", handler as EventListener)
    return () => window.removeEventListener("dashboard-live-event", handler as EventListener)
  }, [addEvent])

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0
    }
  }, [events])

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">⚡ Tiempo real</CardTitle>
          <span className="flex items-center gap-1.5 text-[10px] text-emerald-500 font-medium">
            <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
            EN VIVO
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div ref={containerRef} className="max-h-[320px] overflow-y-auto">
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Esperando ejecuciones...
            </p>
          ) : (
            <div className="divide-y">
              {events.map((event) => (
                <div
                  key={event.id}
                  className={cn(
                    "flex items-center justify-between px-4 py-2.5 transition-colors",
                    "hover:bg-accent/50"
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <EventDot status={event.status} />
                      <span className="text-sm font-medium truncate">
                        {event.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-muted-foreground">
                        #{event.workflow_id}
                      </span>
                      {event.duration_ms && (
                        <span className="text-[10px] text-muted-foreground">
                          {event.duration_ms}ms
                        </span>
                      )}
                      {event.error && (
                        <span className="text-[10px] text-destructive truncate max-w-[120px]">
                          {event.error}
                        </span>
                      )}
                    </div>
                  </div>
                  <StatusBadge
                    status={
                      event.status === "started"
                        ? "running"
                        : event.status === "completed"
                          ? "completed"
                          : "failed"
                    }
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function EventDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    started: "bg-blue-500 animate-pulse",
    completed: "bg-emerald-500",
    failed: "bg-destructive",
  }
  return (
    <span className={cn("size-2 rounded-full shrink-0", colors[status] || "bg-muted")} />
  )
}
