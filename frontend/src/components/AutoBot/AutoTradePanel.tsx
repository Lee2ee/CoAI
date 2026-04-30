import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot, Play, Square, RefreshCw, Zap, Settings2,
  TrendingDown, TrendingUp, Clock, Brain,
  ShieldAlert, Sparkles, LogOut, BarChart2,
} from 'lucide-react'
import api from '../../utils/api'
import type {
  AutoBotStatus, AutoBotPosition, AutoBotTradeLog, ScanResult,
  StylePreset, AutoBotTradeDB, AutoBotTradeStats, AiAnalysisLogEntry,
} from '../../types'
import PositionDetailModal from './PositionDetailModal'
import clsx from 'clsx'

// ─── 봇 동작 시간 표시 훅 ──────────────────────────────────────────────────

function useUptime(startedAt: string | null): string {
  const [, setTick] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!startedAt) { setTick(0); return }
    intervalRef.current = setInterval(() => setTick(t => t + 1), 1000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [startedAt])

  if (!startedAt) return ''
  const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  if (secs < 60) return `${secs}초`
  if (secs < 3600) return `${Math.floor(secs / 60)}분 ${secs % 60}초`
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60)
  return `${h}시간 ${m}분`
}

// ─── 스타일 메타 (프론트 표시용) ─────────────────────────────────────────────

const STYLE_META: Record<string, {
  color: string
  border: string
  badge: string
  desc: string
  volDesc: string
}> = {
  scalping: {
    color: 'text-purple-400',
    border: 'border-purple-500/50',
    badge: 'bg-purple-500/20 text-purple-400',
    desc: '수 분 내 빠른 진입·청산. 변동성 낮고 유동성 최상위 종목만.',
    volDesc: '일 거래대금 50억+ (상위 10~15종목)',
  },
  short: {
    color: 'text-brand-400',
    border: 'border-brand-500/50',
    badge: 'bg-brand-500/20 text-brand-400',
    desc: '수 시간~1일 내 수익 실현. 유동성 높은 주요 알트 포함.',
    volDesc: '일 거래대금 20억+ (상위 15~20종목)',
  },
  mid: {
    color: 'text-amber-400',
    border: 'border-amber-500/50',
    badge: 'bg-amber-500/20 text-amber-400',
    desc: '수 일~수 주 추세 추종. 넓은 TP로 큰 움직임 포착.',
    volDesc: '일 거래대금 5억+ (상위 20~25종목)',
  },
  long: {
    color: 'text-up',
    border: 'border-up/50',
    badge: 'bg-up/20 text-up',
    desc: '수 주~수 개월 장기 보유. 깊은 손절, 큰 익절 목표.',
    volDesc: '일 거래대금 1억+ (전체 스캔)',
  },
}

const STYLE_ORDER = ['scalping', 'short', 'mid', 'long'] as const
const STYLE_LABEL: Record<string, string> = {
  scalping: '초단타', short: '단타', mid: '중장기', long: '장기',
}

// ─── 설정 모달 ───────────────────────────────────────────────────────────────

