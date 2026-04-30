import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import api from '../../utils/api'
import type { Trade } from '../../types'
import clsx from 'clsx'

const EXIT_REASON_LABEL: Record<string, string> = {
  signal: '신호',
  stop_loss: '손절',
  take_profit: '익절',
  trailing_stop: '트레일링',
}

interface Props {
  strategyId?: number
}

export default function TradeHistory({ strategyId }: Props) {
  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['trades', strategyId],
    queryFn: async () => {
      const params = strategyId ? { strategy_id: strategyId } : {}
      const res = await api.get('/trades/', { params })
      return res.data as Trade[]
    },
  })

  if (isLoading) return <div className="card text-slate-400 text-sm">로딩 중...</div>

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">거래 내역</h3>
      {trades.length === 0 ? (
        <p className="text-slate-500 text-sm text-center py-6">거래 내역이 없습니다.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-400 border-b border-surface-700">
                <th className="text-left py-2 pr-4">심볼</th>
                <th className="text-right pr-4">진입가</th>
                <th className="text-right pr-4">청산가</th>
                <th className="text-right pr-4">수익률</th>
                <th className="text-right pr-4">청산 사유</th>
                <th className="text-right">시간</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-surface-700/50 hover:bg-surface-700/30 transition-colors"
                >
                  <td className="py-2 pr-4 font-medium">{t.symbol}</td>
                  <td className="text-right pr-4 text-slate-300">
                    ${t.entry_price.toLocaleString()}
                  </td>
                  <td className="text-right pr-4 text-slate-300">
                    ${t.exit_price.toLocaleString()}
                  </td>
                  <td className={clsx('text-right pr-4 font-medium', t.pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                    {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
                  </td>
                  <td className="text-right pr-4">
                    <span
                      className={clsx(
                        'text-xs px-1.5 py-0.5 rounded',
                        t.exit_reason === 'stop_loss'
                          ? 'bg-down/20 text-down'
                          : t.exit_reason === 'take_profit'
                          ? 'bg-up/20 text-up'
                          : 'bg-surface-600 text-slate-300'
                      )}
                    >
                      {EXIT_REASON_LABEL[t.exit_reason] ?? t.exit_reason}
                    </span>
                  </td>
                  <td className="text-right text-xs text-slate-400">
                    {format(new Date(t.exit_at), 'MM/dd HH:mm')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
