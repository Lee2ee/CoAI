import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Bot, TrendingUp, TrendingDown, Wallet, Sparkles, ChevronDown, ChevronUp, PenLine, Search } from 'lucide-react'
import TradingChart from '../components/Chart/TradingChart'
import StrategyCard from '../components/Strategy/StrategyCard'
import StrategyForm from '../components/Strategy/StrategyForm'
import AutoTradePanel from '../components/AutoBot/AutoTradePanel'
import Modal from '../components/common/Modal'
import BacktestPage from './BacktestPage'
import api from '../utils/api'
import { useSettingsStore } from '../store/settings'
import type { Strategy, BotState, Portfolio, Trade } from '../types'
import clsx from 'clsx'

// ─── 포트폴리오 요약 ────────────────────────────────────────────────────────

function PortfolioSummary({ stats, strategies }: {
  stats: { total: number; win_rate: number; total_pnl: number; total_pnl_pct: number } | undefined
  strategies: Strategy[]
}) {
  const { data: portfolio } = useQuery<Portfolio>({
    queryKey: ['portfolio'],
    queryFn: async () => {
      const res = await api.get('/exchange-accounts/portfolio')
      return res.data
    },
    refetchInterval: 60_000,
  })

  const activeBots = strategies.filter(s => s.is_active).length
  const pnlPct = stats?.total_pnl_pct ?? 0
  const pnlKrw = portfolio?.has_real_account && portfolio.total_krw > 0 && pnlPct !== 0
    ? portfolio.total_krw * pnlPct / (100 + pnlPct)
    : null

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {/* 총 자산 */}
      <div className="card col-span-2 lg:col-span-1">
        <div className="flex items-center gap-2 mb-1">
          <Wallet size={14} className="text-slate-400" />
          <span className="text-xs text-slate-400">총 자산</span>
        </div>
        {portfolio?.has_real_account ? (
          <>
            <p className="text-xl font-bold text-slate-100">
              {portfolio.total_krw.toLocaleString('ko-KR')} <span className="text-sm font-normal text-slate-400">₩</span>
            </p>
            {portfolio.accounts.length > 1 && (
              <p className="text-xs text-slate-500 mt-0.5">{portfolio.accounts.length}개 계정 합산</p>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-500 mt-1">실거래 계정 없음</p>
        )}
      </div>

      {/* 손익 */}
      <div className="card">
        <div className="flex items-center gap-2 mb-1">
          {pnlPct >= 0
            ? <TrendingUp size={14} className="text-up" />
            : <TrendingDown size={14} className="text-down" />
          }
          <span className="text-xs text-slate-400">총 손익</span>
        </div>
        <p className={clsx('text-xl font-bold', pnlPct >= 0 ? 'text-up' : 'text-down')}>
          {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
        </p>
        {pnlKrw !== null && (
          <p className={clsx('text-xs mt-0.5', pnlKrw >= 0 ? 'text-up/70' : 'text-down/70')}>
            {pnlKrw >= 0 ? '+' : ''}{Math.round(pnlKrw).toLocaleString('ko-KR')} ₩
          </p>
        )}
      </div>

      {/* 승률 */}
      <div className="card">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs text-slate-400">승률</span>
        </div>
        <p className="text-xl font-bold text-slate-100">
          {(stats?.win_rate ?? 0).toFixed(1)}%
        </p>
        <p className="text-xs text-slate-500 mt-0.5">총 {stats?.total ?? 0}건</p>
      </div>

      {/* 활성 봇 */}
      <div className="card">
        <div className="flex items-center gap-2 mb-1">
          <Bot size={14} className="text-brand-400" />
          <span className="text-xs text-slate-400">활성 봇</span>
        </div>
        <p className="text-xl font-bold text-slate-100">{activeBots}</p>
        <p className="text-xs text-slate-500 mt-0.5">전략 {strategies.length}개 중</p>
      </div>
    </div>
  )
}

// ─── 전략 실행 상세 모달 ────────────────────────────────────────────────────

function StrategyDetailModal({ strategy }: { strategy: Strategy }) {
  const symbol = strategy.config.symbol
  const [chartSymbol, setChartSymbol] = useState(symbol)

  const { data: state, } = useQuery({
    queryKey: ['strategy-state', strategy.id],
    queryFn: async () => {
      const res = await api.get(`/strategies/${strategy.id}/state`)
      return res.data as { position: { symbol: string; direction: string; entry_price: number; amount: number; stop_loss_price: number; take_profit_price: number; unrealized_pnl: number; unrealized_pnl_pct: number; entry_at: string } | null }
    },
    refetchInterval: 5000,
  })

  const { data: trades = [] } = useQuery<Trade[]>({
    queryKey: ['strategy-trades', strategy.id],
    queryFn: async () => {
      const res = await api.get(`/trades/?strategy_id=${strategy.id}&limit=20`)
      return res.data as Trade[]
    },
    refetchInterval: 10000,
  })

  const pos = state?.position

  return (
    <div className="space-y-4">
      {/* 차트 */}
      <TradingChart symbol={chartSymbol} onSymbolChange={setChartSymbol} />

      {/* 현재 포지션 */}
      <div>
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">현재 포지션</h3>
        {pos ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="bg-surface-700 rounded-lg p-3">
              <p className="text-xs text-slate-400">진입가</p>
              <p className="text-sm font-semibold text-slate-100 mt-0.5">{pos.entry_price.toLocaleString()}</p>
            </div>
            <div className="bg-surface-700 rounded-lg p-3">
              <p className="text-xs text-slate-400">수량</p>
              <p className="text-sm font-semibold text-slate-100 mt-0.5">{pos.amount.toFixed(6)}</p>
            </div>
            <div className="bg-surface-700 rounded-lg p-3">
              <p className="text-xs text-slate-400">미실현 손익</p>
              <p className={clsx('text-sm font-semibold mt-0.5', pos.unrealized_pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
              </p>
            </div>
            <div className="bg-surface-700 rounded-lg p-3">
              <p className="text-xs text-slate-400">손절 / 익절</p>
              <p className="text-xs text-slate-100 mt-0.5">
                <span className="text-down">{pos.stop_loss_price.toLocaleString()}</span>
                {' / '}
                <span className="text-up">{pos.take_profit_price.toLocaleString()}</span>
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-500 bg-surface-700 rounded-lg px-4 py-3">포지션 없음</p>
        )}
      </div>

      {/* 거래 내역 */}
      <div>
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">최근 거래</h3>
        {trades.length === 0 ? (
          <p className="text-sm text-slate-500 bg-surface-700 rounded-lg px-4 py-3">거래 내역 없음</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-surface-700">
                  <th className="text-left pb-2 font-normal">진입</th>
                  <th className="text-left pb-2 font-normal">청산</th>
                  <th className="text-right pb-2 font-normal">진입가</th>
                  <th className="text-right pb-2 font-normal">청산가</th>
                  <th className="text-right pb-2 font-normal">손익</th>
                  <th className="text-right pb-2 font-normal">사유</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-700">
                {trades.map(t => (
                  <tr key={t.id} className="text-slate-300">
                    <td className="py-2 pr-3">{new Date(t.entry_at).toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                    <td className="py-2 pr-3">{new Date(t.exit_at).toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                    <td className="py-2 pr-3 text-right">{t.entry_price.toLocaleString()}</td>
                    <td className="py-2 pr-3 text-right">{t.exit_price.toLocaleString()}</td>
                    <td className={clsx('py-2 pr-3 text-right font-semibold', t.pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                      {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 text-right text-slate-400">{t.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── 봇 현황 ────────────────────────────────────────────────────────────────

function BotStatusPanel() {
  const [expanded, setExpanded] = useState(true)

  const { data: bots = [] } = useQuery<BotState[]>({
    queryKey: ['bot-status'],
    queryFn: async () => {
      const res = await api.get('/strategies/bot-status')
      return res.data
    },
    refetchInterval: 5_000,
  })

  if (bots.length === 0) return null

  return (
    <div className="card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full"
      >
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-up animate-pulse" />
          <h2 className="font-semibold text-slate-100 text-sm">봇 현황</h2>
          <span className="text-xs text-slate-500">{bots.length}개 실행 중</span>
        </div>
        {expanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
      </button>

      {expanded && (
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-2">
          {bots.map((bot) => (
            <BotCard key={bot.strategy_id} bot={bot} />
          ))}
        </div>
      )}
    </div>
  )
}

function BotCard({ bot }: { bot: BotState }) {
  const pos = bot.position
  const pnlPositive = pos ? pos.unrealized_pnl_pct >= 0 : null

  return (
    <div className="bg-surface-700 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="text-sm font-medium text-slate-200">{bot.name}</span>
          <span className="ml-2 text-xs text-slate-500">{bot.symbol} · {bot.timeframe}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {bot.is_paper && (
            <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">모의</span>
          )}
          {pos ? (
            <span className="text-xs bg-up/20 text-up px-1.5 py-0.5 rounded">포지션 보유</span>
          ) : (
            <span className="text-xs bg-surface-600 text-slate-400 px-1.5 py-0.5 rounded">대기 중</span>
          )}
        </div>
      </div>

      {pos ? (
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div>
            <p className="text-slate-500">방향</p>
            <p className={clsx('font-medium', pos.direction === 'long' ? 'text-up' : 'text-down')}>
              {pos.direction === 'long' ? '매수 (Long)' : '매도 (Short)'}
            </p>
          </div>
          <div>
            <p className="text-slate-500">진입가</p>
            <p className="text-slate-200 font-mono">{pos.entry_price.toLocaleString('ko-KR')}</p>
          </div>
          <div>
            <p className="text-slate-500">미실현 손익</p>
            <p className={clsx('font-medium', pnlPositive ? 'text-up' : 'text-down')}>
              {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
            </p>
          </div>
          {pos.stop_loss_price && (
            <div>
              <p className="text-slate-500">손절가</p>
              <p className="text-down font-mono">{pos.stop_loss_price.toLocaleString('ko-KR')}</p>
            </div>
          )}
          {pos.take_profit_price && (
            <div>
              <p className="text-slate-500">익절가</p>
              <p className="text-up font-mono">{pos.take_profit_price.toLocaleString('ko-KR')}</p>
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-500">진입 조건 모니터링 중...</p>
      )}
    </div>
  )
}

// ─── AI 자동 전략 생성 ───────────────────────────────────────────────────────

function AutoStrategyModal({ onClose, symbol }: { onClose: () => void; symbol: string }) {
  const qc = useQueryClient()
  const [reqSymbol, setReqSymbol] = useState(symbol || 'BTC/KRW')
  const [timeframe, setTimeframe] = useState('1h')
  const [result, setResult] = useState<{ strategy_id: number; name: string; config: unknown; market_summary: string } | null>(null)
  const [symbolSearch, setSymbolSearch] = useState('')
  const [symbolOpen, setSymbolOpen] = useState(false)
  const symbolRef = useRef<HTMLDivElement>(null)

  const TIMEFRAMES = ['15m', '1h', '4h', '1d']

  const { data: allSymbols = [] } = useQuery<string[]>({
    queryKey: ['auto-strategy-symbols'],
    queryFn: async () => {
      const res = await api.get('/auto-strategy/symbols')
      return res.data.symbols as string[]
    },
    staleTime: 5 * 60_000,
  })

  const filteredSymbols = useMemo(() => {
    const q = symbolSearch.toUpperCase()
    return q ? allSymbols.filter(s => s.includes(q)) : allSymbols
  }, [allSymbols, symbolSearch])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (symbolRef.current && !symbolRef.current.contains(e.target as Node)) setSymbolOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const mutation = useMutation({
    mutationFn: () =>
      api.post('/auto-strategy/generate', {
        symbol: reqSymbol,
        timeframe,
        exchange: 'upbit',
      }),
    onSuccess: (res) => {
      setResult(res.data)
      qc.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const errMsg = (() => {
    if (!mutation.isError) return null
    const err = mutation.error as { response?: { status?: number; data?: { detail?: string } } }
    const detail = err.response?.data?.detail
    if (detail) return detail
    if (err.response?.status === 429) return 'API 요청 한도를 초과했습니다. 1~2분 후 다시 시도하세요.'
    return 'AI 분석 실패'
  })()

  return (
    <div className="space-y-4">
      {!result ? (
        <>
          <p className="text-sm text-slate-400">
            현재 시장 데이터와 보조지표를 AI가 분석하여 최적의 매매 전략을 자동으로 구성합니다.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div ref={symbolRef} className="relative">
              <label className="text-xs text-slate-400 mb-1 block">종목 선택</label>
              <button
                type="button"
                onClick={() => setSymbolOpen(!symbolOpen)}
                className="input w-full flex items-center justify-between text-left"
              >
                <span>{reqSymbol}</span>
                <ChevronDown size={14} className="text-slate-400 flex-shrink-0" />
              </button>
              {symbolOpen && (
                <div className="absolute z-50 mt-1 w-full bg-surface-800 border border-surface-600 rounded-lg shadow-xl overflow-hidden">
                  <div className="p-2 border-b border-surface-700">
                    <div className="flex items-center gap-2 bg-surface-700 rounded px-2">
                      <Search size={13} className="text-slate-400" />
                      <input
                        autoFocus
                        className="bg-transparent text-sm text-slate-200 placeholder-slate-500 py-1.5 flex-1 outline-none"
                        placeholder="종목 검색..."
                        value={symbolSearch}
                        onChange={e => setSymbolSearch(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {filteredSymbols.slice(0, 100).map(s => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => { setReqSymbol(s); setSymbolOpen(false); setSymbolSearch('') }}
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-surface-700 transition-colors ${s === reqSymbol ? 'text-brand-400 bg-brand-500/10' : 'text-slate-300'}`}
                      >
                        {s}
                      </button>
                    ))}
                    {filteredSymbols.length === 0 && (
                      <p className="text-xs text-slate-500 px-3 py-3">검색 결과 없음</p>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">타임프레임</label>
              <div className="flex gap-1.5">
                {TIMEFRAMES.map(tf => (
                  <button
                    key={tf}
                    onClick={() => setTimeframe(tf)}
                    className={clsx(
                      'flex-1 py-2 rounded text-xs font-medium border transition-colors',
                      timeframe === tf
                        ? 'bg-brand-500/20 border-brand-500 text-brand-400'
                        : 'bg-surface-700 border-surface-600 text-slate-400'
                    )}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-brand-500/10 border border-brand-500/30 rounded-lg p-3 text-xs text-slate-300">
            AI가 RSI, MACD, EMA, 볼린저 밴드 등 주요 보조지표를 종합 분석하여 진입/청산 조건과 리스크 관리를 자동 설정합니다. 생성된 전략은 모의 거래로 시작됩니다.
          </div>

          {errMsg && (
            <div className="bg-down/10 border border-down/30 rounded-lg px-3 py-2 space-y-1">
              <p className="text-sm text-down">{errMsg}</p>
              {(mutation.error as { response?: { status?: number } })?.response?.status === 429 && (
                <p className="text-xs text-slate-400">Gemini 무료 플랜: 분당 15회 · 일 1,500회 제한. 모델을 <b>gemini-2.0-flash</b>로 설정했는지 확인하세요.</p>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={onClose} className="btn-ghost flex-1">취소</button>
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Sparkles size={15} />
              {mutation.isPending ? 'AI 분석 중...' : 'AI 전략 생성'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="bg-up/10 border border-up/30 rounded-lg px-3 py-2">
            <p className="text-sm text-up font-medium">전략이 생성되어 저장됐습니다.</p>
            <p className="text-xs text-slate-400 mt-0.5">{result.name} (모의거래로 시작)</p>
          </div>

          <div>
            <p className="text-xs text-slate-400 mb-1">AI 분석 요약</p>
            <pre className="bg-surface-700 rounded-lg p-3 text-xs text-slate-300 overflow-auto max-h-32 whitespace-pre-wrap">
              {result.market_summary}
            </pre>
          </div>

          <div>
            <p className="text-xs text-slate-400 mb-1">생성된 전략 설정</p>
            <pre className="bg-surface-700 rounded-lg p-3 text-xs text-slate-300 overflow-auto max-h-36">
              {JSON.stringify(result.config, null, 2)}
            </pre>
          </div>

          <button onClick={onClose} className="btn-primary w-full">확인</button>
        </>
      )}
    </div>
  )
}

// ─── 대시보드 메인 ───────────────────────────────────────────────────────────

// ─── 새 전략 드롭다운 버튼 ──────────────────────────────────────────────────

function NewStrategyButton({
  aiEnabled,
  onAI,
  onManual,
}: {
  aiEnabled: boolean
  onAI: () => void
  onManual: () => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // AI 미사용 시 바로 직접 만들기로
  if (!aiEnabled) {
    return (
      <button onClick={onManual} className="btn-primary flex items-center gap-1.5">
        <Plus size={15} /> 새 전략
      </button>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="btn-primary flex items-center gap-1.5"
      >
        <Plus size={15} />
        새 전략
        <ChevronDown size={13} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 bg-surface-700 border border-surface-600 rounded-lg shadow-xl z-50 overflow-hidden">
          <button
            onClick={() => { setOpen(false); onAI() }}
            className="flex items-center gap-2.5 w-full px-3 py-2.5 text-sm text-slate-200 hover:bg-surface-600 transition-colors"
          >
            <Sparkles size={14} className="text-brand-400 flex-shrink-0" />
            AI 자동 생성
          </button>
          <div className="border-t border-surface-600" />
          <button
            onClick={() => { setOpen(false); onManual() }}
            className="flex items-center gap-2.5 w-full px-3 py-2.5 text-sm text-slate-200 hover:bg-surface-600 transition-colors"
          >
            <PenLine size={14} className="text-slate-400 flex-shrink-0" />
            직접 만들기
          </button>
        </div>
      )}
    </div>
  )
}

// ─── 대시보드 메인 ───────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { aiEnabled } = useSettingsStore()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showAutoModal, setShowAutoModal] = useState(false)
  const [backtestStrategy, setBacktestStrategy] = useState<Strategy | null>(null)
  const [detailStrategy, setDetailStrategy] = useState<Strategy | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/KRW')

  const { data: strategies = [], isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const res = await api.get('/strategies/')
      return res.data as Strategy[]
    },
    refetchInterval: 10_000,
  })

  const { data: stats } = useQuery({
    queryKey: ['trade-stats'],
    queryFn: async () => {
      const res = await api.get('/trades/stats')
      return res.data
    },
    refetchInterval: 30_000,
  })

  return (
    <div className="space-y-4">
      {/* 포트폴리오 요약 */}
      <PortfolioSummary stats={stats} strategies={strategies} />

      {/* 봇 현황 */}
      <BotStatusPanel />

      {/* 차트 */}
      <TradingChart symbol={selectedSymbol} onSymbolChange={setSelectedSymbol} />

      {/* 전략 목록 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-slate-100">전략</h2>
          <NewStrategyButton
            aiEnabled={aiEnabled}
            onAI={() => setShowAutoModal(true)}
            onManual={() => setShowCreateModal(true)}
          />
        </div>

        {isLoading ? (
          <p className="text-slate-400 text-sm">로딩 중...</p>
        ) : strategies.length === 0 ? (
          <div className="card text-center py-8">
            <p className="text-slate-400">전략이 없습니다.</p>
            <p className="text-slate-500 text-sm mt-1">새 전략 버튼을 눌러 시작하세요.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {strategies.map((s) => (
              <StrategyCard
                key={s.id}
                strategy={s}
                onBacktest={() => {
                  setSelectedSymbol(s.config.symbol)
                  setBacktestStrategy(s)
                }}
                onDetail={() => setDetailStrategy(s)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 자동매매봇 */}
      <AutoTradePanel />

      {/* 모달: AI 전략 생성 */}
      {showAutoModal && (
        <Modal title="AI 전략 자동 생성" onClose={() => setShowAutoModal(false)} overflowVisible>
          <AutoStrategyModal onClose={() => setShowAutoModal(false)} symbol={selectedSymbol} />
        </Modal>
      )}

      {/* 모달: 전략 직접 생성 */}
      {showCreateModal && (
        <Modal title="새 전략 만들기" onClose={() => setShowCreateModal(false)} wide>
          <StrategyForm onClose={() => setShowCreateModal(false)} />
        </Modal>
      )}

      {/* 모달: 전략 실행 상세 */}
      {detailStrategy && (
        <Modal
          title={`${detailStrategy.name} — 실행 현황`}
          onClose={() => setDetailStrategy(null)}
          wide
        >
          <StrategyDetailModal strategy={detailStrategy} />
        </Modal>
      )}

      {/* 모달: 백테스트 */}
      {backtestStrategy && (
        <Modal
          title={`백테스트: ${backtestStrategy.name}`}
          onClose={() => setBacktestStrategy(null)}
          wide
        >
          <BacktestPage initialConfig={backtestStrategy.config} />
        </Modal>
      )}
    </div>
  )
}
