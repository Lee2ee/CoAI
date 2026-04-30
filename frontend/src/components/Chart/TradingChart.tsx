import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type SeriesMarker,
  type Time,
  LineStyle,
  ColorType,
  TickMarkType,
} from 'lightweight-charts'
import { useQuery } from '@tanstack/react-query'
import api from '../../utils/api'
import type { OHLCVBar, Trade, BotState } from '../../types'
import SymbolPicker from './SymbolPicker'

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '1d', '1w', '1M']

const TIMEFRAME_SECONDS: Record<string, number> = {
  '1m': 60, '5m': 300, '15m': 900,
  '1h': 3600, '1d': 86400, '1w': 604800, '1M': 2592000,
}

// 타임프레임별 기본 표시 봉 수 (fitContent 대신 최근 N개를 기본 줌으로)
const TIMEFRAME_DEFAULT_VISIBLE: Record<string, number> = {
  '1m':  180,   // 3시간
  '5m':  144,   // 12시간
  '15m': 96,    // 24시간
  '1h':  72,    // 3일
  '1d':  60,    // 2개월
  '1w':  52,    // 1년
  '1M':  24,    // 2년
}

// 타임프레임별 API 파라미터
const TIMEFRAME_API: Record<string, { tf: string; limit: number }> = {
  '1m':  { tf: '1m',  limit: 1440 },  // 1일
  '5m':  { tf: '5m',  limit: 1000 },  // 3.5일
  '15m': { tf: '15m', limit: 960  },  // 10일
  '1h':  { tf: '1h',  limit: 720  },  // 30일
  '1d':  { tf: '1d',  limit: 500  },  // 1.4년
  '1w':  { tf: '1w',  limit: 200  },  // 3.8년
  '1M':  { tf: '1M',  limit: 60   },  // 5년
}

// ─── 한국 시간 포맷 유틸 ─────────────────────────────────────────────────────
// lightweight-charts timestamp는 UTC seconds. 한국(KST = UTC+9)로 변환해 표시.
function kstDate(utcSec: number) {
  const d = new Date((utcSec + 9 * 3600) * 1000)
  return {
    y:   d.getUTCFullYear(),
    mo:  d.getUTCMonth() + 1,
    d:   d.getUTCDate(),
    h:   d.getUTCHours(),
    min: String(d.getUTCMinutes()).padStart(2, '0'),
  }
}

function fmtTooltip(utcSec: number, tf: string): string {
  const { y, mo, d, h, min } = kstDate(utcSec)
  if (['1d', '1w', '1M'].includes(tf)) return `${y}년 ${mo}월 ${d}일`
  return `${y}년 ${mo}월 ${d}일 ${h}:${min}`
}

function fmtTick(utcSec: number, type: TickMarkType): string {
  const { y, mo, d, h, min } = kstDate(utcSec)
  switch (type) {
    case TickMarkType.Year:          return `${y}년`
    case TickMarkType.Month:         return `${mo}월`
    case TickMarkType.DayOfMonth:    return `${d}일`
    case TickMarkType.Time:          return `${h}:${min}`
    case TickMarkType.TimeWithSeconds: return `${h}:${min}`
    default:                         return `${d}일`
  }
}

// ─── 차트 테마 ────────────────────────────────────────────────────────────────
const CHART_THEME = {
  layout: { background: { type: ColorType.Solid, color: '#1e293b' }, textColor: '#94a3b8' },
  grid: { vertLines: { color: '#334155' }, horzLines: { color: '#334155' } },
  crosshair: { mode: 1 },
  rightPriceScale: { borderColor: '#334155' },
  timeScale: { borderColor: '#334155', timeVisible: true },
}

// ─── 보조지표 계산 ────────────────────────────────────────────────────────────

function calcEMA(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1)
  const out: (number | null)[] = []
  let prev: number | null = null
  let seedSum = 0, seedCount = 0
  for (const v of values) {
    seedSum += v; seedCount++
    if (seedCount < period) { out.push(null); continue }
    if (seedCount === period) { prev = seedSum / period; out.push(prev); continue }
    prev = v * k + prev! * (1 - k)
    out.push(prev)
  }
  return out
}

