import { useState, useRef, useEffect } from 'react'
import { Search, ChevronDown } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import api from '../../utils/api'

const POPULAR_KRW = [
  'BTC/KRW', 'ETH/KRW', 'SOL/KRW', 'XRP/KRW', 'DOGE/KRW',
  'ADA/KRW', 'AVAX/KRW', 'DOT/KRW', 'LINK/KRW', 'MATIC/KRW',
  'ATOM/KRW', 'LTC/KRW', 'BCH/KRW', 'TRX/KRW', 'SHIB/KRW',
]

interface Props {
  value: string
  onChange: (symbol: string) => void
}

export default function SymbolPicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const { data: markets = POPULAR_KRW } = useQuery<string[]>({
    queryKey: ['markets', 'upbit'],
    queryFn: async () => {
      const res = await api.get('/market/markets?exchange=upbit')
      return res.data.symbols as string[]
    },
    staleTime: 5 * 60 * 1000,
  })

  const filtered = markets.filter((s) =>
    s.toLowerCase().includes(search.toLowerCase())
  )

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const select = (symbol: string) => {
    onChange(symbol)
    setOpen(false)
    setSearch('')
  }

  const [base, quote] = value.split('/')

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 bg-surface-700 hover:bg-surface-600 border border-surface-600 rounded-lg px-3 py-1.5 text-sm font-medium text-slate-100 transition-colors"
      >
        <span className="font-bold">{base}</span>
        <span className="text-slate-400 font-normal">/{quote}</span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-56 bg-surface-800 border border-surface-700 rounded-xl shadow-xl z-50">
          {/* 검색창 + 종목 수 */}
          <div className="p-2 border-b border-surface-700 space-y-1.5">
            <div className="flex items-center gap-2 bg-surface-700 rounded-lg px-2 py-1.5">
              <Search size={13} className="text-slate-400 flex-shrink-0" />
              <input
                autoFocus
                className="bg-transparent text-sm text-slate-100 placeholder:text-slate-500 outline-none w-full"
                placeholder="종목 검색... (예: SOL, DOGE)"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <p className="text-xs text-slate-500 text-right px-1">
              업비트 KRW · {filtered.length}/{markets.length}개
            </p>
          </div>

          <div className="max-h-64 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <p className="text-center text-slate-500 text-xs py-4">검색 결과 없음</p>
            ) : (
              filtered.map((symbol) => {
                const [b, q] = symbol.split('/')
                return (
                  <button
                    key={symbol}
                    onClick={() => select(symbol)}
                    className={`w-full text-left px-3 py-1.5 text-sm transition-colors ${
                      symbol === value
                        ? 'bg-brand-500/20 text-brand-400'
                        : 'text-slate-200 hover:bg-surface-700'
                    }`}
                  >
                    <span className="font-medium">{b}</span>
                    <span className="text-slate-500 text-xs ml-1">/{q}</span>
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
