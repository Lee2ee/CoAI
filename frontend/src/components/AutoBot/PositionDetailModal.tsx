import { useEffect, useRef, useState } from 'react'
import {
  createChart, type IChartApi, type ISeriesApi,
  type CandlestickData, type HistogramData, type SeriesMarker, type Time,
  LineStyle, ColorType,
} from 'lightweight-charts'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, TrendingDown, TrendingUp, AlertTriangle } from 'lucide-react'
import api from '../../utils/api'
import type { AutoBotPosition, OHLCVBar } from '../../types'
import clsx from 'clsx'
import Tooltip from '../common/Tooltip'
import ConfirmModal from '../common/ConfirmModal'

function fmtCurrency(amount: number, exchangeId?: string): string {
  if (!exchangeId || exchangeId === 'upbit') {
    return amount.toLocaleString('ko-KR') + ' ₩'
  }
  return '$' + amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const ENTRY_COLORS = {
  initial: '#3b82f6',   // 파란색 - 최초 진입
  avg_down: '#f59e0b',  // 주황색 - 물타기
  add: '#22c55e',       // 초록색 - 추매
  pyramid: '#a855f7',   // 보라색 - 피라미딩
}
const ENTRY_LABELS = {
  initial: '진입',
  avg_down: '물타기',
  add: '추매',
  pyramid: '피라미딩',
}

interface Props {
  pos: AutoBotPosition
  maxAvgDown: number
  maxAdd: number
  onClose: () => void
  exchangeId?: string
  feeRate?: number
}

export default function PositionDetailModal({ pos, maxAvgDown, maxAdd, onClose, exchangeId, feeRate = 0 }: Props) {
  const qc = useQueryClient()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  // price line refs - 중복 생성 방지
  const priceLinesRef = useRef<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[]>([])
  const base = pos.symbol.split('/')[0]

  const [timeframe, setTimeframe] = useState('1m')
  // timeframeRef: WebSocket handler stale closure 방지
  const timeframeRef = useRef('1m')
  useEffect(() => { timeframeRef.current = timeframe }, [timeframe])

  // 실시간 현재가 (WebSocket) — 카드·차트 모두 동일 값 사용
  const [currentPrice, setCurrentPrice] = useState(pos.current_price)

  // OHLCV 데이터
  const { data: ohlcv } = useQuery<OHLCVBar[]>({
    queryKey: ['ohlcv-pos', pos.symbol, timeframe],
    queryFn: async () => {
      const res = await api.get('/market/ohlcv', {
        params: { symbol: pos.symbol, timeframe, limit: 200, exchange: exchangeId ?? 'upbit' },
      })
      return res.data.data
    },
    refetchInterval: 30_000,
  })

  // 최신 OHLCV 참조 (WebSocket 핸들러 클로저 스테일 방지)
  const ohlcvRef = useRef<OHLCVBar[]>([])

  // 수동 조작 뮤테이션
  const encSym = pos.symbol.replace('/', '-')

  const addMut = useMutation({
    mutationFn: () => api.post(`/auto-bot/position/${encSym}/add`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const avgDownMut = useMutation({
    mutationFn: () => api.post(`/auto-bot/position/${encSym}/avg-down`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const closeMut = useMutation({
    mutationFn: () => api.post(`/auto-bot/position/${encSym}/close`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['auto-bot-status'] }); onClose() },
  })

  // 차트 초기화
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#1e293b' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#334155' }, horzLines: { color: '#334155' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#334155' },
      timeScale: { borderColor: '#334155', timeVisible: true },
      width: containerRef.current.clientWidth,
      height: 420,
    })
    const candle = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      priceScaleId: 'right',
    })
    candle.priceScale().applyOptions({
      scaleMargins: { top: 0.05, bottom: 0.22 },
    })

    const vol = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    vol.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    })

    chartRef.current = chart
    candleRef.current = candle
    volRef.current = vol

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current!.clientWidth })
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove() }
  }, [])

  // OHLCV 데이터 + 마커 + 가격 라인 업데이트
  useEffect(() => {
    if (!ohlcv || !candleRef.current || !chartRef.current) return

    const candle = candleRef.current

    // ── 캔들 데이터 ────────────────────────────────────────────────
    const candles: CandlestickData[] = ohlcv.map(b => ({
      time: b.time as unknown as Time,
      open: b.open, high: b.high, low: b.low, close: b.close,
    }))
    candle.setData(candles)

    // ── 거래량 히스토그램 ──────────────────────────────────────────
    if (volRef.current) {
      const volumes: HistogramData[] = ohlcv.map(b => ({
        time: b.time as unknown as Time,
        value: b.volume,
        color: b.close >= b.open ? '#22c55e40' : '#ef444440',
      }))
      volRef.current.setData(volumes)
    }

    // ── 진입 마커 (봉 시간에 스냅) ──────────────────────────────────
    // 진입 시각을 가장 가까운 이전 봉 시간으로 맞춤
    const candleTimes = ohlcv.map(b => b.time) // 초 단위 unix

    // ISO 문자열에 Z 없으면 UTC로 명시 (로컬 타임 파싱 방지)
    const toUtcSec = (iso: string) =>
      Math.floor(new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime() / 1000)

    const snapTime = (isoAt: string): Time | null => {
      const entryTs = toUtcSec(isoAt)
      let snapped: number | null = null
      for (const t of candleTimes) {
        if (t <= entryTs) snapped = t
        else break
      }
      return snapped as Time | null
    }

    const markerList: SeriesMarker<Time>[] = []
    for (const e of pos.entries) {
      const t = snapTime(e.at)
      if (t === null) continue
      markerList.push({
        time: t,
        position: 'belowBar',
        color: ENTRY_COLORS[e.type],
        shape: 'arrowUp',
        text: `${ENTRY_LABELS[e.type]} ${fmtCurrency(e.price, exchangeId)}`,
        size: 2,
      })
    }
    const markers = markerList

    markers.sort((a, b) => (a.time as number) - (b.time as number))
    candle.setMarkers(markers)

    // ── 가격 라인 (중복 방지: 기존 제거 후 재생성) ──────────────────
    priceLinesRef.current.forEach(pl => candle.removePriceLine(pl))
    priceLinesRef.current = []

    // title은 비워서 차트 위 텍스트 없앰 → 우측 가격 축 레이블만 표시
    priceLinesRef.current.push(
      candle.createPriceLine({
        price: pos.avg_price,
        color: '#f59e0b',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: '',   // 차트 내 텍스트 없음
      }),
      candle.createPriceLine({
        price: pos.stop_loss_price,
        color: '#ef444480',  // 반투명 빨강
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: '',
      }),
      candle.createPriceLine({
        price: pos.take_profit_price,
        color: '#22c55e80',  // 반투명 초록
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: '',
      }),
    )

    chartRef.current.timeScale().fitContent()
  }, [ohlcv, pos])

  // ohlcvRef 동기화
  useEffect(() => { if (ohlcv) ohlcvRef.current = ohlcv }, [ohlcv])

  // WebSocket 실시간 시세
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/ticker?symbol=${encodeURIComponent(pos.symbol)}&exchange=${exchangeId ?? 'upbit'}`
    const ws = new WebSocket(url)

    const TIMEFRAME_SECONDS: Record<string, number> = {
      '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
      '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800, '1M': 2592000,
    }

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type !== 'ticker') return
      setCurrentPrice(msg.last)
      const bars = ohlcvRef.current
      if (!candleRef.current || bars.length === 0) return

      const period = TIMEFRAME_SECONDS[timeframeRef.current] ?? 60
      const nowSec = Math.floor(Date.now() / 1000)
      const candleStart = Math.floor(nowSec / period) * period
      const last = bars[bars.length - 1]

      if (candleStart > last.time) {
        // 새 봉 시작
        const newBar: OHLCVBar = { time: candleStart, open: msg.last, high: msg.last, low: msg.last, close: msg.last, volume: 0 }
        ohlcvRef.current = [...bars, newBar]
        candleRef.current.update({ time: candleStart as unknown as Time, open: msg.last, high: msg.last, low: msg.last, close: msg.last })
        volRef.current?.update({ time: candleStart as unknown as Time, value: 0, color: '#22c55e40' })
      } else {
        // 현재 봉 업데이트
        const updated = { ...last, high: Math.max(last.high, msg.last), low: Math.min(last.low, msg.last), close: msg.last }
        ohlcvRef.current = [...bars.slice(0, -1), updated]
        candleRef.current.update({ time: last.time as unknown as Time, open: last.open, high: updated.high, low: updated.low, close: msg.last })
        // 거래량 바 색상만 현재가 기준으로 갱신 (volume 값은 OHLCV 주기 갱신에서 업데이트)
        volRef.current?.update({
          time: last.time as unknown as Time,
          value: last.volume,
          color: msg.last >= last.open ? '#22c55e40' : '#ef444440',
        })
      }
    }
    ws.onerror = () => ws.close()

    return () => ws.close()
  }, [pos.symbol])

  const canAvgDown = pos.avg_down_count < maxAvgDown
  const canAdd = pos.add_count < maxAdd
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)

  return (
    <>
    {showCloseConfirm && (
      <ConfirmModal
        message={`${pos.symbol} 포지션을 수동 청산하시겠습니까?`}
        detail={`현재가 ${fmtCurrency(currentPrice, exchangeId)}에 즉시 매도됩니다.`}
        confirmText="청산"
        variant="danger"
        onConfirm={() => closeMut.mutate()}
        onClose={() => setShowCloseConfirm(false)}
      />
    )}
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3" onClick={onClose}>
      <div
        className="bg-surface-800 border border-surface-700 rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-surface-700">
          {(() => {
            const entryFees = pos.total_fee_krw ?? 0
            const estExitFee = currentPrice * pos.total_amount * feeRate
            const liveKrw = Math.round((currentPrice - pos.avg_price) * pos.total_amount - entryFees - estExitFee)
            const livePct = pos.avg_price > 0 ? liveKrw / (pos.avg_price * pos.total_amount) * 100 : 0
            const up = livePct >= 0
            return (
              <div className="flex items-center gap-3">
                <span className="font-bold text-slate-100 text-lg">{pos.symbol}</span>
                <span className={clsx('text-sm font-bold', up ? 'text-up' : 'text-down')}>
                  {up ? '+' : ''}{livePct.toFixed(2)}%
                </span>
                <span className={clsx('text-xs', up ? 'text-up/70' : 'text-down/70')}>
                  ({up ? '+' : ''}{fmtCurrency(liveKrw, exchangeId)})
                </span>
              </div>
            )
          })()}
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={20} />
          </button>
        </div>

        {/* 전략 배너 */}
        <StrategyBanner pos={pos} />

        {/* 투입금액 요약 바 */}
        {(() => {
          const invested = Math.round(pos.avg_price * pos.total_amount)
          const current  = Math.round(currentPrice * pos.total_amount)
          const entryFees = pos.total_fee_krw ?? 0
          const estExitFee = currentPrice * pos.total_amount * feeRate
          const liveUPnlKrw = Math.round((currentPrice - pos.avg_price) * pos.total_amount - entryFees - estExitFee)
          const liveUPnlPct = pos.avg_price > 0 ? liveUPnlKrw / (pos.avg_price * pos.total_amount) * 100 : 0
          const pnlPos   = liveUPnlPct >= 0
          return (
            <div className={clsx(
              'mx-4 mt-3 rounded-lg border px-4 py-2.5 flex items-center gap-6 flex-wrap text-sm',
              pnlPos ? 'bg-up/5 border-up/20' : 'bg-down/5 border-down/20'
            )}>
              <div>
                <p className="text-xs text-slate-500 mb-0.5">투입금액</p>
                <p className="font-mono font-bold text-slate-100 tabular-nums">
                  {fmtCurrency(invested, exchangeId)}
                </p>
              </div>
              <span className="text-slate-600 text-lg">→</span>
              <div>
                <p className="text-xs text-slate-500 mb-0.5">현재가치</p>
                <p className={clsx('font-mono font-bold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
                  {fmtCurrency(current, exchangeId)}
                </p>
              </div>
              <div className="ml-auto text-right">
                <p className="text-xs text-slate-500 mb-0.5 flex items-center justify-end gap-1">
                  미실현 손익
                  <Tooltip text="아직 매도하지 않은 포지션의 현재 손익입니다. 청산 시 실제 수익/손실로 확정됩니다. (Unrealized P&L)" iconOnly />
                </p>
                <p className={clsx('font-mono font-bold tabular-nums text-base', pnlPos ? 'text-up' : 'text-down')}>
                  {pnlPos ? '+' : ''}{fmtCurrency(liveUPnlKrw, exchangeId)}
                  <span className="text-sm ml-1">({pnlPos ? '+' : ''}{liveUPnlPct.toFixed(2)}%)</span>
                </p>
              </div>
            </div>
          )
        })()}

        {/* 포지션 요약 */}
        <div className="px-4 pt-3 pb-2 grid grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
          <InfoBox label="평균단가" value={fmtCurrency(pos.avg_price, exchangeId)} color="amber"
            tooltip="물타기·추매를 포함한 모든 진입 평균 매수가입니다." />
          <InfoBox label="현재가" value={fmtCurrency(currentPrice, exchangeId)} />
          <InfoBox label="보유수량" value={`${pos.total_amount.toFixed(6)} ${base}`} />
          <InfoBox label="진입 횟수" value={`${pos.entries.length}회 (물타기 ${pos.avg_down_count} / 추매 ${pos.add_count})`}
            tooltip="물타기: 하락 시 평단을 낮추기 위한 추가 매수. 추매: 상승 추세에서 수익을 극대화하는 추가 매수." />
          <InfoBox label="손절가" value={fmtCurrency(pos.stop_loss_price, exchangeId)} color="down"
            tooltip="현재가가 이 가격 아래로 내려가면 손실을 줄이기 위해 자동으로 매도합니다. (Stop Loss)" />
          <InfoBox label="익절가" value={fmtCurrency(pos.take_profit_price, exchangeId)} color="up"
            tooltip="현재가가 이 가격 이상으로 오르면 수익을 확정하기 위해 자동으로 매도합니다. (Take Profit)" />
          <InfoBox label="최초 진입" value={pos.entry_at.slice(0, 16).replace('T', ' ')} />
          <InfoBox label="AI 점수" value={`${pos.score}점`} color="brand"
            tooltip="진입 시점에 AI가 평가한 매수 신호 강도입니다. RSI, MACD, 거래량, 추세 등 다양한 지표를 종합해 0~100점으로 산출됩니다." />
        </div>

        {/* 진입 이력 */}
        <div className="px-4 pb-3">
          <p className="text-xs text-slate-500 mb-1.5">진입 이력</p>
          <div className="space-y-1">
            {pos.entries.map((e, i) => {
              const entryKrw = Math.round(e.price * e.amount)
              return (
                <div key={i} className="flex items-center gap-3 text-xs bg-surface-700 rounded px-2.5 py-1.5">
                  <span className="w-12 font-medium flex-shrink-0" style={{ color: ENTRY_COLORS[e.type] }}>
                    {ENTRY_LABELS[e.type]}
                  </span>
                  <span className="font-mono text-slate-200">{fmtCurrency(e.price, exchangeId)}</span>
                  <span className="text-slate-400">{e.amount.toFixed(6)} {base}</span>
                  <span className="font-mono font-semibold text-slate-100 tabular-nums">
                    = {fmtCurrency(entryKrw, exchangeId)}
                  </span>
                  <span className="text-slate-500 ml-auto flex-shrink-0">{e.at.slice(0, 16).replace('T', ' ')}</span>
                </div>
              )
            })}
            {/* 진입 합계 */}
            <div className="flex items-center gap-3 text-xs bg-surface-600 rounded px-2.5 py-1.5 mt-1">
              <span className="w-12 text-slate-400 flex-shrink-0">합계</span>
              <span className="text-slate-400">{pos.total_amount.toFixed(6)} {base}</span>
              <span className="font-mono font-bold text-slate-100 tabular-nums">
                = {fmtCurrency(Math.round(pos.avg_price * pos.total_amount), exchangeId)}
              </span>
              <span className="text-slate-500 ml-auto">(평단 {fmtCurrency(pos.avg_price, exchangeId)})</span>
            </div>
          </div>
        </div>

        {/* 차트 범례 + 타임프레임 */}
        <div className="px-4 pb-1 flex items-center justify-between flex-wrap gap-2">
          <div className="flex gap-3 text-xs text-slate-500 flex-wrap">
            <span className="flex items-center gap-1"><span style={{ color: '#3b82f6' }}>▲</span> 최초 진입</span>
            <Tooltip text="하락 시 평균 단가를 낮추기 위해 추가 매수한 시점입니다. (Averaging Down)">
              <span className="flex items-center gap-1"><span style={{ color: '#f59e0b' }}>▲</span> 물타기</span>
            </Tooltip>
            <Tooltip text="상승 추세에서 수익을 극대화하기 위해 추가 매수한 시점입니다. (Adding to Position)">
              <span className="flex items-center gap-1"><span style={{ color: '#22c55e' }}>▲</span> 추매</span>
            </Tooltip>
            <Tooltip text="모든 진입 가격의 평균값입니다. 이 가격 이상이면 수익, 미만이면 손실 상태입니다.">
              <span className="flex items-center gap-1"><span className="text-amber-400">- -</span> 평단가</span>
            </Tooltip>
            <Tooltip text="현재가가 이 선 아래로 내려가면 자동 매도됩니다. (Stop Loss)">
              <span className="flex items-center gap-1"><span className="text-down">···</span> 손절가</span>
            </Tooltip>
            <Tooltip text="현재가가 이 선 이상으로 오르면 수익을 확정하고 자동 매도됩니다. (Take Profit)">
              <span className="flex items-center gap-1"><span className="text-up">···</span> 익절가</span>
            </Tooltip>
          </div>
          <div className="flex gap-1">
            {(['1m', '5m', '15m', '1h', '4h', '1d', '1w', '1M'] as const).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={clsx(
                  'px-2 py-0.5 rounded text-xs font-medium transition-colors',
                  timeframe === tf
                    ? 'bg-brand-500 text-white'
                    : 'bg-surface-700 text-slate-400 hover:text-slate-200'
                )}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* 차트 */}
        <div className="px-4 pb-3">
          <div ref={containerRef} className="rounded-lg overflow-hidden" />
        </div>

        {/* 수동 조작 버튼 */}
        <div className="px-4 pb-4 flex flex-col gap-2">
          <div className="flex gap-2">
            <button
              onClick={() => avgDownMut.mutate()}
              disabled={!canAvgDown || avgDownMut.isPending}
              className={clsx(
                'flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-sm font-medium border transition-colors',
                canAvgDown
                  ? 'bg-amber-500/10 border-amber-500/40 text-amber-400 hover:bg-amber-500/20'
                  : 'bg-surface-700 border-surface-600 text-slate-500 cursor-not-allowed'
              )}
            >
              <TrendingDown size={15} />
              물타기 ({pos.avg_down_count}/{maxAvgDown})
              <span className="text-xs opacity-70">— 하락 시 추가매수, 평단↓</span>
            </button>
            <button
              onClick={() => addMut.mutate()}
              disabled={!canAdd || addMut.isPending}
              className={clsx(
                'flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-sm font-medium border transition-colors',
                canAdd
                  ? 'bg-up/10 border-up/40 text-up hover:bg-up/20'
                  : 'bg-surface-700 border-surface-600 text-slate-500 cursor-not-allowed'
              )}
            >
              <TrendingUp size={15} />
              추매 ({pos.add_count}/{maxAdd})
              <span className="text-xs opacity-70">— 상승 추세에 추가매수</span>
            </button>
          </div>

          <button
            onClick={() => setShowCloseConfirm(true)}
            disabled={closeMut.isPending}
            className="w-full py-2.5 rounded-lg text-sm font-medium border bg-down/10 border-down/40 text-down hover:bg-down/20 transition-colors flex items-center justify-center gap-1.5"
          >
            <AlertTriangle size={15} />
            수동 청산 (현재가 {fmtCurrency(currentPrice, exchangeId)})
          </button>
        </div>
      </div>
    </div>
    </>
  )
}

const POSITION_STYLE_META: Record<string, { badge: string; border: string }> = {
  scalping: { badge: 'bg-purple-500/20 text-purple-400', border: 'border-purple-500/50' },
  short:    { badge: 'bg-blue-500/20 text-blue-400',     border: 'border-blue-500/50' },
  mid:      { badge: 'bg-amber-500/20 text-amber-400',   border: 'border-amber-500/50' },
  long:     { badge: 'bg-green-500/20 text-green-400',   border: 'border-green-500/50' },
}

const RISK_PROFILE_META: Record<string, { label: string; badge: string; border: string }> = {
  conservative: { label: '보수적', badge: 'bg-blue-500/20 text-blue-400',   border: 'border-blue-500/50' },
  balanced:     { label: '균형',   badge: 'bg-slate-500/20 text-slate-300', border: 'border-slate-500/50' },
  aggressive:   { label: '공격적', badge: 'bg-red-500/20 text-red-400',     border: 'border-red-500/50' },
}

// 전략 타입별 스타일 & 설명
const STRATEGY_META: Record<string, { border: string; bg: string; badge: string; icon: string; desc: string }> = {
  oversold_bounce: {
    border: 'border-blue-500/30', bg: 'bg-blue-500/10', badge: 'bg-blue-500/20 text-blue-300',
    icon: '↘', desc: 'RSI 과매도 구간 반등 노림. 낮은 손절 / 중간 익절로 빠른 수익 실현',
  },
  golden_cross: {
    border: 'border-amber-500/30', bg: 'bg-amber-500/10', badge: 'bg-amber-500/20 text-amber-300',
    icon: '✕', desc: 'EMA20이 EMA50을 상향 돌파 — 추세 전환 신호. 넓은 익절로 추세 수익 극대화',
  },
  macd_momentum: {
    border: 'border-purple-500/30', bg: 'bg-purple-500/10', badge: 'bg-purple-500/20 text-purple-300',
    icon: '↗', desc: 'MACD 골든크로스 모멘텀 포착. 중간 SL / 넓은 TP로 추세 탑승',
  },
  volume_breakout: {
    border: 'border-green-500/30', bg: 'bg-green-500/10', badge: 'bg-green-500/20 text-green-300',
    icon: '⚡', desc: 'MACD 크로스 + 거래량 급증 동시 발생 — 강한 돌파 신호. 가장 넓은 익절 목표',
  },
  standard: {
    border: 'border-surface-600', bg: 'bg-surface-700', badge: 'bg-surface-600 text-slate-400',
    icon: '—', desc: '글로벌 설정의 손절/익절 비율 적용',
  },
}

function StrategyBanner({ pos }: { pos: AutoBotPosition }) {
  const type = pos.strategy_type ?? 'standard'
  const label = pos.strategy_label ?? '표준'
  const meta = STRATEGY_META[type] ?? STRATEGY_META.standard

  // 실제 SL/TP % 역산 (avg_price 기준)
  // SL이 진입가 위로 올라간 경우(SL보호) stop_loss_price > avg_price → 음수 방지
  const slRaw = pos.avg_price > 0
    ? (pos.avg_price - pos.stop_loss_price) / pos.avg_price * 100
    : null
  const slAboveEntry = slRaw !== null && slRaw < 0
  const slPct = slRaw !== null ? Math.abs(slRaw).toFixed(1) : '—'
  const tpPct = pos.avg_price > 0
    ? ((pos.take_profit_price - pos.avg_price) / pos.avg_price * 100).toFixed(1)
    : '—'

  return (
    <div className={clsx('mx-4 mt-2 mb-1 rounded-lg border px-3 py-2.5', meta.border, meta.bg)}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-base">{meta.icon}</span>
        <span className={clsx('text-xs font-bold px-2 py-0.5 rounded', meta.badge)}>
          {label}
        </span>
        {pos.position_style_label && (() => {
          const sm = POSITION_STYLE_META[pos.position_style] ?? { badge: 'bg-surface-600 text-slate-400', border: 'border-surface-500' }
          return (
            <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium border', sm.badge, sm.border)}>
              {pos.position_style_label}
            </span>
          )
        })()}
        {pos.risk_profile && (() => {
          const rm = RISK_PROFILE_META[pos.risk_profile] ?? { label: pos.risk_profile, badge: 'bg-surface-600 text-slate-400', border: 'border-surface-500' }
          return (
            <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium border', rm.badge, rm.border)}>
              {rm.label}
            </span>
          )
        })()}
        <span className="text-xs text-slate-500 ml-auto flex items-center gap-3">
          <span>
            {slAboveEntry ? (
              <Tooltip text="손절가가 진입가보다 위로 올라간 상태입니다. 가격이 하락해도 최소한의 수익이 보장됩니다. (Trailing Stop / SL Protection)">
                <span>SL보호 <span className="text-amber-400 font-semibold">+{slPct}%</span></span>
              </Tooltip>
            ) : (
              <Tooltip text="현재가가 진입가 대비 이 비율만큼 하락하면 자동 매도됩니다. (Stop Loss)">
                <span>손절 <span className="text-down font-semibold">-{slPct}%</span></span>
              </Tooltip>
            )}
          </span>
          <Tooltip text="현재가가 진입가 대비 이 비율만큼 상승하면 수익을 확정하고 자동 매도됩니다. (Take Profit)">
            <span>익절 <span className="text-up font-semibold">+{tpPct}%</span></span>
          </Tooltip>
          <Tooltip text="AI가 진입 시점에 평가한 매수 신호 점수입니다. RSI, MACD, EMA 등 기술 지표와 거래량을 종합 분석합니다.">
            <span>AI점수 <span className="text-brand-400 font-semibold">{pos.score}점</span></span>
          </Tooltip>
        </span>
      </div>
      <p className="text-xs text-slate-400">{meta.desc}</p>
      {pos.signals.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {pos.signals.map(s => (
            <span key={s} className="text-xs bg-surface-700/80 text-slate-400 px-1.5 py-0.5 rounded">{s}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function InfoBox({
  label, value, color, tooltip,
}: {
  label: string
  value: string
  color?: 'up' | 'down' | 'amber' | 'brand'
  tooltip?: string
}) {
  const colorMap: Record<string, string> = {
    up: 'text-up', down: 'text-down', amber: 'text-amber-400', brand: 'text-brand-400',
  }
  const colorClass = color ? (colorMap[color] ?? 'text-slate-100') : 'text-slate-100'

  return (
    <div className="bg-surface-700 rounded px-2.5 py-2">
      <p className="text-slate-500 mb-0.5 flex items-center gap-1">
        {label}
        {tooltip && <Tooltip text={tooltip} iconOnly />}
      </p>
      <p className={clsx('font-semibold font-mono text-xs', colorClass)}>{value}</p>
    </div>
  )
}
