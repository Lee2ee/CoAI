import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Search, ChevronDown } from 'lucide-react'
import ConditionBuilder from './ConditionBuilder'
import api from '../../utils/api'
import type { IndicatorCondition, StrategyConfig } from '../../types'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
const DEFAULT_SYMBOLS = ['BTC/KRW', 'ETH/KRW', 'SOL/KRW', 'XRP/KRW', 'DOGE/KRW', 'ADA/KRW']

interface Props {
  onClose: () => void
  initialConfig?: StrategyConfig
}

function SymbolSelector({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const { data: markets = DEFAULT_SYMBOLS } = useQuery<string[]>({
    queryKey: ['markets', 'upbit'],
    queryFn: async () => {
      const res = await api.get('/market/markets?exchange=upbit')
      return res.data.symbols as string[]
    },
    staleTime: 5 * 60 * 1000,
  })

  const filtered = markets.filter(s => s.toLowerCase().includes(search.toLowerCase()))

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="input w-full flex items-center justify-between text-left"
      >
        <span>{value}</span>
        <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-surface-800 border border-surface-600 rounded-lg shadow-xl overflow-hidden">
          <div className="p-2 border-b border-surface-700">
            <div className="flex items-center gap-2 bg-surface-700 rounded px-2">
              <Search size={13} className="text-slate-400" />
              <input
                autoFocus
                className="bg-transparent text-sm text-slate-200 placeholder-slate-500 py-1.5 flex-1 outline-none"
                placeholder="심볼 검색..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
          </div>
          <div className="max-h-48 overflow-y-auto">
            {filtered.slice(0, 50).map(s => (
              <button
                key={s}
                type="button"
                onClick={() => { onChange(s); setOpen(false); setSearch('') }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-surface-700 transition-colors ${
                  s === value ? 'text-brand-400 bg-brand-500/10' : 'text-slate-300'
                }`}
              >
                {s}
              </button>
            ))}
            {filtered.length === 0 && (
              <p className="text-xs text-slate-500 px-3 py-3">검색 결과 없음</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function StrategyForm({ onClose, initialConfig }: Props) {
  const qc = useQueryClient()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [symbol, setSymbol] = useState(initialConfig?.symbol ?? 'BTC/KRW')
  const [timeframe, setTimeframe] = useState(initialConfig?.timeframe ?? '1h')
  const [entryConditions, setEntryConditions] = useState<IndicatorCondition[]>(
    initialConfig?.entry_conditions ?? []
  )
  const [exitConditions, setExitConditions] = useState<IndicatorCondition[]>(
    initialConfig?.exit_conditions ?? []
  )
  const [stopLoss, setStopLoss] = useState(initialConfig?.risk?.stop_loss_pct ?? 2.0)
  const [takeProfit, setTakeProfit] = useState(initialConfig?.risk?.take_profit_pct ?? 4.0)
  const [positionSize, setPositionSize] = useState(initialConfig?.risk?.position_size_pct ?? 5.0)
  const [trailingStop, setTrailingStop] = useState(false)
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (data: unknown) => api.post('/strategies/', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
      onClose()
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(msg || '전략 저장에 실패했습니다.')
    },
  })

  const handleSubmit = () => {
    setError('')
    if (!name.trim()) { setError('전략 이름을 입력하세요.'); return }
    if (entryConditions.length === 0) { setError('진입 조건을 최소 1개 이상 설정하세요.'); return }
    if (stopLoss <= 0) { setError('손절가(%)는 0보다 커야 합니다.'); return }

    mutation.mutate({
      name,
      description,
      is_paper: true,
      config: {
        symbol,
        timeframe,
        entry_conditions: entryConditions,
        exit_conditions: exitConditions,
        risk: {
          stop_loss_pct: stopLoss,
          take_profit_pct: takeProfit,
          position_size_pct: positionSize,
          trailing_stop: trailingStop,
        },
      },
    })
  }

  return (
    <div className="space-y-5">
      {/* 기본 정보 */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">기본 설정</h3>
        <input
          className="input"
          placeholder="전략 이름 *"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <textarea
          className="input resize-none h-16"
          placeholder="전략 설명 (선택)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">거래쌍 (업비트 KRW)</label>
            <SymbolSelector value={symbol} onChange={setSymbol} />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">타임프레임</label>
            <select className="input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* 진입 조건 */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">진입 조건 (매수)</h3>
        <ConditionBuilder
          label="진입 신호"
          conditions={entryConditions}
          onChange={setEntryConditions}
        />
      </div>

      {/* 청산 조건 */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">청산 조건 (매도)</h3>
        <p className="text-xs text-slate-500">
          비워두면 손절/익절 가격에 의해서만 청산됩니다.
        </p>
        <ConditionBuilder
          label="청산 신호"
          conditions={exitConditions}
          onChange={setExitConditions}
        />
      </div>

      {/* 리스크 관리 */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">리스크 관리</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">손절가 (%)</label>
            <input
              type="number" className="input" step="0.1" min="0.1" max="50"
              value={stopLoss}
              onChange={(e) => setStopLoss(parseFloat(e.target.value))}
            />
            <p className="text-xs text-slate-500 mt-0.5">진입가 대비 -{stopLoss}%</p>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">익절가 (%)</label>
            <input
              type="number" className="input" step="0.1" min="0.1" max="200"
              value={takeProfit}
              onChange={(e) => setTakeProfit(parseFloat(e.target.value))}
            />
            <p className="text-xs text-slate-500 mt-0.5">진입가 대비 +{takeProfit}%</p>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">포지션 크기 (%)</label>
            <input
              type="number" className="input" step="1" min="1" max="100"
              value={positionSize}
              onChange={(e) => setPositionSize(parseFloat(e.target.value))}
            />
            <p className="text-xs text-slate-500 mt-0.5">자본의 {positionSize}% 투입</p>
          </div>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={trailingStop}
            onChange={(e) => setTrailingStop(e.target.checked)}
            className="w-4 h-4 rounded"
          />
          <span className="text-sm text-slate-300">트레일링 스탑 사용</span>
          <span className="text-xs text-slate-500">(수익 보호를 위해 손절가를 자동 상향)</span>
        </label>

        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex gap-2">
          <AlertTriangle size={16} className="text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="text-xs text-amber-300 font-medium">모의 거래로 시작</p>
            <p className="text-xs text-amber-200/70">
              새 전략은 항상 모의 거래로 시작됩니다. 충분한 검증 후 전략 목록에서 실거래로 전환하세요.
            </p>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-down/10 border border-down/30 rounded-lg p-3">
          <p className="text-sm text-down">{error}</p>
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button onClick={onClose} className="btn-ghost flex-1">취소</button>
        <button
          onClick={handleSubmit}
          disabled={mutation.isPending}
          className="btn-primary flex-1"
        >
          {mutation.isPending ? '저장 중...' : '전략 저장'}
        </button>
      </div>
    </div>
  )
}
