import { useEffect, useRef, useState, useCallback } from 'react'

interface UseWebSocketOptions {
  onMessage?: (data: unknown) => void
  reconnectInterval?: number
}

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const { onMessage, reconnectInterval = 3000 } = options
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      if (mountedRef.current) {
        timerRef.current = setTimeout(connect, reconnectInterval)
      }
    }
    ws.onerror = () => ws.close()
    ws.onmessage = (e) => {
      try {
        onMessage?.(JSON.parse(e.data))
      } catch {
        onMessage?.(e.data)
      }
    }
  }, [url, onMessage, reconnectInterval])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { connected }
}
