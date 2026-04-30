import { useState, useMemo } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BarChart2, Play, ChevronDown, ChevronUp, Search } from 'lucide-react'
import api from '../utils/api'
import EquityChart from '../components/Dashboard/EquityChart'
import ConditionBuilder from '../components/Strategy/ConditionBuilder'
import type { BacktestRequest, BacktestResult, StrategyConfig, IndicatorCondition } from '../types'
import clsx from 'clsx'

const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

interface Props {
  initialConfig?: StrategyConfig
}

let _id = 0
const newId = () => `bt_${++_id}`

// ─── 심볼 검색 컴포넌트 ──────────────────────────────────────────────────────

function SymbolSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)

  const { data: symbols = [], isLoading } = useQuery<string[]>({
    queryKey: ['upbit-markets'],
    queryFn: async () => {
      const res = await api.get('/market/markets?exchange=upbit')
      return res.data.symbols as string[]
    },
    staleTime: 5 * 60_000,
  })

  const filtered = useMemo(() => {
    const q = search.toUpperCase()
    return q ? symbols.filter(s => s.includes(q)) : symbols
  }, [symbols, search])

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="input flex items-center justify-between w-full"
      >
        <span>{value}</span>
        <ChevronDown size={14} className="text-slate-400" />
      </button>

      {open && (
        <div className="absolute z-20 top-full mt-1 w-full bg-surface-800 border border-surface-600 rounded-lg shadow-xl">
          <div className="p-2 border-b border-surface-700">
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                autoFocus
                className="input pl-8 py-1.5 text-sm"
                placeholder="종목 검색 (예: BTC)"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
          </div>
          <div className="max-h-52 overflow-y-auto">
            {isLoading ? (
              <p className="text-xs text-slate-400 text-center py-3">불러오는 중...</p>
            ) : filtered.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-3">검색 결과 없음</p>
            ) : (
              filtered.map(s => (
                <button
                  key={s}
                  type="button"
                  onClick={() => { onChange(s); setOpen(false); setSearch('') }}
                  className={clsx(
                    'w-full text-left px-3 py-2 text-sm hover:bg-surface-700 transition-colors',
                    s === value ? 'text-brand-400 bg-brand-500/10' : 'text-slate-300'
                  )}
                >
                  {s}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── 백테스트 페이지 ─────────────────────────────────────────────────────────

export default function BacktestPage({ initialConfig }: Props) {
  const [symbol, setSymbol] = useState(initialConfig?.symbol ?? 'BTC/KRW')
  const [timeframe, setTimeframe] = useState(initialConfig?.timeframe ?? '1h')
  const [entryConditions, setEntryConditions] = useState<IndicatorCondition[]>(
    initialConfig?.entry_conditions ?? [
      { id: newId(), indicator: 'RSI', params: { length: 14 }, operator: '<', value: 30 },
    ]
  )
  const [exitConditions, setExitConditions] = useState<IndicatorCondition[]>(
    initialConfig?.exit_conditions ?? [
      { id: newId(), indicator: 'RSI', params: { length: 14 }, operator: '>', value: 70 },
    ]
  )
  const [stopLoss, setStopLoss] = useState(initialConfig?.risk?.stop_loss_pct ?? 2.0)
  const [takeProfit, setTakeProfit] = useState(initialConfig?.risk?.take_profit_pct ?? 5.0)
  const [positionSize, setPositionSize] = useState(initialConfig?.risk?.position_size_pct ?? 10.0)
  const [initialCapital, setInitialCapital] = useState(1_000_000)
  const [feeRate, setFeeRate] = useState(0.0005)  // 업비트 수수료 0.05%
  const [walkForward, setWalkForward] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [configOpen, setConfigOpen] = useState(!initialConfig)

  const mutation = useMutation({
    mutationFn: (req: BacktestRequest) => api.post('/backtest/run', req),
    onSuccess: (res) => setResult(res.data),
  })

  const run = () => {
    if (entryConditions.length === 0) {
      alert('진입 조건을 최소 1개 이상 설정하세요.')
      return
    }
    const config: StrategyConfig = {
      symbol,
      timeframe,
      exchange: 'upbit',
      entry_conditions: entryConditions,
      exit_conditions: exitConditions,
      risk: { stop_loss_pct: stopLoss, take_profit_pct: takeProfit, position_size_pct: positionSize },
    }
    mutation.mutate({
      strategy_config: config,
      exchange: 'upbit',
      initial_capital: initialCapital,
      fee_rate: feeRate,
      walk_forward: walkForward,
    })
  }

  const equityData = result?.equity_curve.map((v, i) => ({
    time: result.timestamps[i] || String(i),
    value: v,
  })) ?? []

  const errorDetail = (mutation.error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  const errorMsg = typeof errorDetail === 'string'
    ? errorDetail
    : Array.isArray(errorDetail)
    ? (errorDetail[0] as { msg?: string })?.msg
    : '알 수 없는 오류'

  return (
    <div className="space-y-4">
      {/* 전략 설정 */}
      <div className="card space-y-4">
        <button
          onClick={() => setConfigOpen(!configOpen)}
          className="flex items-center justify-between w-full"
        >
          <h2 className="font-semibold text-slate-100 flex items-center gap-2">
            <BarChart2 size={18} className="text-brand-500" />
            전략 설정
          </h2>
          {configOpen ? <ChevronUp size={16} className="text-slate-400" /> : <ChevronDown size={16} className="text-slate-400" />}
        </button>

        {configOpen && (
          <div className="space-y-4 pt-1">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-400 mb-1 block">종목 (업비트 KRW 마켓)</label>
                <SymbolSelector value={symbol} onChange={setSymbol} />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">타임프레임</label>
                <select className="input" value={timeframe} onChange={e => setTimeframe(e.target.value)}>
                  {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
                </select>
              </div>
            </div>

            <ConditionBuilder label="진입 조건" conditions={entryConditions} onChange={setEntryConditions} />
            <ConditionBuilder label="청산 조건" conditions={exitConditions} onChange={setExitConditions} />

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-slate-400 mb-1 block">손절 (%)</label>
                <input type="number" className="input" step="0.1" min="0.1"
                  value={stopLoss} onChange={e => setStopLoss(Number(e.target.value))} />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">익절 (%)</label>
                <input type="number" className="input" step="0.1" min="0.1"
                  value={takeProfit} onChange={e => setTakeProfit(Number(e.target.value))} />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">포지션 크기 (%)</label>
                <input type="number" className="input" step="1" min="1" max="100"
                  value={positionSize} onChange={e => setPositionSize(Number(e.target.value))} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 백테스트 파라미터 */}
      <div className="card space-y-4">
        <h2 className="font-semibold text-slate-100">백테스트 파라미터</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">초기 자본 (₩)</label>
            <input type="number" className="input"
              value={initialCapital} onChange={e => setInitialCapital(Number(e.target.value))} />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">수수료율 (업비트 기본 0.05%)</label>
            <input type="number" className="input" step="0.0001"
              value={feeRate} onChange={e => setFeeRate(Number(e.target.value))} />
          </div>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={walkForward}
            onChange={e => setWalkForward(e.target.checked)} className="w-4 h-4 rounded" />
          <span className="text-sm text-slate-300">Walk-Forward 분석 (과최적화 방지)</span>
        </label>

        <button onClick={run} disabled={mutation.isPending}
          className="btn-primary flex items-center gap-2 disabled:opacity-50">
          <Play size={16} />
          {mutation.isPending ? '백테스트 실행 중...' : '백테스트 실행'}
        </button>

        {mutation.isError && (
          <div className="bg-down/10 border border-down/30 rounded-lg px-3 py-2">
            <p className="text-sm text-down">오류: {errorMsg}</p>
          </div>
        )}
      </div>

      {/* 결과 */}
      {result && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="총 거래" value={result.total_trades.toString()} />
            <StatCard label="승률" value={`${result.win_rate.toFixed(1)}%`} color={result.win_rate >= 50 ? 'up' : 'down'} />
            <StatCard
              label="총 수익률"
              value={`${result.total_pnl_pct >= 0 ? '+' : ''}${result.total_pnl_pct.toFixed(2)}%`}
              color={result.total_pnl_pct >= 0 ? 'up' : 'down'}
            />
            <StatCard label="최대 낙폭" value={`-${result.max_drawdown_pct.toFixed(2)}%`} color="down" />
            <StatCard label="샤프 비율" value={result.sharpe_ratio.toFixed(2)} />
            <StatCard label="손익비" value={result.profit_factor === Infinity ? '∞' : result.profit_factor.toFixed(2)} />
            <StatCard label="평균 수익률" value={`${result.avg_trade_pnl_pct.toFixed(2)}%`} />
            <StatCard label="최대 연속 손실" value={`${result.max_consecutive_losses}회`} color="down" />
          </div>

          <EquityChart data={equityData} title="백테스트 자산 곡선 (₩)" />

          {result.walk_forward_results && (
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Walk-Forward 구간별 결과</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-400 border-b border-surface-700">
                      <th className="text-left py-2">구간</th>
                      <th className="text-right">거래</th>
                      <th className="text-right">승률</th>
                      <th className="text-right">수익률</th>
                      <th className="text-right">최대낙폭</th>
                      <th className="text-right">샤프</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.walk_forward_results.map((wf, i) => (
                      <tr key={i} className="border-b border-surface-700/50">
                        <td className="py-2">{i + 1}구간</td>
                        <td className="text-right">{wf.total_trades}</td>
                        <td className="text-right">{wf.win_rate.toFixed(1)}%</td>
                        <td className={clsx('text-right font-medium', wf.total_pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                          {wf.total_pnl_pct >= 0 ? '+' : ''}{wf.total_pnl_pct.toFixed(2)}%
                        </td>
                        <td className="text-right text-down">-{wf.max_drawdown_pct.toFixed(2)}%</td>
                        <td className="text-right">{wf.sharpe_ratio.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="card">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">개별 거래 ({result.trades.length}건)</h3>
            {result.trades.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-4">
                해당 기간에 거래 신호가 발생하지 않았습니다. 조건을 조정해보세요.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-400 border-b border-surface-700">
                      <th className="text-left py-2">진입</th>
                      <th className="text-left">청산</th>
                      <th className="text-right">진입가 (₩)</th>
                      <th className="text-right">청산가 (₩)</th>
                      <th className="text-right">수익률</th>
                      <th className="text-right">사유</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((t, i) => (
                      <tr key={i} className="border-b border-surface-700/50 text-xs">
                        <td className="py-1.5 text-slate-400">{t.entry_at.slice(0, 16)}</td>
                        <td className="text-slate-400">{t.exit_at.slice(0, 16)}</td>
                        <td className="text-right">{t.entry_price.toLocaleString('ko-KR')}</td>
                        <td className="text-right">{t.exit_price.toLocaleString('ko-KR')}</td>
                        <td className={clsx('text-right font-medium', t.pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                          {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                        </td>
                        <td className="text-right text-slate-400">{t.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color?: 'up' | 'down' }) {
  return (
    <div className="card text-center">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={clsx('text-lg font-bold mt-1', color === 'up' ? 'text-up' : color === 'down' ? 'text-down' : 'text-slate-100')}>
        {value}
      </p>
    </div>
  )
}
