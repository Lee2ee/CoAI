import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Pause, Trash2, BarChart2, Eye, AlertTriangle } from 'lucide-react'
import api from '../../utils/api'
import type { Strategy, ExchangeAccount } from '../../types'
import clsx from 'clsx'
import ConfirmModal from '../common/ConfirmModal'
import Modal from '../common/Modal'

// ─── 거래소별 수수료 ─────────────────────────────────────────────────────────

const EXCHANGES = [
  { id: 'upbit',   label: 'Upbit',   quote: 'KRW',  fee: 0.05 },
  { id: 'binance', label: 'Binance', quote: 'USDT', fee: 0.10 },
  { id: 'bybit',   label: 'Bybit',   quote: 'USDT', fee: 0.10 },
]

// ─── 시작 설정 모달 ──────────────────────────────────────────────────────────

function StartModal({ strategy, onClose }: { strategy: Strategy; onClose: () => void }) {
  const qc = useQueryClient()
  const [exchange, setExchange] = useState(strategy.config.exchange ?? 'upbit')
  const [isPaper, setIsPaper] = useState(true)

  const { data: accounts = [] } = useQuery<ExchangeAccount[]>({
    queryKey: ['exchange-accounts'],
    queryFn: async () => (await api.get('/exchange-accounts/')).data,
    staleTime: 30_000,
  })
  const connectedExchanges = new Set(
    accounts.filter(a => a.is_paper === isPaper && a.is_active).map(a => a.exchange)
  )

  // accounts 로딩 후 또는 isPaper 변경 시 현재 선택 거래소가 유효하지 않으면 보정
  useEffect(() => {
    if (accounts.length === 0) return
    if (!connectedExchanges.has(exchange)) {
      const first = [...connectedExchanges][0]
      if (first) setExchange(first)
      // first가 없으면(해당 모드 계정 전혀 없음) exchange 그대로 유지 — 버튼 disabled로 차단
    }
  }, [accounts, isPaper]) // eslint-disable-line react-hooks/exhaustive-deps

  const exInfo = EXCHANGES.find(e => e.id === exchange) ?? EXCHANGES[0]
  const canStart = connectedExchanges.has(exchange)

  const mutation = useMutation({
    mutationFn: () =>
      api.patch(`/strategies/${strategy.id}`, {
        config: { ...strategy.config, exchange },
        is_paper: isPaper,
        is_active: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
      onClose()
    },
  })

  const errMsg = mutation.isError
    ? ((mutation.error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? '시작 실패')
    : null

  return (
    <div className="space-y-5">
      {/* 거래소 선택 */}
      <div>
        <label className="text-xs text-slate-400 mb-2 block">거래소</label>
        <div className="grid grid-cols-3 gap-2">
          {EXCHANGES.map(ex => {
            const connected = connectedExchanges.has(ex.id)
            return (
              <button
                key={ex.id}
                disabled={!connected}
                onClick={() => connected && setExchange(ex.id)}
                title={!connected ? `${ex.label} ${isPaper ? '모의투자' : '실거래'} 계정이 등록되지 않았습니다` : undefined}
                className={clsx(
                  'flex flex-col items-center py-3 rounded-lg border text-sm font-medium transition-colors',
                  !connected
                    ? 'bg-surface-800 border-surface-700 text-slate-600 cursor-not-allowed'
                    : exchange === ex.id
                      ? 'bg-brand-500/20 border-brand-500 text-brand-300'
                      : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
                )}
              >
                <span>{ex.label}</span>
                <span className="text-xs mt-0.5 font-normal opacity-70">
                  {connected ? `${ex.quote} · ${ex.fee}%` : '미등록'}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* 거래 모드 */}
      <div>
        <label className="text-xs text-slate-400 mb-2 block">거래 모드</label>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setIsPaper(true)}
            className={clsx(
              'py-3 rounded-lg border text-sm font-medium transition-colors',
              isPaper
                ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
            )}
          >
            모의거래
            <p className="text-xs font-normal mt-0.5 opacity-70">가상 자금으로 연습</p>
          </button>
          <button
            onClick={() => setIsPaper(false)}
            className={clsx(
              'py-3 rounded-lg border text-sm font-medium transition-colors',
              !isPaper
                ? 'bg-down/20 border-down text-red-300'
                : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
            )}
          >
            실거래
            <p className="text-xs font-normal mt-0.5 opacity-70">실제 자금 사용</p>
          </button>
        </div>
      </div>

      {/* 수수료 요약 */}
      <div className="bg-surface-700 rounded-lg px-4 py-3 flex items-center justify-between text-sm">
        <span className="text-slate-400">적용 수수료</span>
        <span className="text-slate-100 font-semibold">{exInfo.fee}% <span className="text-xs font-normal text-slate-400">/ 거래</span></span>
      </div>

      {/* 실거래 경고 */}
      {!isPaper && (
        <div className="flex gap-2 bg-down/10 border border-down/30 rounded-lg px-3 py-2.5">
          <AlertTriangle size={15} className="text-down flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-300">실거래는 실제 자금이 사용됩니다. 거래소 계정 API 키가 등록되어 있어야 합니다.</p>
        </div>
      )}

      {!canStart && connectedExchanges.size === 0 && accounts.length > 0 && (
        <p className="text-xs text-slate-400">
          {isPaper ? '모의투자' : '실거래'} 계정이 등록된 거래소가 없습니다. 거래소 계정 메뉴에서 API 키를 등록하세요.
        </p>
      )}

      {errMsg && (
        <p className="text-sm text-down">{errMsg}</p>
      )}

      <div className="flex gap-3 pt-1">
        <button onClick={onClose} className="btn-ghost flex-1">취소</button>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || !canStart}
          className="btn-primary flex-1 disabled:opacity-50"
        >
          {mutation.isPending ? '시작 중...' : !canStart ? '계정 미등록' : '시작'}
        </button>
      </div>
    </div>
  )
}

// ─── 전략 카드 ───────────────────────────────────────────────────────────────

interface Props {
  strategy: Strategy
  onBacktest?: () => void
  onDetail?: () => void
}

export default function StrategyCard({ strategy, onBacktest, onDetail }: Props) {
  const qc = useQueryClient()
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showStartModal, setShowStartModal] = useState(false)
  const [showPositionAlert, setShowPositionAlert] = useState(false)

  const handleDeleteClick = async () => {
    if (strategy.is_active) {
      const res = await api.get(`/strategies/${strategy.id}/state`)
      if (res.data?.position) {
        setShowPositionAlert(true)
        return
      }
    }
    setShowDeleteConfirm(true)
  }

  const stopMutation = useMutation({
    mutationFn: () => api.patch(`/strategies/${strategy.id}`, { is_active: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/strategies/${strategy.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  const pnlPositive = strategy.total_pnl_pct >= 0
  const exchange = strategy.config.exchange ?? 'upbit'
  const exInfo = EXCHANGES.find(e => e.id === exchange)

  return (
    <>
      {showDeleteConfirm && (
        <ConfirmModal
          message={`'${strategy.name}' 전략을 삭제하시겠습니까?`}
          detail="삭제 후에는 복구할 수 없습니다."
          confirmText="삭제"
          variant="danger"
          onConfirm={() => deleteMutation.mutate()}
          onClose={() => setShowDeleteConfirm(false)}
        />
      )}

      {showStartModal && (
        <Modal title="전략 시작 설정" onClose={() => setShowStartModal(false)}>
          <StartModal strategy={strategy} onClose={() => setShowStartModal(false)} />
        </Modal>
      )}

      {showPositionAlert && (
        <Modal title="삭제 불가" onClose={() => setShowPositionAlert(false)}>
          <div className="space-y-4">
            <div className="flex gap-3 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
              <AlertTriangle size={20} className="text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm text-slate-100">포지션이 열려 있는 전략은 삭제할 수 없습니다.</p>
                <p className="text-xs text-slate-400">보유 포지션을 청산한 후 전략을 삭제하세요.</p>
              </div>
            </div>
            <button onClick={() => setShowPositionAlert(false)} className="btn-primary w-full">확인</button>
          </div>
        </Modal>
      )}

      <div className="card hover:border-surface-600 transition-colors">
        {/* 헤더 */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-semibold text-slate-100">{strategy.name}</h3>
              <span className={clsx(
                'text-xs px-1.5 py-0.5 rounded',
                strategy.is_paper
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-down/20 text-red-400'
              )}>
                {strategy.is_paper ? '모의' : '실거래'}
              </span>
              {exInfo && (
                <span className="text-xs bg-surface-600 text-slate-400 px-1.5 py-0.5 rounded">
                  {exInfo.label} {exInfo.fee}%
                </span>
              )}
              {strategy.is_active && (
                <span className="flex items-center gap-1 text-xs bg-up/20 text-up px-1.5 py-0.5 rounded">
                  <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
                  실행 중
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {strategy.config.symbol} · {strategy.config.timeframe}
            </p>
          </div>

          <div className="flex items-center gap-1">
            {/* 백테스트 */}
            <button
              onClick={onBacktest}
              className="p-1.5 text-slate-400 hover:text-brand-400 transition-colors"
              title="백테스트"
            >
              <BarChart2 size={16} />
            </button>

            {/* 실행 중 상세 보기 */}
            {strategy.is_active && (
              <button
                onClick={onDetail}
                className="p-1.5 text-slate-400 hover:text-brand-400 transition-colors"
                title="실행 현황 상세 보기"
              >
                <Eye size={16} />
              </button>
            )}

            {/* 시작 / 정지 */}
            {strategy.is_active ? (
              <button
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
                className="p-1.5 text-up hover:text-down transition-colors"
                title="정지"
              >
                <Pause size={16} />
              </button>
            ) : (
              <button
                onClick={() => setShowStartModal(true)}
                className="p-1.5 text-slate-400 hover:text-up transition-colors"
                title="시작 설정"
              >
                <Play size={16} />
              </button>
            )}

            {/* 삭제 */}
            <button
              onClick={handleDeleteClick}
              className="p-1.5 text-slate-400 hover:text-down transition-colors"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        {/* 성과 지표 */}
        <div className="grid grid-cols-4 gap-2">
          <Metric label="총 거래" value={strategy.total_trades.toString()} />
          <Metric label="승률" value={`${strategy.win_rate.toFixed(1)}%`} />
          <Metric
            label="총 수익률"
            value={`${pnlPositive ? '+' : ''}${strategy.total_pnl_pct.toFixed(2)}%`}
            color={pnlPositive ? 'up' : 'down'}
          />
          <Metric
            label="최대 낙폭"
            value={`-${strategy.max_drawdown_pct.toFixed(2)}%`}
            color="down"
          />
        </div>

        {/* 리스크 설정 요약 */}
        <div className="flex gap-3 mt-3 pt-3 border-t border-surface-700 text-xs text-slate-400">
          <span>손절 {strategy.config.risk.stop_loss_pct}%</span>
          <span>익절 {strategy.config.risk.take_profit_pct}%</span>
          <span>포지션 {strategy.config.risk.position_size_pct}%</span>
          <span>샤프 {strategy.sharpe_ratio.toFixed(2)}</span>
        </div>
      </div>
    </>
  )
}

function Metric({ label, value, color }: { label: string; value: string; color?: 'up' | 'down' }) {
  return (
    <div className="bg-surface-700 rounded-lg p-2 text-center">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={clsx(
        'text-sm font-semibold mt-0.5',
        color === 'up' ? 'text-up' : color === 'down' ? 'text-down' : 'text-slate-100'
      )}>
        {value}
      </p>
    </div>
  )
}
