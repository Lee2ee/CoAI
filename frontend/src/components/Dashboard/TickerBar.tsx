import { useState, useCallback } from 'react'
import { useWebSocket } from '../../hooks/useWebSocket'
import { WifiOff } from 'lucide-react'
import clsx from 'clsx'

const WATCH_SYMBOLS = ['BTC/KRW', 'ETH/KRW', 'SOL/KRW', 'XRP/KRW', 'DOGE/KRW']

interface TickerData {
  symbol: string
  last: number
  change_pct: number
}

function getWsUrl(symbol: string) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/ticker?symbol=${encodeURIComponent(symbol)}&exchange=upbit`
}

export default function TickerBar() {
  const [tickers, setTickers] = useState<Record<string, TickerData>>({})
  const [error, setError] = useState('')

  const onMessage = useCallback((data: unknown) => {
    const msg = data as {
      type: string; symbol?: string
      last?: number; change_pct?: number; message?: string
    }
    if (msg.type === 'ticker' && msg.symbol && msg.last != null) {
      setError('')
      setTickers(prev => ({
        ...prev,
        [msg.symbol!]: { symbol: msg.symbol!, last: msg.last!, change_pct: msg.change_pct ?? 0 },
      }))
    } else if (msg.type === 'error') {
      setError((msg.message ?? '').slice(0, 80))
    }
  }, [])

  const { connected } = useWebSocket(
    getWsUrl('BTC/KRW'),
    { onMessage, reconnectInterval: 5000 },
  )

  return (
    <div className="bg-surface-800 border-b border-surface-700 h-10 flex items-center px-4 gap-5 overflow-x-auto">
      {(!connected || error) && (
        <div className="flex items-center gap-1.5 text-xs text-amber-400 whitespace-nowrap flex-shrink-0">
          <WifiOff size={12} />
          {!connected ? 'WS 연결 중...' : error}
        </div>
      )}

      {WATCH_SYMBOLS.map(sym => {
        const t = tickers[sym]
        const up = (t?.change_pct ?? 0) >= 0
        const label = sym.replace('/KRW', '')
        return (
          <div key={sym} className="flex items-center gap-2 whitespace-nowrap flex-shrink-0">
            <span className="text-xs text-slate-400">{label}</span>
            <span className="text-sm font-medium tabular-nums">
              {t ? `${t.last.toLocaleString('ko-KR')} ₩` : '—'}
            </span>
            {t && (
              <span className={clsx('text-xs font-medium tabular-nums', up ? 'text-up' : 'text-down')}>
                {up ? '+' : ''}{t.change_pct.toFixed(2)}%
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