function calcBB(values: number[], period = 20, mult = 2) {
  const upper: (number | null)[] = [], middle: (number | null)[] = [], lower: (number | null)[] = []
  for (let i = 0; i < values.length; i++) {
    if (i < period - 1) { upper.push(null); middle.push(null); lower.push(null); continue }
    const sl = values.slice(i - period + 1, i + 1)
    const mean = sl.reduce((a, b) => a + b, 0) / period
    const std = Math.sqrt(sl.reduce((a, b) => a + (b - mean) ** 2, 0) / period)
    upper.push(mean + mult * std)
    middle.push(mean)
    lower.push(mean - mult * std)
  }
  return { upper, middle, lower }
}

function calcRSI(values: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = [null]
  for (let i = 1; i < values.length; i++) {
    if (i < period) { out.push(null); continue }
    let gains = 0, losses = 0
    for (let j = i - period + 1; j <= i; j++) {
      const d = values[j] - values[j - 1]
      if (d > 0) gains += d; else losses -= d
    }
    const rs = losses === 0 ? 100 : gains / losses
    out.push(100 - 100 / (1 + rs))
  }
  return out
}

function calcMACD(values: number[], fast = 12, slow = 26, signal = 9) {
  const emaFast = calcEMA(values, fast)
  const emaSlow = calcEMA(values, slow)
  const macdLine: (number | null)[] = emaFast.map((f, i) =>
    f !== null && emaSlow[i] !== null ? f - emaSlow[i]! : null
  )
  const signalLine: (number | null)[] = new Array(macdLine.length).fill(null)
  const k = 2 / (signal + 1)
  let cnt = 0, sum = 0, prev: number | null = null
  for (let i = 0; i < macdLine.length; i++) {
    const v = macdLine[i]
    if (v === null) continue
    sum += v; cnt++
    if (cnt < signal) continue
    if (cnt === signal) { prev = sum / signal; signalLine[i] = prev; continue }
    prev = v * k + prev! * (1 - k)
    signalLine[i] = prev
  }
  const histogram: (number | null)[] = macdLine.map((v, i) =>
    v !== null && signalLine[i] !== null ? v - signalLine[i]! : null
  )
  return { macd: macdLine, signalLine, histogram }
}

function toLineData(times: number[], values: (number | null)[]) {
  return times
    .map((t, i) => ({ time: t as unknown as Time, value: values[i]! }))
    .filter(d => d.value !== null && !isNaN(d.value))
}

// ─── 지표 정의 ────────────────────────────────────────────────────────────────