function SettingsModal({
  settings,
  onSave,
  onClose,
}: {
  settings: AutoBotStatus['settings']
  onSave: (s: Partial<AutoBotStatus['settings']>) => void
  onClose: () => void
}) {
  const [form, setForm] = useState({ ...settings })
  const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d']

  const set = (key: string, val: number | boolean | string) =>
    setForm(f => ({ ...f, [key]: val }))

  // 스타일 프리셋 조회
  const { data: presets } = useQuery<Record<string, StylePreset>>({
    queryKey: ['style-presets'],
    queryFn: async () => (await api.get('/auto-bot/style-presets')).data,
    staleTime: Infinity,
  })

  const applyStyle = (styleKey: string) => {
    const preset = presets?.[styleKey]
    if (!preset) return
    setForm(f => ({
      ...f,
      trading_style: styleKey,
      timeframe: preset.timeframe,
      scan_interval_min: preset.scan_interval_min,
      stop_loss_pct: preset.stop_loss_pct,
      take_profit_pct: preset.take_profit_pct,
      min_score: preset.min_score,
      position_size_pct: preset.position_size_pct,
      max_positions: preset.max_positions,
      auto_avg_down: preset.auto_avg_down,
      avg_down_threshold_pct: preset.avg_down_threshold_pct,
      max_avg_down: preset.max_avg_down,
      auto_add: preset.auto_add,
      add_threshold_pct: preset.add_threshold_pct,
      max_add: preset.max_add,
    }))
  }

  const currentStyle = form.trading_style ?? 'short'
  const currentMeta = STYLE_META[currentStyle] ?? STYLE_META.short

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      {/* flex-col + max-h로 헤더·스타일·버튼 고정, 설정만 스크롤 */}
      <div
        className="bg-surface-800 border border-surface-700 rounded-xl shadow-2xl w-full max-w-md flex flex-col"
        style={{ maxHeight: 'min(90vh, 680px)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── 고정 헤더 ── */}
        <div className="px-5 pt-5 pb-3 flex-shrink-0">
          <h3 className="font-semibold text-slate-100">자동매매 설정</h3>
        </div>

        {/* ── 고정 스타일 셀렉터 ── */}
        <div className="px-5 pb-3 flex-shrink-0 space-y-2">
          <p className="text-xs text-slate-400 font-medium">매매 스타일</p>
          <div className="grid grid-cols-4 gap-1.5">
            {STYLE_ORDER.map(key => {
              const meta = STYLE_META[key]
              const active = currentStyle === key
              return (
                <button
                  key={key}
                  onClick={() => applyStyle(key)}
                  className={clsx(
                    'py-2 rounded-lg text-xs font-semibold border transition-colors',
                    active
                      ? `${meta.badge} ${meta.border}`
                      : 'bg-surface-700 border-surface-600 text-slate-400 hover:text-slate-200'
                  )}
                >
                  {STYLE_LABEL[key]}
                </button>
              )
            })}
          </div>
          <div className={clsx('rounded-lg border px-3 py-2 text-xs', currentMeta.border, 'bg-surface-700/50')}>
            <p className={clsx('font-medium', currentMeta.color)}>{currentMeta.desc}</p>
            <p className="text-slate-500 mt-0.5">거래량 기준: {currentMeta.volDesc}</p>
          </div>
        </div>

        <div className="border-t border-surface-700 flex-shrink-0" />

        {/* ── 스크롤 영역 ── */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">

          {/* 기본 설정 — 2열 그리드 */}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-2">기본 설정</p>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="최대 포지션" min={1} max={10}
                value={form.max_positions} onChange={v => set('max_positions', v)} />
              <NumRow label="투입 (%)" min={1} max={100} step={1}
                value={form.position_size_pct} onChange={v => set('position_size_pct', v)} />
              <NumRow label="손절 (%)" min={0.5} max={20} step={0.5}
                value={form.stop_loss_pct} onChange={v => set('stop_loss_pct', v)} />
              <NumRow label="익절 (%)" min={1} max={50} step={0.5}
                value={form.take_profit_pct} onChange={v => set('take_profit_pct', v)} />
              <NumRow label="최소 점수" min={30} max={90} step={5}
                value={form.min_score} onChange={v => set('min_score', v)} />
              <NumRow label="스캔 주기 (분)" min={1} max={1440}
                value={form.scan_interval_min} onChange={v => set('scan_interval_min', v)} />
            </div>
          </div>

          {/* 타임프레임 */}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-2">지표 타임프레임</p>
            <div className="flex gap-1.5 flex-wrap">
              {TIMEFRAMES.map(tf => (
                <button key={tf} onClick={() => set('timeframe', tf)}
                  className={clsx(
                    'px-2.5 py-1 rounded text-xs font-medium border transition-colors',
                    form.timeframe === tf
                      ? 'bg-brand-500/20 border-brand-500 text-brand-400'
                      : 'bg-surface-700 border-surface-600 text-slate-400 hover:text-slate-200'
                  )}
                >{tf}</button>
              ))}
            </div>
          </div>

          {/* 물타기 */}
          <div className="border-t border-surface-700 pt-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs text-slate-400 font-medium">물타기</p>
              <Toggle checked={!!form.auto_avg_down} onChange={v => set('auto_avg_down', v)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="발동 하락 (%)" min={1} max={20} step={0.5}
                value={form.avg_down_threshold_pct} onChange={v => set('avg_down_threshold_pct', v)} />
              <NumRow label="최대 횟수" min={1} max={5}
                value={form.max_avg_down} onChange={v => set('max_avg_down', v)} />
            </div>
          </div>

          {/* 추매 */}
          <div className="border-t border-surface-700 pt-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs text-slate-400 font-medium">추매</p>
              <Toggle checked={!!form.auto_add} onChange={v => set('auto_add', v)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="발동 상승 (%)" min={1} max={20} step={0.5}
                value={form.add_threshold_pct} onChange={v => set('add_threshold_pct', v)} />
              <NumRow label="최대 횟수" min={1} max={3}
                value={form.max_add} onChange={v => set('max_add', v)} />
            </div>
          </div>
        </div>

        {/* ── 고정 버튼 ── */}
        <div className="border-t border-surface-700 flex-shrink-0 px-5 pt-3 pb-4 space-y-3">
          <p className="text-xs text-slate-500 text-center leading-relaxed">
            저장 즉시 적용됩니다. <span className="text-amber-400">기존 포지션의 손절/익절가는 변경되지 않습니다.</span>
          </p>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-ghost flex-1 text-sm">취소</button>
            <button onClick={() => { onSave(form); onClose() }} className="btn-primary flex-1 text-sm">저장</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function NumRow({
  label, value, onChange, min, max, step = 1,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-500">{label}</span>
      <input
        type="number" min={min} max={max} step={step}
        className="input text-right text-sm py-1"
        value={value}
        onChange={e => onChange(+e.target.value)}
      />
    </label>
  )
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={clsx(
        'relative inline-flex h-6 w-12 flex-shrink-0 rounded-full border-2 border-transparent transition-colors',
        checked ? 'bg-brand-500' : 'bg-surface-600'
      )}
    >
      <span className={clsx(
        'absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow transition-transform',
        checked ? 'translate-x-6' : 'translate-x-0'
      )} />
    </button>
  )
}

// ─── 전략 색상 맵 ────────────────────────────────────────────────────────────

const STRATEGY_COLORS: Record<string, string> = {
  oversold_bounce: 'bg-blue-500/20 text-blue-400',
  golden_cross:    'bg-amber-500/20 text-amber-400',
  macd_momentum:   'bg-purple-500/20 text-purple-400',
  volume_breakout: 'bg-up/20 text-up',
  standard:        'bg-surface-600 text-slate-400',
}

// ─── 포지션 카드 (클릭 시 상세 모달) ────────────────────────────────────────

function PositionCard({ pos, onClick }: { pos: AutoBotPosition; onClick: () => void }) {
  const pnlPos = pos.unrealized_pnl_pct >= 0
  const base = pos.symbol.split('/')[0]
  const investedKrw = Math.round(pos.avg_price * pos.total_amount)
  const currentKrw  = Math.round(pos.current_price * pos.total_amount)

  return (
    <div
      onClick={onClick}
      className="bg-surface-700 rounded-lg p-3 space-y-2 cursor-pointer hover:bg-surface-600 transition-colors border border-surface-600 hover:border-brand-500/40"
    >
      {/* 심볼 + 배지 + 손익% */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-slate-100">{pos.symbol}</span>
          {pos.strategy_label && (
            <span className={clsx(
              'text-xs px-1.5 py-0.5 rounded font-medium',
              STRATEGY_COLORS[pos.strategy_type] ?? STRATEGY_COLORS.standard
            )}>
              {pos.strategy_label}
            </span>
          )}
          {pos.position_style_label && (
            <span className={clsx(
              'text-xs px-1.5 py-0.5 rounded font-medium border',
              STYLE_META[pos.position_style]?.badge ?? 'bg-surface-600 text-slate-400',
              STYLE_META[pos.position_style]?.border ?? 'border-surface-500'
            )}>
              {pos.position_style_label}
            </span>
          )}
          {pos.avg_down_count > 0 && (
            <span className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded flex items-center gap-0.5">
              <TrendingDown size={10} /> 물타기 {pos.avg_down_count}회
            </span>
          )}
          {pos.add_count > 0 && (
            <span className="text-xs bg-up/20 text-up px-1.5 py-0.5 rounded flex items-center gap-0.5">
              <TrendingUp size={10} /> 추매 {pos.add_count}회
            </span>
          )}
        </div>
        <span className={clsx('text-sm font-bold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
          {pnlPos ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
        </span>
      </div>

      {/* 투입금액 → 현재가치 */}
      <div className="flex items-center gap-2 bg-surface-600/60 rounded-lg px-2.5 py-1.5 text-xs">
        <span className="text-slate-400">투입금액</span>
        <span className="font-mono font-semibold text-slate-100 tabular-nums">
          {investedKrw.toLocaleString('ko-KR')} ₩
        </span>
        <span className="text-slate-600 mx-0.5">→</span>
        <span className="text-slate-400">현재가치</span>
        <span className={clsx('font-mono font-semibold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
          {currentKrw.toLocaleString('ko-KR')} ₩
        </span>
        <span className={clsx('ml-auto font-semibold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
          {pnlPos ? '+' : ''}{pos.unrealized_pnl_krw?.toLocaleString('ko-KR')} ₩
        </span>
      </div>

      {/* 세부 정보 그리드 */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-slate-500">평균단가</p>
          <p className="text-amber-400 font-mono font-semibold">{pos.avg_price.toLocaleString('ko-KR')} ₩</p>
        </div>
        <div>
          <p className="text-slate-500">현재가</p>
          <p className="text-slate-200 font-mono">{pos.current_price.toLocaleString('ko-KR')} ₩</p>
        </div>
        <div>
          <p className="text-slate-500">보유 ({base})</p>
          <p className="text-slate-200 font-mono">{pos.total_amount.toFixed(6)}</p>
        </div>
        <div>
          <p className="text-slate-500">손절가</p>
          <p className="text-down font-mono">{pos.stop_loss_price.toLocaleString('ko-KR')} ₩</p>
        </div>
        <div>
          <p className="text-slate-500">익절가</p>
          <p className="text-up font-mono">{pos.take_profit_price.toLocaleString('ko-KR')} ₩</p>
        </div>
        <div>
          <p className="text-slate-500">진입 횟수</p>
          <p className="text-slate-200 font-mono">{pos.entries.length}회</p>
        </div>
      </div>

      {pos.signals.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {pos.signals.map(s => (
            <span key={s} className="text-xs bg-surface-600 text-slate-400 px-1.5 py-0.5 rounded">{s}</span>
          ))}
        </div>
      )}

      <p className="text-xs text-slate-600 text-right">클릭하여 상세 차트 보기 →</p>
    </div>
  )
}

// ─── 스캔 결과 / 거래 로그 행 ────────────────────────────────────────────────

function ScanRow({ r, rank }: { r: ScanResult; rank: number }) {
  const c = r.score >= 70 ? 'text-up' : r.score >= 50 ? 'text-amber-400' : 'text-slate-400'
  const stratColor = STRATEGY_COLORS[r.strategy_type] ?? STRATEGY_COLORS.standard
  return (
    <div className="py-2 border-b border-surface-700 last:border-0 space-y-1">
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-500 w-4">{rank}</span>
        <span className="text-sm font-medium text-slate-200 w-24">{r.symbol}</span>
        <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium', stratColor)}>
          {r.strategy_label}
        </span>
        {r.sl_pct && (
          <span className="text-xs text-slate-500">
            SL <span className="text-down">{r.sl_pct}%</span>
            {' '}/ TP <span className="text-up">{r.tp_pct}%</span>
          </span>
        )}
        <span className="text-xs text-slate-500 ml-auto">RSI {r.rsi}</span>
        <span className={clsx('text-sm font-bold w-10 text-right', c)}>{r.score}</span>
      </div>
      <div className="flex flex-wrap gap-1 pl-8">
        {r.signals.map(s => (
          <span key={s} className="text-xs bg-surface-600 text-slate-400 px-1 py-0.5 rounded">{s}</span>
        ))}
      </div>
    </div>
  )
}

const REASON_LABEL: Record<string, string> = {
  stop_loss: '손절', take_profit: '익절', manual: '수동청산',
  trailing_stop: '트레일링', ai_exit: 'AI청산',
}

const REASON_COLOR: Record<string, string> = {
  stop_loss:     'bg-down/20 text-down',
  take_profit:   'bg-up/20 text-up',
  trailing_stop: 'bg-brand-500/20 text-brand-400',
  ai_exit:       'bg-purple-500/20 text-purple-400',
  manual:        'bg-surface-600 text-slate-400',
}

function calcDuration(entryAt: string, exitAt: string): string {
  try {
    const secs = Math.floor((new Date(exitAt).getTime() - new Date(entryAt).getTime()) / 1000)
    if (secs <= 0) return ''
    if (secs < 60) return `${secs}초`
    if (secs < 3600) return `${Math.floor(secs / 60)}분 ${secs % 60}초`
    if (secs < 86400) {
      const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60)
      return m > 0 ? `${h}시간 ${m}분` : `${h}시간`
    }
    const d = Math.floor(secs / 86400), h = Math.floor((secs % 86400) / 3600)
    return h > 0 ? `${d}일 ${h}시간` : `${d}일`
  } catch { return '' }
}

function fmtKst(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      month: 'numeric', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
      hour12: false,
    })
  } catch { return iso.slice(0, 16).replace('T', ' ') }
}

function LogRow({ t }: { t: AutoBotTradeLog | AutoBotTradeDB }) {
  const pos = t.pnl_pct >= 0
  const reasonLabel = REASON_LABEL[t.exit_reason] ?? t.exit_reason
  const reasonColor = REASON_COLOR[t.exit_reason] ?? 'bg-surface-600 text-slate-400'
  const stratColor  = STRATEGY_COLORS[('strategy_type' in t ? t.strategy_type : undefined) ?? 'standard'] ?? STRATEGY_COLORS.standard
  const investKrw   = Math.round(t.avg_price * t.total_amount)
  const exitKrw     = Math.round(t.exit_price * t.total_amount)
  const duration    = calcDuration(t.entry_at, t.exit_at)
  const base        = t.symbol.split('/')[0]

  return (
    <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-2">
      {/* ── 1행: 심볼 + 배지 + 손익 ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-bold text-slate-100">{t.symbol}</span>
        {'strategy_label' in t && t.strategy_label && (
          <span className={clsx('px-1.5 py-0.5 rounded font-medium', stratColor)}>
            {t.strategy_label}
          </span>
        )}
        <span className={clsx('px-1.5 py-0.5 rounded font-medium', reasonColor)}>
          {reasonLabel}
        </span>
        <span className={clsx(
          'ml-auto text-sm font-bold tabular-nums',
          pos ? 'text-up' : 'text-down'
        )}>
          {pos ? '+' : ''}{t.pnl_pct.toFixed(2)}%
        </span>
        <span className={clsx('font-mono font-semibold tabular-nums text-sm', pos ? 'text-up' : 'text-down')}>
          {pos ? '+' : ''}{t.pnl_krw.toLocaleString('ko-KR')} ₩
        </span>
      </div>

      {/* ── 2행: 가격 / 금액 ── */}
      <div className="flex items-center gap-1.5 bg-surface-700/60 rounded px-2.5 py-1.5 font-mono flex-wrap">
        <span className="text-slate-500">매수</span>
        <span className="text-amber-400 font-semibold">{t.avg_price.toLocaleString('ko-KR')} ₩</span>
        <span className="text-slate-600 mx-0.5">×</span>
        <span className="text-slate-300">{t.total_amount.toFixed(6)} {base}</span>
        <span className="text-slate-600 mx-1">=</span>
        <span className="text-slate-200">{investKrw.toLocaleString('ko-KR')} ₩</span>
        <span className="text-slate-600 mx-1">→</span>
        <span className="text-slate-500">매도</span>
        <span className={clsx('font-semibold', pos ? 'text-up' : 'text-down')}>
          {t.exit_price.toLocaleString('ko-KR')} ₩
        </span>
        <span className="text-slate-600 mx-0.5">=</span>
        <span className={clsx(pos ? 'text-up/80' : 'text-down/80')}>
          {exitKrw.toLocaleString('ko-KR')} ₩
        </span>
      </div>

      {/* ── 3행: 진입 시각 / 청산 시각 / 보유 기간 ── */}
      <div className="flex items-center gap-2 text-slate-500 flex-wrap">
        <Clock size={10} className="flex-shrink-0" />
        <span>진입 <span className="text-slate-300">{fmtKst(t.entry_at)}</span></span>
        <span className="text-slate-600">→</span>
        <span>청산 <span className="text-slate-300">{fmtKst(t.exit_at)}</span></span>
        {duration && (
          <span className="text-slate-600 ml-1">· 보유 <span className="text-slate-400">{duration}</span></span>
        )}
        {(t.avg_down_count > 0 || t.add_count > 0) && (
          <span className="ml-auto flex gap-2">
            {t.avg_down_count > 0 && (
              <span className="text-amber-500/70">물타기 {t.avg_down_count}회</span>
            )}
            {t.add_count > 0 && (
              <span className="text-up/70">추매 {t.add_count}회</span>
            )}
          </span>
        )}
      </div>
    </div>
  )
}

// ─── 메인 패널 ───────────────────────────────────────────────────────────────

export default function AutoTradePanel() {
  const qc = useQueryClient()
  const [showSettings, setShowSettings] = useState(false)
  const [selectedPos, setSelectedPos] = useState<AutoBotPosition | null>(null)
  const [tab, setTab] = useState<'positions' | 'scan' | 'log' | 'ai'>('positions')

  const { data: status, isLoading } = useQuery<AutoBotStatus>({
    queryKey: ['auto-bot-status'],
    queryFn: async () => (await api.get('/auto-bot/status')).data,
    refetchInterval: 3_000,
  })

  const { data: dbTrades } = useQuery<AutoBotTradeDB[]>({
    queryKey: ['auto-bot-trades'],
    queryFn: async () => (await api.get('/auto-bot/trades')).data,
    refetchInterval: tab === 'log' ? 5_000 : 30_000,
  })

  const { data: tradeStats } = useQuery<AutoBotTradeStats>({
    queryKey: ['auto-bot-trade-stats'],
    queryFn: async () => (await api.get('/auto-bot/trades/stats')).data,
    refetchInterval: 10_000,
  })

  const { data: aiConfig } = useQuery<{
    provider: string
    model: string
    providers: Record<string, { tier: 'free' | 'paid'; label: string }>
  }>({
    queryKey: ['ai-config'],
    queryFn: async () => (await api.get('/ai-config')).data,
    refetchInterval: false,
  })

  const uptime = useUptime(status?.started_at ?? null)

  const startMut = useMutation({
    mutationFn: () => api.post('/auto-bot/start'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const stopMut = useMutation({
    mutationFn: () => api.post('/auto-bot/stop'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const scanMut = useMutation({
    mutationFn: () => api.post('/auto-bot/scan'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const settingsMut = useMutation({
    mutationFn: (s: object) => api.patch('/auto-bot/settings', s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })

  if (isLoading || !status) {
    return <div className="card"><p className="text-slate-500 text-sm">로딩 중...</p></div>
  }

  // 선택된 포지션이 업데이트됐으면 동기화
  const livePos = selectedPos
    ? status.positions.find(p => p.symbol === selectedPos.symbol) ?? null
    : null

  return (
    <>
      {showSettings && (
        <SettingsModal
          settings={status.settings}
          onSave={s => settingsMut.mutate(s)}
          onClose={() => setShowSettings(false)}
        />
      )}

      {livePos && (
        <PositionDetailModal
          pos={livePos}
          maxAvgDown={status.settings.max_avg_down}
          maxAdd={status.settings.max_add}
          onClose={() => setSelectedPos(null)}
        />
      )}

      <div className="card space-y-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Bot size={18} className={status.running ? 'text-brand-400' : 'text-slate-500'} />
            <h2 className="font-semibold text-slate-100">자동매매봇</h2>
            {/* 매매 스타일 배지 */}
            {(() => {
              const sk = status.settings.trading_style ?? 'short'
              const meta = STYLE_META[sk] ?? STYLE_META.short
              return (
                <span className={clsx('text-xs px-2 py-0.5 rounded font-medium', meta.badge)}>
                  {STYLE_LABEL[sk] ?? status.style_label}
                </span>
              )
            })()}
            <span className={clsx(
              'flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium',
              status.running ? 'bg-up/20 text-up' : 'bg-surface-700 text-slate-400'
            )}>
              {status.running && <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />}
              {status.running ? '실행 중' : '중지됨'}
            </span>
            {status.running && uptime && (
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <Clock size={11} /> {uptime}
              </span>
            )}
            {status.scan_in_progress && (
              <span className="text-xs text-amber-400 flex items-center gap-1">
                <RefreshCw size={11} className="animate-spin" /> 스캔 중...
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowSettings(true)} className="p-1.5 text-slate-400 hover:text-slate-200">
              <Settings2 size={16} />
            </button>
            <button
              onClick={() => scanMut.mutate()}
              disabled={status.scan_in_progress}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 bg-surface-700 hover:bg-surface-600 border border-surface-600 rounded-lg text-slate-300 transition-colors disabled:opacity-50"
            >
              <Zap size={12} /> 시장 스캔
            </button>
            {status.running ? (
              <button
                onClick={() => stopMut.mutate()}
                disabled={stopMut.isPending}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-down/20 border border-down/40 text-down rounded-lg hover:bg-down/30 transition-colors"
              >
                <Square size={13} /> 중지
              </button>
            ) : (
              <button
                onClick={() => startMut.mutate()}
                disabled={startMut.isPending}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-up/20 border border-up/40 text-up rounded-lg hover:bg-up/30 transition-colors"
              >
                <Play size={13} /> 시작
              </button>
            )}
          </div>
        </div>

        {/* 통계 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <StatCard label="모의 잔고" value={`${status.balance_krw.toLocaleString('ko-KR')} ₩`} />
          <StatCard label="총 평가" value={`${status.total_value_krw.toLocaleString('ko-KR')} ₩`} />
          <StatCard
            label="실현 손익 (누적)"
            value={(() => {
              const pnl = tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.total_trades > 0 ? status.realized_pnl_krw : null
              return pnl !== null ? `${pnl >= 0 ? '+' : ''}${pnl.toLocaleString('ko-KR')} ₩` : '—'
            })()}
            color={(() => {
              const pnl = tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.total_trades > 0 ? status.realized_pnl_krw : null
              return pnl !== null && pnl > 0 ? 'up' : pnl !== null && pnl < 0 ? 'down' : undefined
            })()}
          />
          <StatCard
            label={`총 거래 ${tradeStats ? `(승률 ${tradeStats.win_rate}%)` : ''}`}
            value={`${tradeStats?.total ?? status.total_trades}건`}
          />
        </div>

        {/* 종합 미실현 손익 (포지션 있을 때만) */}
        {status.positions.length > 0 && (
          <div className={clsx(
            'rounded-lg px-4 py-3 border flex items-center justify-between flex-wrap gap-3',
            status.unrealized_pnl_krw >= 0
              ? 'bg-up/5 border-up/20'
              : 'bg-down/5 border-down/20'
          )}>
            <div>
              <p className="text-xs text-slate-500 mb-0.5">종합 미실현 손익 ({status.positions.length}개 포지션)</p>
              <div className="flex items-baseline gap-2">
                <span className={clsx(
                  'text-xl font-bold tabular-nums',
                  status.unrealized_pnl_krw >= 0 ? 'text-up' : 'text-down'
                )}>
                  {status.unrealized_pnl_krw >= 0 ? '+' : ''}
                  {status.unrealized_pnl_krw.toLocaleString('ko-KR')} ₩
                </span>
                <span className={clsx(
                  'text-sm font-semibold',
                  status.unrealized_pnl_pct >= 0 ? 'text-up' : 'text-down'
                )}>
                  ({status.unrealized_pnl_pct >= 0 ? '+' : ''}{status.unrealized_pnl_pct.toFixed(2)}%)
                </span>
              </div>
            </div>
            <div className="text-xs text-slate-500 text-right space-y-0.5">
              {status.positions.map(p => (
                <div key={p.symbol} className="flex items-center gap-2">
                  <span className="text-slate-400 w-20 text-left">{p.symbol.split('/')[0]}</span>
                  <span className={clsx('tabular-nums', p.unrealized_pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                    {p.unrealized_pnl_pct >= 0 ? '+' : ''}{p.unrealized_pnl_pct.toFixed(2)}%
                  </span>
                  <span className={clsx('tabular-nums w-28 text-right', p.unrealized_pnl_krw >= 0 ? 'text-up/70' : 'text-down/70')}>
                    {p.unrealized_pnl_krw >= 0 ? '+' : ''}{p.unrealized_pnl_krw.toLocaleString('ko-KR')} ₩
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 설정 요약 */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 bg-surface-700 rounded-lg px-3 py-2">
          <span>타임프레임 <b className="text-slate-200">{status.settings.timeframe}</b></span>
          <span>스캔 <b className="text-slate-200">{status.settings.scan_interval_min}분</b></span>
          <span>포지션당 <b className="text-slate-200">{status.settings.position_size_pct}%</b></span>
          <span>손절 <b className="text-down">{status.settings.stop_loss_pct}%</b></span>
          <span>익절 <b className="text-up">{status.settings.take_profit_pct}%</b></span>
          <span>최대 <b className="text-slate-200">{status.settings.max_positions}개</b></span>
          <span>물타기 <b className={status.settings.auto_avg_down ? 'text-amber-400' : 'text-slate-500'}>{status.settings.auto_avg_down ? `ON (${status.settings.avg_down_threshold_pct}%)` : 'OFF'}</b></span>
          <span>추매 <b className={status.settings.auto_add ? 'text-up' : 'text-slate-500'}>{status.settings.auto_add ? `ON (${status.settings.add_threshold_pct}%)` : 'OFF'}</b></span>
          {status.last_scan_at && <span className="ml-auto text-slate-500">마지막 스캔: {status.last_scan_at}</span>}
        </div>

        {/* 탭 */}
        <div className="flex gap-1 border-b border-surface-700">
          {([
            ['positions', `포지션 (${status.positions.length})`],
            ['scan', `스캔 결과 (${status.scan_results.length})`],
            ['log', `거래 내역 (${tradeStats?.total ?? status.total_trades})`],
            ['ai', `AI 활동 (${status.ai_analysis_log?.length ?? 0})`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={clsx(
                'px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
                tab === key ? 'border-brand-500 text-brand-400' : 'border-transparent text-slate-400 hover:text-slate-200'
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* 탭 컨텐츠 */}
        {tab === 'positions' && (
          status.positions.length === 0 ? (
            <p className="text-sm text-slate-500 py-2">
              {status.running
                ? '진입 조건을 탐색 중... 스캔 후 조건 충족 종목에 자동 진입합니다.'
                : '봇을 시작하면 시장을 분석하여 자동으로 종목을 선택하고 매매합니다.'}
            </p>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
              {status.positions.map(p => (
                <PositionCard
                  key={p.symbol}
                  pos={p}
                  onClick={() => setSelectedPos(p)}
                />
              ))}
            </div>
          )
        )}

        {tab === 'scan' && (
          status.scan_results.length === 0 ? (
            <p className="text-sm text-slate-500 py-2">"시장 스캔" 버튼을 눌러 전체 종목을 분석하세요.</p>
          ) : (
            <div>
              <p className="text-xs text-slate-500 mb-2">
                RSI(30) + EMA(20) + MACD(30) + 거래량(20) = 최대 100점 · 전략 자동 분류 적용
              </p>
              {status.scan_results.map((r, i) => <ScanRow key={r.symbol} r={r} rank={i + 1} />)}
            </div>
          )
        )}

        {tab === 'ai' && (
          <AiActivityLog
            log={status.ai_analysis_log ?? []}
            available={status.ai_available}
            regime={status.ai_regime}
            consecutiveLosses={status.ai_consecutive_losses}
            providerLabel={aiConfig ? `${aiConfig.providers?.[aiConfig.provider]?.label ?? aiConfig.provider} / ${aiConfig.model}` : undefined}
            providerTier={aiConfig ? (aiConfig.providers?.[aiConfig.provider]?.tier ?? 'free') : undefined}
          />
        )}

        {tab === 'log' && (
          <>
            {/* 실현 손익 요약 */}
            {((tradeStats && tradeStats.total > 0) || status.total_trades > 0) && (
              <div className={clsx(
                'rounded-lg px-4 py-3 border flex flex-wrap gap-4 text-xs mb-2',
                (tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.realized_pnl_krw) >= 0
                  ? 'bg-up/5 border-up/20' : 'bg-down/5 border-down/20'
              )}>
                <div>
                  <p className="text-slate-500 mb-0.5">누적 실현 손익{!(tradeStats && tradeStats.total > 0) && ' (세션)'}</p>
                  <p className={clsx('text-base font-bold tabular-nums',
                    (tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.realized_pnl_krw) >= 0 ? 'text-up' : 'text-down'
                  )}>
                    {(tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.realized_pnl_krw) >= 0 ? '+' : ''}
                    {(tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.realized_pnl_krw).toLocaleString('ko-KR')} ₩
                  </p>
                </div>
                <div><p className="text-slate-500 mb-0.5">총 거래</p><p className="text-slate-200 font-semibold">{tradeStats?.total ?? status.total_trades}건</p></div>
                {tradeStats && tradeStats.total > 0 && <>
                  <div><p className="text-slate-500 mb-0.5">승률</p><p className="text-slate-200 font-semibold">{tradeStats.win_rate}%</p></div>
                  <div><p className="text-slate-500 mb-0.5">평균 손익</p>
                    <p className={clsx('font-semibold', tradeStats.avg_pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                      {tradeStats.avg_pnl_pct >= 0 ? '+' : ''}{tradeStats.avg_pnl_pct.toFixed(2)}%
                    </p>
                  </div>
                  <div><p className="text-slate-500 mb-0.5">최고</p><p className="text-up font-semibold">+{tradeStats.best_trade_pct.toFixed(2)}%</p></div>
                  <div><p className="text-slate-500 mb-0.5">최저</p><p className="text-down font-semibold">{tradeStats.worst_trade_pct.toFixed(2)}%</p></div>
                </>}
              </div>
            )}
            {(() => {
              const trades = dbTrades && dbTrades.length > 0
                ? dbTrades
                : status.trade_log
              const isMemOnly = (!dbTrades || dbTrades.length === 0) && status.trade_log.length > 0
              return trades.length === 0 ? (
                <p className="text-sm text-slate-500 py-2">완료된 거래가 없습니다.</p>
              ) : (
                <div>
                  {isMemOnly && (
                    <p className="text-xs text-amber-400/70 mb-2 flex items-center gap-1">
                      <ShieldAlert size={11} /> DB 저장 오류 — 현재 세션 거래 내역입니다 (서버 재시작 시 초기화됨)
                    </p>
                  )}
                  {(trades as (AutoBotTradeDB | AutoBotTradeLog)[]).map((t, i) => (
                    <LogRow key={'id' in t ? t.id : i} t={t} />
                  ))}
                </div>
              )
            })()}
          </>
        )}
      </div>
    </>
  )
}

// ─── AI 활동 로그 ─────────────────────────────────────────────────────────────

const REGIME_KO: Record<string, string> = {
  trending: '추세장', ranging: '횡보장', volatile: '급등락장',
}
const STYLE_KO: Record<string, string> = {
  scalping: '초단기', short: '단기', mid: '중장기', long: '장기',
}
const ISSUE_KO: Record<string, string> = {
  SL_TOO_TIGHT: '손절선이 너무 좁음',
  WRONG_STRATEGY: '전략 불일치',
  BAD_TIMING: '진입 타이밍 불량',
}

function AiLogEntry({ entry }: { entry: AiAnalysisLogEntry }) {
  const { type } = entry

  if (type === 'regime_change') {
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <BarChart2 size={14} className="text-brand-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">시장 국면 감지</span>
              <span className="px-1.5 py-0.5 rounded bg-brand-500/20 text-brand-300 font-medium">
                {REGIME_KO[entry.regime ?? ''] ?? entry.regime}
              </span>
              {entry.changed && entry.changed.length > 0 && entry.changed.map((c, i) => (
                <span key={i} className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">{c}</span>
              ))}
            </div>
            <p className="text-slate-400 mt-1">{entry.reason}</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  if (type === 'loss_analysis') {
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <ShieldAlert size={14} className="text-down mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">연속 손절 분석</span>
              <span className="px-1.5 py-0.5 rounded bg-down/20 text-down font-medium">
                {ISSUE_KO[entry.issue ?? ''] ?? entry.issue}
              </span>
              {entry.adjusted && entry.adjusted.length > 0 && entry.adjusted.map((a, i) => (
                <span key={i} className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">{a} 으로 조정됨</span>
              ))}
            </div>
            <p className="text-slate-400 mt-1">{entry.reason}</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  if (type === 'entry_blocked') {
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <Sparkles size={14} className="text-amber-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">진입 차단</span>
              <span className="text-slate-300 font-mono">{entry.symbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">
                신뢰도 {entry.confidence}%
              </span>
            </div>
            <p className="text-slate-400 mt-1">{entry.reason}</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  if (type === 'exit_action') {
    const isClose = entry.action === 'close_now'
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <LogOut size={14} className={clsx('mt-0.5 flex-shrink-0', isClose ? 'text-up' : 'text-amber-400')} />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">
                {isClose ? '조기 청산 권고' : 'SL 상향 권고'}
              </span>
              <span className="text-slate-300 font-mono">{entry.symbol}</span>
              <span className={clsx(
                'px-1.5 py-0.5 rounded font-medium',
                isClose ? 'bg-up/20 text-up' : 'bg-amber-500/20 text-amber-300'
              )}>
                {entry.pnl_pct !== undefined ? `+${entry.pnl_pct.toFixed(2)}%` : ''}
              </span>
            </div>
            <p className="text-slate-400 mt-1">{entry.reason}</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  return null
}

function AiActivityLog({
  log, available, regime, consecutiveLosses, providerLabel, providerTier,
}: {
  log: AiAnalysisLogEntry[]
  available: boolean
  regime?: AutoBotStatus['ai_regime']
  consecutiveLosses: number
  providerLabel?: string
  providerTier?: 'free' | 'paid'
}) {
  return (
    <div className="space-y-3">
      {/* 현재 상태 요약 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-surface-700 rounded-lg px-3 py-2 text-xs">
          <p className="text-slate-500 mb-0.5">AI 연결</p>
          <p className={clsx('font-semibold', available ? 'text-up' : 'text-slate-500')}>
            {available ? '연결됨' : '미연결'}
          </p>
        </div>
        <div className="bg-surface-700 rounded-lg px-3 py-2 text-xs">
          <p className="text-slate-500 mb-0.5">현재 시장</p>
          <p className="text-slate-200 font-semibold">
            {regime ? (REGIME_KO[regime.regime] ?? regime.regime) : '—'}
          </p>
        </div>
        <div className="bg-surface-700 rounded-lg px-3 py-2 text-xs">
          <p className="text-slate-500 mb-0.5">연속 손절</p>
          <p className={clsx('font-semibold', consecutiveLosses >= 2 ? 'text-down' : 'text-slate-200')}>
            {consecutiveLosses}회
          </p>
        </div>
      </div>

      {/* 국면 감지 이유 */}
      {regime?.reason && (
        <div className="bg-surface-700 rounded-lg px-3 py-2 text-xs">
          <div className="flex items-center gap-1.5 mb-1">
            <Brain size={12} className="text-brand-400" />
            <span className="text-slate-400 font-medium">AI 판단 근거</span>
          </div>
          <p className="text-slate-300">{regime.reason}</p>
          <div className="flex gap-3 mt-1.5 text-slate-500">
            <span>추천 스타일: <b className="text-slate-300">{STYLE_KO[regime.style] ?? regime.style}</b></span>
            {regime.min_score_delta !== 0 && (
              <span>최소점수 조정: <b className={regime.min_score_delta > 0 ? 'text-up' : 'text-down'}>
                {regime.min_score_delta > 0 ? '+' : ''}{regime.min_score_delta}
              </b></span>
            )}
          </div>
        </div>
      )}

      {/* AI 호출 빈도 안내 */}
      <div className="bg-surface-700/60 border border-surface-600 rounded-lg px-3 py-2.5 text-xs text-slate-400 space-y-1">
        <p className="text-slate-300 font-medium flex items-center gap-1.5">
          <Brain size={12} className="text-brand-400" /> AI 호출 빈도 안내
        </p>
        <p>· <b className="text-slate-300">시장 국면 감지</b> — 최소 15분에 1회 (캐시 적용)</p>
        <p>· <b className="text-slate-300">진입 확인</b> — 같은 종목·조건은 10분 캐시</p>
        <p>· <b className="text-slate-300">청산 보조</b> — 포지션당 5분 캐시</p>
        <p>· <b className="text-slate-300">손절 분석</b> — 연속 손절 3회 발생 시에만</p>
        {providerLabel ? (
          <p className="text-slate-500 pt-0.5">
            현재 사용 중: <b className="text-slate-400">{providerLabel}</b>
            {providerTier === 'paid'
              ? <> — <span className="text-amber-400">유료 과금</span> 방식입니다. 하루 AI 호출은 수백 회 수준으로 비용은 소량입니다.</>
              : ' — 무료 한도 내에서 충분히 운영 가능합니다.'}
          </p>
        ) : (
          <p className="text-slate-500 pt-0.5">AI 미설정 상태입니다. 설정 메뉴에서 프로바이더를 선택하세요.</p>
        )}
      </div>

      {/* 로그 목록 */}
      {log.length === 0 ? (
        <p className="text-sm text-slate-500 py-2">아직 AI 활동 기록이 없습니다.</p>
      ) : (
        <div>
          {log.map((entry, i) => <AiLogEntry key={i} entry={entry} />)}
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: string; color?: 'up' | 'down' }) {
  return (
    <div className="bg-surface-700 rounded-lg p-2.5">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={clsx(
        'text-sm font-semibold mt-0.5 tabular-nums',
        color === 'up' ? 'text-up' : color === 'down' ? 'text-down' : 'text-slate-100'
      )}>{value}</p>
    </div>
  )
}
