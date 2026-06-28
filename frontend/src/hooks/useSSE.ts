import { useEffect, useRef, useCallback, useState, useMemo } from "react"

interface SSEEvent {
  type: string
  data: Record<string, unknown>
}

type EventHandler = (event: SSEEvent) => void

export function useSSE(url: string) {
  const [connected, setConnected] = useState(false)
  const [reconnectCounter, setReconnectCounter] = useState(0)
  const listenersRef = useRef<Map<string, Set<EventHandler>>>(new Map())
  // Refs tipados con `undefined` para que TS strict permita la reasignación a undefined
  // en disconnect() y en el cleanup del useEffect.
  const eventSourceRef = useRef<EventSource | null | undefined>(undefined)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const on = useCallback((eventType: string, handler: EventHandler) => {
    if (!listenersRef.current.has(eventType)) {
      listenersRef.current.set(eventType, new Set())
    }
    listenersRef.current.get(eventType)!.add(handler)

    return () => {
      listenersRef.current.get(eventType)?.delete(handler)
    }
  }, [])

  const off = useCallback((eventType: string, handler: EventHandler) => {
    listenersRef.current.get(eventType)?.delete(handler)
  }, [])

  const disconnect = useCallback(() => {
    if (reconnectRef.current !== undefined) {
      clearTimeout(reconnectRef.current)
      reconnectRef.current = undefined
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = undefined
    }
    setConnected(false)
  }, [])

  useEffect(() => {
    const es = new EventSource(url, { withCredentials: true })
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      if (reconnectRef.current !== undefined) {
        clearTimeout(reconnectRef.current)
        reconnectRef.current = undefined
      }
    }

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        const sseEvent: SSEEvent = { type: "message", data }
        listenersRef.current.get("*")?.forEach((h) => h(sseEvent))
        listenersRef.current.get("message")?.forEach((h) => h(sseEvent))
      } catch {
        // Non-JSON messages are ignored (e.g. keep-alive pings)
      }
    }

    es.addEventListener("execution.started", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data)
        const sseEvent: SSEEvent = { type: "execution.started", data }
        listenersRef.current.get("execution.started")?.forEach((h) => h(sseEvent))
        listenersRef.current.get("*")?.forEach((h) => h(sseEvent))
      } catch {
        // Non-JSON messages are ignored
      }
    })

    es.addEventListener("execution.completed", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data)
        const sseEvent: SSEEvent = { type: "execution.completed", data }
        listenersRef.current.get("execution.completed")?.forEach((h) => h(sseEvent))
        listenersRef.current.get("*")?.forEach((h) => h(sseEvent))
      } catch {
        // Non-JSON messages are ignored
      }
    })

    es.addEventListener("execution.failed", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data)
        const sseEvent: SSEEvent = { type: "execution.failed", data }
        listenersRef.current.get("execution.failed")?.forEach((h) => h(sseEvent))
        listenersRef.current.get("*")?.forEach((h) => h(sseEvent))
      } catch {
        // Non-JSON messages are ignored
      }
    })

    es.onerror = () => {
      setConnected(false)
      es.close()
      eventSourceRef.current = undefined
      // Auto-reconnect after 3 seconds
      reconnectRef.current = setTimeout(() => {
        setReconnectCounter((c) => c + 1)
      }, 3000)
    }

    return () => {
      if (reconnectRef.current !== undefined) {
        clearTimeout(reconnectRef.current)
        reconnectRef.current = undefined
      }
      es.close()
      eventSourceRef.current = undefined
      setConnected(false)
    }
  }, [url, reconnectCounter])

  return useMemo(
    () => ({ on, off, connected, disconnect }),
    [on, off, connected, disconnect]
  )
}