const IND_DEFS = {
  ema9:   { label: 'EMA9',   color: '#06b6d4', type: 'overlay' as const },
  ema20:  { label: 'EMA20',  color: '#f59e0b', type: 'overlay' as const },
  ema50:  { label: 'EMA50',  color: '#a855f7', type: 'overlay' as const },
  ema200: { label: 'EMA200', color: '#64748b', type: 'overlay' as const },
  bb:     { label: 'BB(20)', color: '#475569', type: 'overlay' as const },
  rsi:    { label: 'RSI',    color: '#818cf8', type: 'osc'     as const },
  macd:   { label: 'MACD',   color: '#34d399', type: 'osc'     as const },
}
type IndKey = keyof typeof IND_DEFS

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  symbol?: string
  exchange?: string
  onSymbolChange?: (symbol: string) => void
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function TradingChart({ symbol: externalSymbol, exchange = 'upbit', onSymbolChange }: Props) {
  const containerRef    = useRef<HTMLDivElement>(null)
  const oscContainerRef = useRef<HTMLDivElement>(null)

  // 메인 차트
  const chartRef        = useRef<IChartApi | null>(null)
  const candleRef       = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef       = useRef<ISeriesApi<'Histogram'> | null>(null)
  const priceLineRef    = useRef<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']> | null>(null)

  // 오버레이 지표 시리즈
  const ema9Ref    = useRef<ISeriesApi<'Line'> | null>(null)
  const ema20Ref   = useRef<ISeriesApi<'Line'> | null>(null)
  const ema50Ref   = useRef<ISeriesApi<'Line'> | null>(null)
  const ema200Ref  = useRef<ISeriesApi<'Line'> | null>(null)
  const bbUpRef    = useRef<ISeriesApi<'Line'> | null>(null)
  const bbMidRef   = useRef<ISeriesApi<'Line'> | null>(null)
  const bbLowRef   = useRef<ISeriesApi<'Line'> | null>(null)

  // 오실레이터 차트
  const oscChartRef    = useRef<IChartApi | null>(null)
  const rsiRef         = useRef<ISeriesApi<'Line'> | null>(null)
  const rsi30Ref       = useRef<ISeriesApi<'Line'> | null>(null)
  const rsi70Ref       = useRef<ISeriesApi<'Line'> | null>(null)
  const macdLineRef    = useRef<ISeriesApi<'Line'> | null>(null)
  const macdSignalRef  = useRef<ISeriesApi<'Line'> | null>(null)
  const macdHistRef    = useRef<ISeriesApi<'Histogram'> | null>(null)

  const dataRef      = useRef<OHLCVBar[]>([])
  const timeframeRef = useRef('1h')

  const [internalSymbol, setInternalSymbol] = useState(externalSymbol ?? 'BTC/KRW')
  const [timeframe, setTimeframe]           = useState('1h')
  const [liveTicker, setLiveTicker]         = useState<{ last: number; change_pct: number } | null>(null)
  const [indicators, setIndicators]         = useState<Record<IndKey, boolean>>({
    ema9: false, ema20: false, ema50: false, ema200: false, bb: false, rsi: false, macd: false,
  })

  const symbol  = externalSymbol ?? internalSymbol
  const hasOsc  = indicators.rsi || indicators.macd

  const handleSymbolChange = (s: string) => { setInternalSymbol(s); onSymbolChange?.(s) }

  // 타임프레임 변경 시: ref 갱신 + timeVisible 토글 (일봉 이상은 시간 불필요)
  useEffect(() => {
    timeframeRef.current = timeframe
    const showTime = !['1d', '1w', '1M'].includes(timeframe)
    chartRef.current?.applyOptions({ timeScale: { timeVisible: showTime } })
  }, [timeframe])

  const toggleInd = (key: IndKey) => {
    setIndicators(prev => {
      const next = { ...prev, [key]: !prev[key] }
      // 오실레이터는 하나만
      if (key === 'rsi'  && next.rsi)  next.macd = false
      if (key === 'macd' && next.macd) next.rsi  = false
      return next
    })
  }

  // ── OHLCV fetch ──────────────────────────────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ['ohlcv', symbol, timeframe, exchange],
    queryFn: async () => {
      const { tf, limit } = TIMEFRAME_API[timeframe] ?? { tf: timeframe, limit: 500 }
      const res = await api.get('/market/ohlcv', { params: { symbol, timeframe: tf, limit, exchange } })
      return res.data.data as OHLCVBar[]
    },
    refetchInterval: 30_000,
  })
  useEffect(() => { if (data) dataRef.current = data }, [data])

  // ── WebSocket 실시간 시세 ─────────────────────────────────────────────────
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/ticker?symbol=${encodeURIComponent(symbol)}&exchange=${exchange}`
    const ws = new WebSocket(url)
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type !== 'ticker') return
      setLiveTicker({ last: msg.last, change_pct: msg.change_pct })
      const bars = dataRef.current
      if (!candleRef.current || bars.length === 0) return
      const period = TIMEFRAME_SECONDS[timeframeRef.current] ?? 60
      const nowSec = Math.floor(Date.now() / 1000)
      const candleStart = Math.floor(nowSec / period) * period
      const last = bars[bars.length - 1]
      if (candleStart > last.time) {
        const newBar: OHLCVBar = { time: candleStart, open: msg.last, high: msg.last, low: msg.last, close: msg.last, volume: 0 }
        dataRef.current = [...bars, newBar]
        candleRef.current.update({ time: candleStart as unknown as Time, open: msg.last, high: msg.last, low: msg.last, close: msg.last })
        volumeRef.current?.update({ time: candleStart as unknown as Time, value: 0, color: '#22c55e40' })
      } else {
        const updated = { ...last, high: Math.max(last.high, msg.last), low: Math.min(last.low, msg.last), close: msg.last }
        dataRef.current = [...bars.slice(0, -1), updated]
        candleRef.current.update({ time: last.time as unknown as Time, open: last.open, high: updated.high, low: updated.low, close: msg.last })
      }
    }
    ws.onerror = () => ws.close()
    return () => ws.close()
  }, [symbol, exchange])

  // ── 거래 내역 (마커용) ────────────────────────────────────────────────────
  const { data: trades = [] } = useQuery<Trade[]>({
    queryKey: ['trades-chart', symbol],
    queryFn: async () => (await api.get('/trades/', { params: { symbol, limit: 200 } })).data,
    refetchInterval: 15_000,
  })

  // ── 봇 포지션 ─────────────────────────────────────────────────────────────
  const { data: botStatus = [] } = useQuery<BotState[]>({
    queryKey: ['bot-status'],
    queryFn: async () => (await api.get('/strategies/bot-status')).data,
    refetchInterval: 5_000,
  })
  const activePosition = botStatus.find(b => b.symbol === symbol && b.position)?.position ?? null
  const activeBotInfo  = botStatus.find(b => b.symbol === symbol && b.position) ?? null

  // ── 차트 초기화 (최초 1회) ───────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !oscContainerRef.current) return

    // 메인 차트
    const chart = createChart(containerRef.current, {
      ...CHART_THEME,
      width: containerRef.current.clientWidth,
      height: 340,
      localization: {
        timeFormatter: (t: number) => fmtTooltip(t, timeframeRef.current),
      },
      timeScale: {
        ...CHART_THEME.timeScale,
        tickMarkFormatter: (t: number, type: TickMarkType) => fmtTick(t, type),
      },
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderDownColor: '#ef4444', borderUpColor: '#22c55e',
      wickDownColor: '#ef4444', wickUpColor: '#22c55e',
    })
    candleRef.current = candleSeries

    const volumeSeries = chart.addHistogramSeries({
      color: '#334155', priceFormat: { type: 'volume' }, priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    volumeRef.current = volumeSeries

    // 오버레이 시리즈 (처음엔 숨김)
    const lineOpts = { lineWidth: 1 as const, priceLineVisible: false as const, lastValueVisible: false as const, crosshairMarkerVisible: false as const }
    ema9Ref.current   = chart.addLineSeries({ ...lineOpts, color: '#06b6d4', visible: false })
    ema20Ref.current  = chart.addLineSeries({ ...lineOpts, color: '#f59e0b', visible: false })
    ema50Ref.current  = chart.addLineSeries({ ...lineOpts, color: '#a855f7', visible: false })
    ema200Ref.current = chart.addLineSeries({ ...lineOpts, color: '#64748b', visible: false })
    bbUpRef.current   = chart.addLineSeries({ ...lineOpts, color: '#475569', lineStyle: LineStyle.Dashed, visible: false })
    bbMidRef.current  = chart.addLineSeries({ ...lineOpts, color: '#64748b', visible: false })
    bbLowRef.current  = chart.addLineSeries({ ...lineOpts, color: '#475569', lineStyle: LineStyle.Dashed, visible: false })

    // 오실레이터 차트 (항상 생성, CSS로 숨김)
    const oscChart = createChart(oscContainerRef.current, {
      ...CHART_THEME,
      width: oscContainerRef.current.clientWidth,
      height: 130,
      timeScale: { ...CHART_THEME.timeScale, visible: false },
      rightPriceScale: { borderColor: '#334155', scaleMargins: { top: 0.1, bottom: 0.1 } },
    })
    oscChartRef.current = oscChart

    const oscLineOpts = { lineWidth: 1 as const, priceLineVisible: false as const, lastValueVisible: true as const, crosshairMarkerVisible: false as const }
    rsiRef.current        = oscChart.addLineSeries({ ...oscLineOpts, color: '#818cf8', visible: false })
    rsi30Ref.current      = oscChart.addLineSeries({ ...oscLineOpts, color: '#ef444460', lineStyle: LineStyle.Dashed, lastValueVisible: false, visible: false })
    rsi70Ref.current      = oscChart.addLineSeries({ ...oscLineOpts, color: '#22c55e60', lineStyle: LineStyle.Dashed, lastValueVisible: false, visible: false })
    macdLineRef.current   = oscChart.addLineSeries({ ...oscLineOpts, color: '#34d399', visible: false })
    macdSignalRef.current = oscChart.addLineSeries({ ...oscLineOpts, color: '#f87171', lastValueVisible: false, visible: false })
    macdHistRef.current   = oscChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false, visible: false })

    // 타임스케일 동기화
    let syncing = false
    chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (syncing || !range) return
      syncing = true; oscChart.timeScale().setVisibleLogicalRange(range); syncing = false
    })
    oscChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (syncing || !range) return
      syncing = true; chart.timeScale().setVisibleLogicalRange(range); syncing = false
    })

    // 리사이즈
    const ro = new ResizeObserver(() => {
      if (containerRef.current)    chart.applyOptions({ width: containerRef.current.clientWidth })
      if (oscContainerRef.current) oscChart.applyOptions({ width: oscContainerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)
    ro.observe(oscContainerRef.current)

    return () => {
      ro.disconnect()
      chart.remove(); oscChart.remove()
      chartRef.current = null; oscChartRef.current = null
      candleRef.current = null; volumeRef.current = null
      ema9Ref.current = null; ema20Ref.current = null; ema50Ref.current = null; ema200Ref.current = null
      bbUpRef.current = null; bbMidRef.current = null; bbLowRef.current = null
      rsiRef.current = null; rsi30Ref.current = null; rsi70Ref.current = null
      macdLineRef.current = null; macdSignalRef.current = null; macdHistRef.current = null
      priceLineRef.current = null
    }
  }, [])

  // ── OHLCV + 지표 데이터 업데이트 ─────────────────────────────────────────
  useEffect(() => {
    if (!data || !candleRef.current || !volumeRef.current) return

    const candles: CandlestickData[] = data.map(b => ({
      time: b.time as unknown as Time, open: b.open, high: b.high, low: b.low, close: b.close,
    }))
    const volumes = data.map(b => ({
      time: b.time as unknown as Time, value: b.volume,
      color: b.close >= b.open ? '#22c55e40' : '#ef444440',
    }))
    candleRef.current.setData(candles)
    volumeRef.current.setData(volumes)

    // 타임프레임별 기본 줌: 전체 압축 대신 최근 N개 봉을 보기 좋게 표시
    const total   = data.length
    const visible = TIMEFRAME_DEFAULT_VISIBLE[timeframe] ?? 72
    if (total > 0) {
      chartRef.current?.timeScale().setVisibleLogicalRange({
        from: Math.max(0, total - visible),
        to:   total + 2,   // 오른쪽 여백
      })
    }

    const closes = data.map(b => b.close)
    const times  = data.map(b => b.time)

    // EMA
    ema9Ref.current?.setData(toLineData(times, calcEMA(closes, 9)))
    ema20Ref.current?.setData(toLineData(times, calcEMA(closes, 20)))
    ema50Ref.current?.setData(toLineData(times, calcEMA(closes, 50)))
    ema200Ref.current?.setData(toLineData(times, calcEMA(closes, 200)))

    // BB
    const bb = calcBB(closes)
    bbUpRef.current?.setData(toLineData(times, bb.upper))
    bbMidRef.current?.setData(toLineData(times, bb.middle))
    bbLowRef.current?.setData(toLineData(times, bb.lower))

    // RSI
    const rsiVals = calcRSI(closes)
    rsiRef.current?.setData(toLineData(times, rsiVals))
    rsi30Ref.current?.setData(times.map(t => ({ time: t as unknown as Time, value: 30 })))
    rsi70Ref.current?.setData(times.map(t => ({ time: t as unknown as Time, value: 70 })))

    // MACD
    const { macd, signalLine, histogram } = calcMACD(closes)
    macdLineRef.current?.setData(toLineData(times, macd))
    macdSignalRef.current?.setData(toLineData(times, signalLine))
    macdHistRef.current?.setData(
      times
        .map((t, i) => ({
          time: t as unknown as Time,
          value: histogram[i] ?? 0,
          color: (histogram[i] ?? 0) >= 0 ? '#22c55e80' : '#ef444480',
        }))
        .filter((_, i) => histogram[i] !== null)
    )

  }, [data, timeframe])

  // ── 지표 표시/숨김 ────────────────────────────────────────────────────────
  useEffect(() => {
    ema9Ref.current?.applyOptions({ visible: indicators.ema9 })
    ema20Ref.current?.applyOptions({ visible: indicators.ema20 })
    ema50Ref.current?.applyOptions({ visible: indicators.ema50 })
    ema200Ref.current?.applyOptions({ visible: indicators.ema200 })
    bbUpRef.current?.applyOptions({ visible: indicators.bb })
    bbMidRef.current?.applyOptions({ visible: indicators.bb })
    bbLowRef.current?.applyOptions({ visible: indicators.bb })
    rsiRef.current?.applyOptions({ visible: indicators.rsi })
    rsi30Ref.current?.applyOptions({ visible: indicators.rsi })
    rsi70Ref.current?.applyOptions({ visible: indicators.rsi })
    macdLineRef.current?.applyOptions({ visible: indicators.macd })
    macdSignalRef.current?.applyOptions({ visible: indicators.macd })
    macdHistRef.current?.applyOptions({ visible: indicators.macd })
    // 오실레이터 패널 표시 후 너비 갱신
    const hasOscNow = indicators.rsi || indicators.macd
    if (hasOscNow && oscContainerRef.current && oscChartRef.current) {
      setTimeout(() => {
        oscChartRef.current?.applyOptions({ width: oscContainerRef.current!.clientWidth })
        oscChartRef.current?.timeScale().fitContent()
      }, 0)
    }
  }, [indicators])

  // ── 매매 마커 ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!candleRef.current || !data || data.length === 0) return
    const toUtcSec = (iso: string) =>
      Math.floor(new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').getTime() / 1000)
    const markers: SeriesMarker<Time>[] = []
    for (const trade of trades) {
      markers.push({ time: toUtcSec(trade.entry_at) as Time, position: 'belowBar', color: '#22c55e', shape: 'arrowUp', text: `매수 ${trade.entry_price.toLocaleString('ko-KR')}`, size: 1 })
      const pos = trade.pnl_pct >= 0
      markers.push({ time: toUtcSec(trade.exit_at) as Time, position: 'aboveBar', color: pos ? '#22c55e' : '#ef4444', shape: 'arrowDown', text: `매도 ${pos ? '+' : ''}${trade.pnl_pct.toFixed(2)}%`, size: 1 })
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number))
    candleRef.current.setMarkers(markers)
  }, [trades, data])

  // ── 포지션 평균가 라인 ────────────────────────────────────────────────────
  useEffect(() => {
    if (!candleRef.current) return
    if (priceLineRef.current) { candleRef.current.removePriceLine(priceLineRef.current); priceLineRef.current = null }
    if (activePosition) {
      priceLineRef.current = candleRef.current.createPriceLine({
        price: activePosition.entry_price, color: '#f59e0b', lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true,
        title: `평균매수가 ${activePosition.entry_price.toLocaleString('ko-KR')}`,
      })
    }
  }, [activePosition])

  const isUp = (liveTicker?.change_pct ?? 0) >= 0

  return (
    <div className="card">
      {/* ── 헤더: 종목 + 가격 + 타임프레임 ── */}
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <SymbolPicker value={symbol} onChange={handleSymbolChange} />
          {liveTicker && (
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-slate-100 tabular-nums">
                {liveTicker.last?.toLocaleString('ko-KR')}
                <span className="text-sm font-normal text-slate-400 ml-1">₩</span>
              </span>
              <span className={`text-sm font-medium ${isUp ? 'text-up' : 'text-down'}`}>
                {isUp ? '+' : ''}{liveTicker.change_pct?.toFixed(2)}%
              </span>
            </div>
          )}
          {isLoading && <span className="text-xs text-slate-500">로딩 중...</span>}
        </div>
        <div className="flex gap-1 flex-wrap">
          {TIMEFRAMES.map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                timeframe === tf ? 'bg-brand-500 text-white' : 'bg-surface-700 text-slate-400 hover:text-slate-200'
              }`}>{tf}</button>
          ))}
        </div>
      </div>

      {/* ── 지표 선택 툴바 ── */}
      <div className="flex items-center gap-1.5 flex-wrap mb-2 pb-2 border-b border-surface-700">
        <span className="text-xs text-slate-500">지표</span>
        {(Object.entries(IND_DEFS) as [IndKey, typeof IND_DEFS[IndKey]][]).map(([key, def]) => {
          const active = indicators[key]
          const isSeparator = key === 'rsi' // RSI 앞에 구분선
          return (
            <span key={key} className="flex items-center">
              {isSeparator && <span className="w-px h-4 bg-surface-600 mx-1" />}
              <button
                onClick={() => toggleInd(key)}
                className="text-xs px-2 py-0.5 rounded border transition-colors font-medium"
                style={active
                  ? { backgroundColor: def.color + '33', borderColor: def.color, color: def.color }
                  : { backgroundColor: '#1e293b', borderColor: '#334155', color: '#94a3b8' }
                }
              >{def.label}</button>
            </span>
          )
        })}
        {/* 활성 오버레이 범례 */}
        <div className="ml-auto flex items-center gap-2 flex-wrap">
          {indicators.ema9   && <span className="text-xs" style={{ color: '#06b6d4' }}>─ EMA9</span>}
          {indicators.ema20  && <span className="text-xs" style={{ color: '#f59e0b' }}>─ EMA20</span>}
          {indicators.ema50  && <span className="text-xs" style={{ color: '#a855f7' }}>─ EMA50</span>}
          {indicators.ema200 && <span className="text-xs" style={{ color: '#64748b' }}>─ EMA200</span>}
          {indicators.bb     && <span className="text-xs text-slate-500">── BB(20,2)</span>}
        </div>
      </div>

      {/* ── 포지션 배너 ── */}
      {activePosition && activeBotInfo && (
        <div className="mb-2 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 flex items-center gap-4 flex-wrap text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-amber-300 font-medium">{activeBotInfo.name} 포지션 보유 중</span>
          </div>
          <div className="flex gap-4 text-slate-300 flex-wrap">
            <span>평균단가: <span className="font-mono font-semibold text-amber-300">{activePosition.entry_price.toLocaleString('ko-KR')} ₩</span></span>
            <span>보유수량: <span className="font-mono font-semibold text-slate-100">{activePosition.amount.toFixed(6)} {symbol.split('/')[0]}</span></span>
            <span>미실현손익: <span className={`font-semibold ${activePosition.unrealized_pnl_pct >= 0 ? 'text-up' : 'text-down'}`}>{activePosition.unrealized_pnl_pct >= 0 ? '+' : ''}{activePosition.unrealized_pnl_pct.toFixed(2)}%</span></span>
            {activePosition.stop_loss_price   && <span>손절가: <span className="text-down font-mono">{activePosition.stop_loss_price.toLocaleString('ko-KR')} ₩</span></span>}
            {activePosition.take_profit_price && <span>익절가: <span className="text-up font-mono">{activePosition.take_profit_price.toLocaleString('ko-KR')} ₩</span></span>}
          </div>
        </div>
      )}

      {/* ── 마커 범례 ── */}
      {trades.length > 0 && (
        <div className="mb-1.5 flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1"><span className="text-up">▲</span> 매수</span>
          <span className="flex items-center gap-1"><span className="text-down">▼</span> 매도</span>
          {activePosition && <span className="flex items-center gap-1"><span className="text-amber-400">- -</span> 평균매수가</span>}
          <span className="ml-auto">{trades.length}건 표시</span>
        </div>
      )}

      {/* ── 메인 차트 ── */}
      <div ref={containerRef} />

      {/* ── 오실레이터 서브패널 ── */}
      <div className={hasOsc ? 'block' : 'hidden'}>
        <div className="flex items-center gap-3 px-1 pt-1 pb-0.5 text-xs text-slate-500 border-t border-surface-700">
          {indicators.rsi && (
            <>
              <span style={{ color: '#818cf8' }}>● RSI(14)</span>
              <span style={{ color: '#ef444480' }}>── 30</span>
              <span style={{ color: '#22c55e80' }}>── 70</span>
            </>
          )}
          {indicators.macd && (
            <>
              <span style={{ color: '#34d399' }}>● MACD(12,26,9)</span>
              <span style={{ color: '#f87171' }}>● Signal</span>
              <span className="text-slate-600">Histogram</span>
            </>
          )}
        </div>
        <div ref={oscContainerRef} />
      </div>
    </div>
  )
}
