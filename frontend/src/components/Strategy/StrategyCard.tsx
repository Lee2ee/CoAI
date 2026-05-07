import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Play, Pause, Trash2, TrendingUp, TrendingDown, BarChart2 } from 'lucide-react'
import api from '../../utils/api'
import type { Strategy } from '../../types'
import clsx from 'clsx'
import ConfirmModal from '../common/ConfirmModal'

interface Props {
  strategy: Strategy
  onBacktest?: () => void
}

export default function StrategyCard({ strategy, onBacktest }: Props) {
  const qc = useQueryClient()
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const toggleMutation = useMutation({
    mutationFn: (is_active: boolean) =>
      api.patch(`/strategies/${strategy.id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/strategies/${strategy.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })

  const pnlPositive = strategy.total_pnl_pct >= 0

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
    <div className="card hover:border-surface-600 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-slate-100">{strategy.name}</h3>
            {strategy.is_paper && (
              <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">모의</span>
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
          <button
            onClick={onBacktest}
            className="p-1.5 text-slate-400 hover:text-brand-400 transition-colors"
            title="백테스트"
          >
            <BarChart2 size={16} />
          </button>
          <button
            onClick={() => toggleMutation.mutate(!strategy.is_active)}
            disabled={toggleMutation.isPending}
            className={clsx(
              'p-1.5 transition-colors',
              strategy.is_active
                ? 'text-up hover:text-down'
                : 'text-slate-400 hover:text-up'
            )}
            title={strategy.is_active ? '정지' : '시작'}
          >
            {strategy.is_active ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
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

function Metric({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color?: 'up' | 'down'
}) {
  return (
    <div className="bg-surface-700 rounded-lg p-2 text-center">
      <p className="text-xs text-slate-400">{label}</p>
      <p
        className={clsx(
          'text-sm font-semibold mt-0.5',
          color === 'up' ? 'text-up' : color === 'down' ? 'text-down' : 'text-slate-100'
        )}
      >
        {value}
      </p>
    </div>
  )
}
