import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot, Play, Square, Pause, RefreshCw, Zap, Settings2,
  TrendingDown, TrendingUp, Clock, Brain,
  ShieldAlert, Sparkles, LogOut, BarChart2,
  AlertCircle, CheckCircle, X,
} from 'lucide-react'
import api from '../../utils/api'
import Tooltip from '../common/Tooltip'
import ConfirmModal from '../common/ConfirmModal'
import type {
  AutoBotStatus, AutoBotSettings, AutoBotPosition, AutoBotTradeLog, ScanResult,
  StylePreset, AutoBotTradeDB, AutoBotTradeStats, AiAnalysisLogEntry, PerformanceStats,
  FuturesPosition, ExchangeAccount,
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

// ─── 거래소 메타 ─────────────────────────────────────────────────────────────

const EXCHANGE_LABEL: Record<string, string> = {
  upbit: 'Upbit', binance: 'Binance', bybit: 'Bybit',
}
const EXCHANGE_COLOR: Record<string, string> = {
  upbit: 'text-blue-400', binance: 'text-yellow-400', bybit: 'text-orange-400',
}

function fmtCurrency(amount: number, exchangeIdOrCurrency?: string): string {
  const isKrw = !exchangeIdOrCurrency || exchangeIdOrCurrency === 'upbit' || exchangeIdOrCurrency === 'KRW'
  if (isKrw) {
    return amount.toLocaleString('ko-KR') + ' ₩'
  }
  return '$' + amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 스타일 메타 (프론트 표시용) ─────────────────────────────────────────────

const STYLE_META: Record<string, {
  color: string
  border: string
  badge: string
  desc: string
  volDesc: string
  volDescUsdt: string
}> = {
  scalping: {
    color: 'text-purple-400',
    border: 'border-purple-500/50',
    badge: 'bg-purple-500/20 text-purple-400',
    desc: '수 분 내 빠른 진입·청산. 변동성 낮고 유동성 최상위 종목만.',
    volDesc: '일 거래대금 50억+ (상위 10~15종목)',
    volDescUsdt: '24h 거래량 $5M+ (상위 10~15종목)',
  },
  short: {
    color: 'text-brand-400',
    border: 'border-brand-500/50',
    badge: 'bg-brand-500/20 text-brand-400',
    desc: '수 시간~1일 내 수익 실현. 유동성 높은 주요 알트 포함.',
    volDesc: '일 거래대금 20억+ (상위 15~20종목)',
    volDescUsdt: '24h 거래량 $2M+ (상위 15~20종목)',
  },
  mid: {
    color: 'text-amber-400',
    border: 'border-amber-500/50',
    badge: 'bg-amber-500/20 text-amber-400',
    desc: '수 일~수 주 추세 추종. 넓은 TP로 큰 움직임 포착.',
    volDesc: '일 거래대금 5억+ (상위 20~25종목)',
    volDescUsdt: '24h 거래량 $500k+ (상위 20~25종목)',
  },
  long: {
    color: 'text-up',
    border: 'border-up/50',
    badge: 'bg-up/20 text-up',
    desc: '수 주~수 개월 장기 보유. 깊은 손절, 큰 익절 목표.',
    volDesc: '일 거래대금 1억+ (전체 스캔)',
    volDescUsdt: '24h 거래량 $100k+ (전체 스캔)',
  },
}

const STYLE_ORDER = ['scalping', 'short', 'mid', 'long'] as const
const STYLE_LABEL: Record<string, string> = {
  scalping: '초단타', short: '단타', mid: '중장기', long: '장기',
}

// ─── 투자 성향 메타 ───────────────────────────────────────────────────────────

interface RiskProfileAdjustment {
  key: string
  label: string
  position_size_pct_mult?: number
  min_score_delta?: number
  max_positions_delta?: number
  stop_loss_pct_mult?: number
  take_profit_pct_mult?: number
  auto_avg_down?: boolean
  auto_add?: boolean
}

const RISK_PROFILE_ORDER = ['conservative', 'balanced', 'aggressive'] as const
const RISK_PROFILE_META: Record<string, { label: string; badge: string; border: string; desc: string }> = {
  conservative: {
    label: '보수적',
    badge: 'bg-blue-500/20 text-blue-400',
    border: 'border-blue-500/50',
    desc: '포지션 60% 크기, 진입 기준 강화, 빠른 손절. 자산 보존 우선.',
  },
  balanced: {
    label: '균형',
    badge: 'bg-brand-500/20 text-brand-400',
    border: 'border-brand-500/50',
    desc: '스타일 프리셋 기본값 그대로 사용.',
  },
  aggressive: {
    label: '공격적',
    badge: 'bg-orange-500/20 text-orange-400',
    border: 'border-orange-500/50',
    desc: '포지션 150% 크기, 진입 기준 완화, 넓은 손절/익절. 수익 극대화 목표.',
  },
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

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  const set = (key: string, val: number | boolean | string) =>
    setForm(f => ({ ...f, [key]: val }))

  const { data: accounts = [] } = useQuery<ExchangeAccount[]>({
    queryKey: ['exchange-accounts'],
    queryFn: async () => (await api.get('/exchange-accounts/')).data,
    staleTime: 30_000,
  })
  const isPaperMode = form.is_paper ?? true
  const connectedExchanges = new Set(
    accounts.filter(a => a.is_paper === isPaperMode && a.is_active).map(a => a.exchange)
  )

  // 스타일 프리셋 조회
  const { data: presets } = useQuery<Record<string, StylePreset>>({
    queryKey: ['style-presets'],
    queryFn: async () => (await api.get('/auto-bot/style-presets')).data,
    staleTime: Infinity,
  })

  // 투자 성향 프로파일 조회
  const { data: riskProfiles } = useQuery<Record<string, RiskProfileAdjustment>>({
    queryKey: ['risk-profiles'],
    queryFn: async () => (await api.get('/auto-bot/risk-profiles')).data,
    staleTime: Infinity,
  })

  // 프리셋 기본값에 투자 성향 조정치를 적용
  const applyRiskAdj = (base: Partial<AutoBotSettings>, profile: string): Partial<AutoBotSettings> => {
    const adj = riskProfiles?.[profile]
    if (!adj) return base
    const r = { ...base }
    if (adj.position_size_pct_mult != null) r.position_size_pct = Math.round(base.position_size_pct! * adj.position_size_pct_mult * 10) / 10
    if (adj.min_score_delta != null) r.min_score = Math.min(90, Math.max(30, base.min_score! + adj.min_score_delta))
    if (adj.max_positions_delta != null) r.max_positions = Math.max(1, base.max_positions! + adj.max_positions_delta)
    if (adj.stop_loss_pct_mult != null) r.stop_loss_pct = Math.round(base.stop_loss_pct! * adj.stop_loss_pct_mult * 10) / 10
    if (adj.take_profit_pct_mult != null) r.take_profit_pct = Math.round(base.take_profit_pct! * adj.take_profit_pct_mult * 10) / 10
    if (adj.auto_avg_down != null) r.auto_avg_down = adj.auto_avg_down
    if (adj.auto_add != null) r.auto_add = adj.auto_add
    return r
  }

  const applyStyle = (styleKey: string) => {
    const preset = presets?.[styleKey]
    if (!preset) return
    const base: Partial<AutoBotSettings> = {
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
    }
    const adjusted = applyRiskAdj(base, form.risk_profile ?? 'balanced')
    // 사용자가 켜놓은 물타기/추매/피라미딩은 스타일 전환 시에도 유지
    if (form.auto_avg_down) adjusted.auto_avg_down = true
    if (form.auto_add) adjusted.auto_add = true
    if (form.pyramid_enabled) adjusted.pyramid_enabled = true
    setForm(f => ({ ...f, ...adjusted }))
  }

  const applyRiskProfile = (profile: string) => {
    const preset = presets?.[form.trading_style ?? 'short']
    if (!preset) { setForm(f => ({ ...f, risk_profile: profile })); return }
    const base: Partial<AutoBotSettings> = {
      stop_loss_pct: preset.stop_loss_pct,
      take_profit_pct: preset.take_profit_pct,
      min_score: preset.min_score,
      position_size_pct: preset.position_size_pct,
      max_positions: preset.max_positions,
      auto_avg_down: preset.auto_avg_down,
      auto_add: preset.auto_add,
    }
    const adjusted = applyRiskAdj(base, profile)
    // 사용자가 켜놓은 물타기/추매/피라미딩은 투자 성향 변경 시에도 유지
    if (form.auto_avg_down) adjusted.auto_avg_down = true
    if (form.auto_add) adjusted.auto_add = true
    if (form.pyramid_enabled) adjusted.pyramid_enabled = true
    setForm(f => ({ ...f, risk_profile: profile, ...adjusted }))
  }

  const currentStyle = form.trading_style ?? 'short'
  const currentMeta = STYLE_META[currentStyle] ?? STYLE_META.short
  const currentRiskProfile = form.risk_profile ?? 'balanced'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="bg-surface-800 border border-surface-700 rounded-xl shadow-2xl w-full max-w-md flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* ── 고정 타이틀 ── */}
        <div className="px-5 pt-5 pb-4 border-b border-surface-700 flex-shrink-0">
          <h3 className="font-semibold text-slate-100">자동매매 설정</h3>
        </div>

        {/* ── 전체 스크롤 영역 ── */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-5">

          {/* 거래소 */}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-2">거래소</p>
            <div className="grid grid-cols-3 gap-1.5">
              {(['upbit', 'binance', 'bybit'] as const).map(ex => {
                const connected = connectedExchanges.has(ex)
                return (
                  <button
                    key={ex}
                    disabled={!connected}
                    onClick={() => connected && setForm(f => ({
                      ...f,
                      exchange_id: ex,
                      ...(ex === 'upbit' ? { market_type: 'spot' } : {}),
                    }))}
                    className={clsx(
                      'py-2 rounded-lg text-xs font-medium border transition-colors',
                      !connected
                        ? 'bg-surface-800 border-surface-700 text-slate-600 cursor-not-allowed'
                        : (form.exchange_id ?? 'upbit') === ex
                          ? `bg-brand-500/20 border-brand-500 ${EXCHANGE_COLOR[ex]}`
                          : 'bg-surface-700 border-surface-600 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    <span className="flex items-center justify-center gap-1">
                      {EXCHANGE_LABEL[ex]}
                      {!connected && (
                        <Tooltip
                          text={`${EXCHANGE_LABEL[ex]} ${isPaperMode ? '모의투자' : '실거래'} 계정이 등록되지 않았습니다. 거래소 계정 메뉴에서 API 키를 등록하세요.`}
                          iconOnly
                        />
                      )}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 거래 모드 */}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-2">거래 모드</p>
            <div className="grid grid-cols-2 gap-1.5">
              {(['spot', 'futures'] as const).map(mt => {
                const isUpbit = (form.exchange_id ?? 'upbit') === 'upbit'
                const isFuturesDisabled = mt === 'futures' && isUpbit
                return (
                  <button
                    key={mt}
                    disabled={isFuturesDisabled}
                    onClick={() => !isFuturesDisabled && set('market_type', mt)}
                    className={clsx(
                      'py-2 rounded-lg text-xs font-medium border transition-colors',
                      isFuturesDisabled
                        ? 'bg-surface-800 border-surface-700 text-slate-600 cursor-not-allowed'
                        : (form.market_type ?? 'spot') === mt
                          ? 'bg-brand-500/20 border-brand-500 text-brand-400'
                          : 'bg-surface-700 border-surface-600 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    <Tooltip
                      text={isFuturesDisabled
                        ? '업비트는 현물 거래만 지원합니다. 선물 거래는 Binance 또는 Bybit을 선택하세요.'
                        : mt === 'spot'
                          ? '실제 암호화폐를 직접 매수·매도합니다. 레버리지 없이 보유 자산 한도 내에서 거래합니다.'
                          : '미래 가격을 현재 약정하는 파생상품 거래입니다. 레버리지로 증폭 거래가 가능하며 롱·숏 양방향 거래를 지원합니다.'}
                    >
                      {mt === 'spot' ? '현물 (Spot)' : '선물 (Futures)'}
                    </Tooltip>
                  </button>
                )
              })}
            </div>
            {(form.exchange_id ?? 'upbit') === 'upbit' && (
              <p className="text-xs text-slate-500 mt-1.5">업비트는 현물 거래만 지원합니다.</p>
            )}
            {(form.market_type ?? 'spot') === 'futures' && (
              <div className="mt-3 space-y-3">
                {/* 레버리지 */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs text-slate-400 flex items-center gap-1">
                      레버리지
                      <Tooltip text="내 자산의 N배 규모로 포지션을 열 수 있는 배율입니다. 5x이면 100달러로 500달러 규모 거래 가능. 수익과 손실이 모두 N배로 증폭되며 높을수록 청산 위험이 커집니다." iconOnly />
                    </p>
                    <span className="text-xs font-bold text-amber-400">{form.leverage ?? 5}x</span>
                  </div>
                  <input
                    type="range" min={1} max={20} step={1}
                    value={form.leverage ?? 5}
                    onChange={e => set('leverage', Number(e.target.value))}
                    className="w-full accent-amber-500"
                  />
                  <div className="flex justify-between text-xs text-slate-600 mt-0.5">
                    <span>1x</span><span>5x</span><span>10x</span><span>20x</span>
                  </div>
                </div>
                {/* 마진 모드 */}
                <div>
                  <p className="text-xs text-slate-400 mb-1.5 flex items-center gap-1">
                    마진 모드
                    <Tooltip text="청산 위험이 발생했을 때 손실을 어디서 충당하는지 결정합니다." iconOnly />
                  </p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {(['cross', 'isolated'] as const).map(mm => (
                      <button
                        key={mm}
                        onClick={() => set('margin_mode', mm)}
                        className={clsx(
                          'py-1.5 rounded text-xs font-medium border transition-colors',
                          (form.margin_mode ?? 'cross') === mm
                            ? 'bg-brand-500/20 border-brand-500 text-brand-400'
                            : 'bg-surface-700 border-surface-600 text-slate-400 hover:text-slate-200'
                        )}
                      >
                        <Tooltip
                          text={mm === 'cross'
                            ? '교차 마진: 계좌 전체 잔고가 증거금으로 사용됩니다. 청산 가격은 낮아지지만, 손실이 계좌 전체 자산으로 확산될 수 있습니다.'
                            : '격리 마진: 이 포지션에만 별도 증거금을 배정합니다. 청산 시 손실이 해당 증거금으로만 제한되어 계좌 전체를 보호할 수 있습니다.'}
                        >
                          {mm === 'cross' ? 'Cross (교차)' : 'Isolated (격리)'}
                        </Tooltip>
                      </button>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-1.5">
                  레버리지가 높을수록 청산 위험이 증가합니다. 모의거래로 먼저 테스트하세요.
                </p>
              </div>
            )}
          </div>

          {/* 매매 스타일 */}
          <div className="border-t border-surface-700 pt-4">
            <p className="text-xs text-slate-400 font-medium mb-2">매매 스타일</p>
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
            <div className={clsx('mt-2 rounded-lg border px-3 py-2 text-xs', currentMeta.border, 'bg-surface-700/50')}>
              <p className={clsx('font-medium', currentMeta.color)}>{currentMeta.desc}</p>
              <p className="text-slate-500 mt-0.5">거래량 기준: {(form.exchange_id ?? 'upbit') === 'upbit' ? currentMeta.volDesc : currentMeta.volDescUsdt}</p>
            </div>
            {/* 자동 전환 허용 스타일 */}
            <div className="mt-3">
              <p className="text-xs text-slate-500 mb-1.5 flex items-center gap-1">
                자동 전환 허용
                <Tooltip text="AI 시장 국면 감지가 매매 스타일을 자동 변경할 때 허용할 스타일만 선택하세요. 체크 해제된 스타일로는 자동 전환되지 않습니다." iconOnly />
              </p>
              <div className="flex gap-2 flex-wrap">
                {STYLE_ORDER.map(key => {
                  const meta = STYLE_META[key]
                  const allowed: string[] = form.allowed_styles ?? ['scalping', 'short', 'mid', 'long']
                  const checked = allowed.includes(key)
                  const toggle = () => {
                    const next = checked
                      ? allowed.filter(s => s !== key)
                      : [...allowed, key]
                    // 최소 1개는 허용
                    if (next.length === 0) return
                    setForm(f => ({ ...f, allowed_styles: next }))
                  }
                  return (
                    <label key={key} className="flex items-center gap-1 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={toggle}
                        className="accent-brand-500"
                      />
                      <span className={clsx('text-xs', checked ? meta.color : 'text-slate-500')}>
                        {STYLE_LABEL[key]}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          </div>

          {/* 투자 성향 */}
          <div className="border-t border-surface-700 pt-4">
            <p className="text-xs text-slate-400 font-medium mb-2 flex items-center gap-1">
              투자 성향
              <Tooltip text="같은 매매 스타일에서 포지션 크기·진입 기준·손절/익절 폭을 일괄 조정합니다. 보수적일수록 작게 걸고 빠르게 손절하며, 공격적일수록 크게 걸고 넓게 버팁니다." iconOnly />
            </p>
            <div className="grid grid-cols-3 gap-1.5">
              {RISK_PROFILE_ORDER.map(key => {
                const meta = RISK_PROFILE_META[key]
                return (
                  <button
                    key={key}
                    onClick={() => applyRiskProfile(key)}
                    className={clsx(
                      'py-2 rounded-lg text-xs font-semibold border transition-colors',
                      currentRiskProfile === key
                        ? `${meta.badge} ${meta.border}`
                        : 'bg-surface-700 border-surface-600 text-slate-400 hover:text-slate-200'
                    )}
                  >
                    {meta.label}
                  </button>
                )
              })}
            </div>
            <p className="text-xs text-slate-500 mt-1.5">{RISK_PROFILE_META[currentRiskProfile]?.desc}</p>
          </div>

          {/* 기본 설정 */}
          <div className="border-t border-surface-700 pt-4">
            <p className="text-xs text-slate-400 font-medium mb-2">기본 설정</p>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="최대 포지션" min={1} max={10}
                value={form.max_positions} onChange={v => set('max_positions', v)}
                tooltip="동시에 보유할 수 있는 종목 수의 상한입니다. 예: 5이면 최대 5개 종목에 포지션을 유지합니다." />
              <NumRow label="투입 (%)" min={1} max={100} step={1}
                value={form.position_size_pct} onChange={v => set('position_size_pct', v)}
                tooltip="종목 1개 매수 시 전체 자산 대비 투입할 비율입니다. 예: 10%이면 100만원 자산 중 10만원을 한 종목에 사용합니다." />
              <NumRow label="손절 (%)" min={0.5} max={20} step={0.5}
                value={form.stop_loss_pct} onChange={v => set('stop_loss_pct', v)}
                tooltip="손실이 이 비율에 도달하면 자동으로 매도하여 추가 손실을 막습니다. (Stop Loss)" />
              <NumRow label="익절 (%)" min={1} max={50} step={0.5}
                value={form.take_profit_pct} onChange={v => set('take_profit_pct', v)}
                tooltip="수익이 이 비율에 도달하면 자동으로 매도하여 수익을 확정합니다. (Take Profit)" />
              <NumRow label="최소 점수" min={30} max={90} step={5}
                value={form.min_score} onChange={v => set('min_score', v)}
                tooltip="AI가 매수 가능성을 0~100점으로 평가하며, 이 점수 이상인 종목만 진입합니다. 높을수록 조건이 엄격해져 진입 빈도가 낮아집니다." />
              <NumRow label="스캔 주기 (분)" min={1} max={1440}
                value={form.scan_interval_min} onChange={v => set('scan_interval_min', v)}
                tooltip="종목을 자동으로 분석하는 주기(분)입니다. 짧을수록 빠른 대응이 가능하지만 API 요청이 증가합니다." />
            </div>
          </div>

          {/* 포트폴리오 리스크 */}
          <div className="border-t border-surface-700 pt-4">
            <p className="text-xs text-slate-400 font-medium mb-2">포트폴리오 리스크</p>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="일일 최대 손실 (%)" min={1} max={30} step={0.5}
                value={form.max_daily_loss_pct ?? 5} onChange={v => set('max_daily_loss_pct', v)}
                tooltip="하루 동안 전체 자산 대비 이 비율 이상 손실이 발생하면 봇이 자동으로 신규 매수를 중단합니다." />
              <NumRow label="최대 투자 비중 (%)" min={10} max={100} step={5}
                value={form.max_portfolio_exposure_pct ?? 80} onChange={v => set('max_portfolio_exposure_pct', v)}
                tooltip="전체 자산 중 자동매매에 투입되는 최대 비율입니다. 나머지는 현금으로 유지하여 리스크를 분산합니다." />
            </div>
          </div>

          {/* 지표 타임프레임 */}
          <div className="border-t border-surface-700 pt-4">
            <p className="text-xs text-slate-400 font-medium mb-2 flex items-center gap-1">
              지표 타임프레임
              <Tooltip text="기술 지표(RSI, MACD, EMA 등)를 계산할 봉(캔들) 단위입니다. 1m=1분봉, 1h=1시간봉, 1d=일봉. 단타일수록 짧은 TF, 중장기일수록 긴 TF를 권장합니다." iconOnly />
            </p>
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
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-slate-400 font-medium flex items-center gap-1">
                물타기
                <Tooltip text="평균 단가를 낮추기 위해, 가격이 추가 하락했을 때 동일 종목을 추가 매수하는 전략입니다. (Averaging Down) 하락이 계속되면 손실이 커질 수 있으니 횟수를 제한하세요." iconOnly />
              </p>
              <Toggle checked={!!form.auto_avg_down} onChange={v => set('auto_avg_down', v)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="발동 하락 (%)" min={1} max={20} step={0.5}
                value={form.avg_down_threshold_pct} onChange={v => set('avg_down_threshold_pct', v)}
                tooltip="진입가 대비 이 비율만큼 하락하면 물타기가 자동으로 실행됩니다." />
              <NumRow label="최대 횟수" min={1} max={5}
                value={form.max_avg_down} onChange={v => set('max_avg_down', v)}
                tooltip="물타기를 실행할 수 있는 최대 횟수입니다. 초과 시 더 이상 추가 매수하지 않습니다." />
            </div>
          </div>

          {/* 추매 */}
          <div className="border-t border-surface-700 pt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-slate-400 font-medium flex items-center gap-1">
                추매
                <Tooltip text="상승 추세가 지속될 때 동일 종목을 추가 매수하여 수익을 극대화하는 전략입니다. (Adding to a Winner) 이미 오른 가격에 매수하므로 고점 리스크에 유의하세요." iconOnly />
              </p>
              <Toggle checked={!!form.auto_add} onChange={v => set('auto_add', v)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="발동 상승 (%)" min={1} max={20} step={0.5}
                value={form.add_threshold_pct} onChange={v => set('add_threshold_pct', v)}
                tooltip="진입가 대비 이 비율만큼 상승하면 추매가 자동으로 실행됩니다." />
              <NumRow label="최대 횟수" min={1} max={3}
                value={form.max_add} onChange={v => set('max_add', v)}
                tooltip="추매를 실행할 수 있는 최대 횟수입니다." />
            </div>
          </div>

          {/* 피라미딩 */}
          <div className="border-t border-surface-700 pt-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-slate-400 font-medium flex items-center gap-1">
                피라미딩
                <Tooltip text="포지션이 수익 구간(발동 수익률 이상)에 진입하고, 현재 시장 신호 점수가 최소 점수 이상일 때 초기 투자금의 50%를 추가 매수합니다. 수익 중인 포지션을 단계적으로 키워 수익을 극대화하는 전략입니다." iconOnly />
              </p>
              <Toggle checked={!!form.pyramid_enabled} onChange={v => set('pyramid_enabled', v)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <NumRow label="발동 수익 (%)" min={1} max={20} step={0.5}
                value={form.pyramid_threshold_pct ?? 3} onChange={v => set('pyramid_threshold_pct', v)}
                tooltip="미실현 수익이 이 비율 이상이고 최신 스코어가 최소 점수를 넘으면 피라미딩이 실행됩니다." />
              <NumRow label="최대 횟수" min={1} max={3}
                value={form.max_pyramid ?? 2} onChange={v => set('max_pyramid', v)}
                tooltip="피라미딩을 실행할 수 있는 최대 횟수입니다." />
            </div>
          </div>

        </div>

        {/* ── 고정 하단 버튼 ── */}
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
  label, value, onChange, min, max, step = 1, tooltip,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  tooltip?: string
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-500 flex items-center gap-1">
        {label}
        {tooltip && <Tooltip text={tooltip} iconOnly />}
      </span>
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

// ─── 실거래 전환 확인 모달 ───────────────────────────────────────────────────

type LiveModalStep =
  | { type: 'loading' }
  | { type: 'no_account' }
  | { type: 'no_balance'; accountLabel: string }
  | { type: 'confirm'; accountLabel: string; balance: number; currency: string }

function LiveSwitchModal({
  exchangeId,
  onConfirm,
  onClose,
}: {
  exchangeId: string
  onConfirm: () => void
  onClose: () => void
}) {
  const [step, setStep] = useState<LiveModalStep>({ type: 'loading' })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      // ① 거래소 계좌 목록 조회
      const accountsRes = await api.get('/exchange-accounts/').catch(() => null)
      if (cancelled) return
      if (!accountsRes) { setStep({ type: 'no_account' }); return }

      const accounts: { id: number; exchange: string; label: string; is_paper: boolean; is_active: boolean }[] =
        accountsRes.data ?? []
      const liveAccount = accounts.find(a => a.exchange === exchangeId && !a.is_paper && a.is_active)

      if (!liveAccount) { setStep({ type: 'no_account' }); return }

      // ② 잔고 조회
      const balanceRes = await api.get(`/exchange-accounts/${liveAccount.id}/balance`).catch(() => null)
      if (cancelled) return

      const currency = exchangeId === 'upbit' ? 'KRW' : 'USDT'
      const balances: { currency: string; free: number }[] = balanceRes?.data?.balances ?? []
      const bal = balances.find(b => b.currency === currency)?.free ?? 0

      if (bal <= 0) {
        setStep({ type: 'no_balance', accountLabel: liveAccount.label })
      } else {
        setStep({ type: 'confirm', accountLabel: liveAccount.label, balance: bal, currency })
      }
    })()
    return () => { cancelled = true }
  }, [exchangeId])

  const fmtBal = (amount: number, currency: string) =>
    currency === 'KRW'
      ? amount.toLocaleString('ko-KR') + ' ₩'
      : '$' + amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="bg-surface-800 border border-surface-700 rounded-xl shadow-2xl w-full max-w-sm"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-surface-700">
          <h3 className="font-semibold text-slate-100">실거래 전환</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-5 space-y-4">
          {step.type === 'loading' && (
            <div className="flex items-center gap-3 text-slate-400 text-sm">
              <RefreshCw size={16} className="animate-spin" />
              계좌 및 잔고를 확인하는 중...
            </div>
          )}

          {step.type === 'no_account' && (
            <>
              <div className="flex gap-3 bg-down/10 border border-down/30 rounded-lg px-4 py-3">
                <AlertCircle size={18} className="text-down flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-100 mb-1">실거래 계좌 없음</p>
                  <p className="text-xs text-slate-400">
                    선택한 거래소({exchangeId})에 등록된 실거래 계좌가 없습니다.
                    거래소 설정 페이지에서 실거래 계좌를 먼저 등록해주세요.
                  </p>
                </div>
              </div>
              <button onClick={onClose} className="btn-ghost w-full text-sm">닫기</button>
            </>
          )}

          {step.type === 'no_balance' && (
            <>
              <div className="flex gap-3 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
                <AlertCircle size={18} className="text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-100 mb-1">잔고 없음</p>
                  <p className="text-xs text-slate-400">
                    <span className="text-slate-200">{step.accountLabel}</span> 계좌의 거래 가능 잔고가 없습니다.
                    거래소 앱에서 입금 후 다시 시도해주세요.
                  </p>
                </div>
              </div>
              <button onClick={onClose} className="btn-ghost w-full text-sm">닫기</button>
            </>
          )}

          {step.type === 'confirm' && (
            <>
              <div className="flex gap-3 bg-up/10 border border-up/30 rounded-lg px-4 py-3">
                <CheckCircle size={18} className="text-up flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-100 mb-1">계좌 확인 완료</p>
                  <p className="text-xs text-slate-400">
                    계좌: <span className="text-slate-200">{step.accountLabel}</span><br />
                    거래 가능 잔고: <span className="text-up font-semibold font-mono">{fmtBal(step.balance, step.currency)}</span>
                  </p>
                </div>
              </div>
              <div className="bg-down/10 border border-down/30 rounded-lg px-4 py-3 text-xs text-down space-y-1">
                <p className="font-semibold">실거래 투자 시 유의사항</p>
                <ul className="text-down/80 space-y-0.5 list-disc list-inside">
                  <li>실제 자금으로 거래가 진행됩니다.</li>
                  <li>시장 상황에 따라 손실이 발생할 수 있습니다.</li>
                  <li>충분히 모의투자로 검증 후 진행하세요.</li>
                </ul>
              </div>
              <p className="text-xs text-slate-400 text-center">정말 실거래 투자를 진행하시겠습니까?</p>
              <div className="flex gap-2">
                <button onClick={onClose} className="btn-ghost flex-1 text-sm">취소</button>
                <button
                  onClick={() => { onConfirm(); onClose() }}
                  className="flex-1 py-2 rounded-lg text-sm font-medium bg-down/20 border border-down/40 text-down hover:bg-down/30 transition-colors"
                >
                  실거래 시작
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
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

function PositionCard({ pos, onClick, exchangeId }: { pos: AutoBotPosition; onClick: () => void; exchangeId?: string }) {
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
          {pos.risk_profile && (() => {
            const rm = RISK_PROFILE_META[pos.risk_profile]
            return rm ? (
              <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium border', rm.badge, rm.border)}>
                {rm.label}
              </span>
            ) : null
          })()}
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
          {pos.pyramid_count > 0 && (
            <span className="text-xs bg-brand-500/20 text-brand-400 px-1.5 py-0.5 rounded flex items-center gap-0.5">
              <Sparkles size={10} /> 피라미딩 {pos.pyramid_count}회
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
          {fmtCurrency(investedKrw, exchangeId)}
        </span>
        <span className="text-slate-600 mx-0.5">→</span>
        <span className="text-slate-400">현재가치</span>
        <span className={clsx('font-mono font-semibold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
          {fmtCurrency(currentKrw, exchangeId)}
        </span>
        <span className={clsx('ml-auto font-semibold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
          {pnlPos ? '+' : ''}{fmtCurrency(pos.unrealized_pnl_krw ?? 0, exchangeId)}
        </span>
      </div>

      {/* 세부 정보 그리드 */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-slate-500">평균단가</p>
          <p className="text-amber-400 font-mono font-semibold">{fmtCurrency(pos.avg_price, exchangeId)}</p>
        </div>
        <div>
          <p className="text-slate-500">현재가</p>
          <p className="text-slate-200 font-mono">{fmtCurrency(pos.current_price, exchangeId)}</p>
        </div>
        <div>
          <p className="text-slate-500">보유 ({base})</p>
          <p className="text-slate-200 font-mono">{pos.total_amount.toFixed(6)}</p>
        </div>
        <div>
          <p className="text-slate-500">손절가</p>
          <p className="text-down font-mono">{fmtCurrency(pos.stop_loss_price, exchangeId)}</p>
        </div>
        <div>
          <p className="text-slate-500">익절가</p>
          <p className="text-up font-mono">{fmtCurrency(pos.take_profit_price, exchangeId)}</p>
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

// ─── 선물 포지션 카드 ─────────────────────────────────────────────────────────

function FuturesPositionCard({ pos }: { pos: FuturesPosition }) {
  const pnlPos = pos.unrealized_pnl_pct >= 0
  const isLong = pos.side === 'long'
  const liqPct = pos.liquidation_price
    ? Math.abs(pos.current_price - pos.liquidation_price) / pos.current_price * 100
    : null

  return (
    <div className="bg-surface-700 rounded-lg p-3 space-y-2 border border-surface-600">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-slate-100">{pos.symbol}</span>
          <span className={clsx(
            'text-xs px-1.5 py-0.5 rounded font-bold border',
            isLong
              ? 'bg-up/20 border-up/40 text-up'
              : 'bg-down/20 border-down/40 text-down'
          )}>
            {isLong ? '롱' : '숏'} {pos.leverage}x
          </span>
          <span className="text-xs bg-surface-600 text-slate-400 px-1.5 py-0.5 rounded">
            {pos.margin_mode === 'cross' ? 'Cross' : 'Isolated'}
          </span>
        </div>
        <span className={clsx('text-sm font-bold tabular-nums', pnlPos ? 'text-up' : 'text-down')}>
          {pnlPos ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
        </span>
      </div>

      {/* 증거금 → 미실현 PnL */}
      <div className="flex items-center gap-2 bg-surface-600/60 rounded-lg px-2.5 py-1.5 text-xs">
        <span className="text-slate-400">증거금</span>
        <span className="font-mono font-semibold text-slate-100 tabular-nums">
          ${pos.initial_margin.toFixed(2)}
        </span>
        <span className="text-slate-600 mx-0.5">→</span>
        <span className={clsx('font-mono font-semibold tabular-nums ml-auto', pnlPos ? 'text-up' : 'text-down')}>
          {pnlPos ? '+' : ''}${pos.unrealized_pnl_usdt.toFixed(4)}
        </span>
      </div>

      {/* 세부 정보 */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-slate-500">진입가</p>
          <p className="text-amber-400 font-mono font-semibold">${pos.entry_price.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-slate-500">현재가</p>
          <p className="text-slate-200 font-mono">${pos.current_price.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-slate-500">수량</p>
          <p className="text-slate-200 font-mono">{pos.contracts.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-slate-500">손절가</p>
          <p className="text-down font-mono">${pos.stop_loss_price.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-slate-500">익절가</p>
          <p className="text-up font-mono">${pos.take_profit_price.toFixed(4)}</p>
        </div>
        <div>
          <p className="text-slate-500">청산가</p>
          <p className={clsx(
            'font-mono font-semibold',
            liqPct !== null && liqPct < 10 ? 'text-red-400 animate-pulse' : 'text-slate-400'
          )}>
            {pos.liquidation_price ? `$${pos.liquidation_price.toFixed(4)}` : '—'}
            {liqPct !== null && <span className="text-xs ml-1">({liqPct.toFixed(1)}%)</span>}
          </p>
        </div>
      </div>

      {/* 펀딩비 */}
      {pos.funding_rate !== 0 && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">펀딩비:</span>
          <span className={pos.funding_rate > 0 ? 'text-amber-400' : 'text-up'}>
            {(pos.funding_rate * 100).toFixed(4)}%
          </span>
          <span className="text-slate-600 text-xs">
            ({pos.funding_rate > 0 ? '롱 부담' : '숏 부담'})
          </span>
        </div>
      )}
    </div>
  )
}

// ─── 스캔 결과 / 거래 로그 행 ────────────────────────────────────────────────

function ScanRow({ r, rank }: { r: ScanResult; rank: number }) {
  const c = r.score >= 70 ? 'text-up' : r.score >= 50 ? 'text-amber-400' : 'text-slate-400'
  const stratColor = STRATEGY_COLORS[r.strategy_type] ?? STRATEGY_COLORS.standard
  const mtfLabel = r.mtf_trend === 'bullish' ? '↑HTF' : r.mtf_trend === 'bearish' ? '↓HTF' : null
  const mtfColor = r.mtf_trend === 'bullish' ? 'text-up' : 'text-down'
  return (
    <div className="py-2 border-b border-surface-700 last:border-0 space-y-1">
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-500 w-4">{rank}</span>
        <span className="text-sm font-medium text-slate-200 w-24">{r.symbol}</span>
        <span className={clsx('text-xs px-1.5 py-0.5 rounded font-medium', stratColor)}>
          {r.strategy_label}
        </span>
        {mtfLabel && (
          <span className={clsx('text-xs font-bold', mtfColor)}>{mtfLabel}</span>
        )}
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

function LogRow({ t, exchangeId }: { t: AutoBotTradeLog | AutoBotTradeDB; exchangeId?: string }) {
  const pos = t.pnl_pct >= 0
  // stop_loss인데 수익이면 "손절"이 아닌 "SL보호" (진입가 위에서 SL 발동)
  const reasonLabel = t.exit_reason === 'stop_loss'
    ? (t.pnl_pct > 0 ? 'SL보호' : '손절')
    : (REASON_LABEL[t.exit_reason] ?? t.exit_reason)
  const reasonColor = t.exit_reason === 'stop_loss'
    ? (t.pnl_pct > 0 ? 'bg-amber-500/20 text-amber-400' : 'bg-down/20 text-down')
    : (REASON_COLOR[t.exit_reason] ?? 'bg-surface-600 text-slate-400')
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
        {t.position_style_label && (
          <span className={clsx(
            'px-1.5 py-0.5 rounded font-medium border',
            STYLE_META[t.position_style ?? '']?.badge ?? 'bg-surface-600 text-slate-400',
            STYLE_META[t.position_style ?? '']?.border ?? 'border-surface-500',
          )}>
            {t.position_style_label}
          </span>
        )}
        {t.risk_profile && (() => {
          const rm = RISK_PROFILE_META[t.risk_profile]
          return rm ? (
            <span className={clsx('px-1.5 py-0.5 rounded font-medium border', rm.badge, rm.border)}>
              {rm.label}
            </span>
          ) : null
        })()}
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
          {pos ? '+' : ''}{fmtCurrency(t.pnl_krw, exchangeId)}
        </span>
      </div>

      {/* ── 2행: 가격 / 금액 ── */}
      <div className="flex items-center gap-1.5 bg-surface-700/60 rounded px-2.5 py-1.5 font-mono flex-wrap">
        <span className="text-slate-500">매수</span>
        <span className="text-amber-400 font-semibold">{fmtCurrency(t.avg_price, exchangeId)}</span>
        <span className="text-slate-600 mx-0.5">×</span>
        <span className="text-slate-300">{t.total_amount.toFixed(6)} {base}</span>
        <span className="text-slate-600 mx-1">=</span>
        <span className="text-slate-200">{fmtCurrency(investKrw, exchangeId)}</span>
        <span className="text-slate-600 mx-1">→</span>
        <span className="text-slate-500">매도</span>
        <span className={clsx('font-semibold', pos ? 'text-up' : 'text-down')}>
          {fmtCurrency(t.exit_price, exchangeId)}
        </span>
        <span className="text-slate-600 mx-0.5">=</span>
        <span className={clsx(pos ? 'text-up/80' : 'text-down/80')}>
          {fmtCurrency(exitKrw, exchangeId)}
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
  const [tab, setTab] = useState<'positions' | 'scan' | 'log' | 'ai' | 'forecast' | 'perf'>('positions')
  const [showLiveModal, setShowLiveModal] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState<{
    message: string
    detail?: string
    confirmText?: string
    variant?: 'danger' | 'warning' | 'info'
    onConfirm: () => void
  } | null>(null)

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
  const pauseMut = useMutation({
    mutationFn: () => api.post('/auto-bot/pause'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const resumeMut = useMutation({
    mutationFn: () => api.post('/auto-bot/resume'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const fullStopMut = useMutation({
    mutationFn: (isPaper: boolean) => api.post('/auto-bot/full-stop', { is_paper: isPaper }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auto-bot-status'] })
      qc.invalidateQueries({ queryKey: ['auto-bot-trades'] })
      qc.invalidateQueries({ queryKey: ['auto-bot-trade-stats'] })
    },
  })
  const scanMut = useMutation({
    mutationFn: () => api.post('/auto-bot/scan'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const settingsMut = useMutation({
    mutationFn: (s: object) => api.patch('/auto-bot/settings', s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })
  const balanceMut = useMutation({
    mutationFn: (krw: number) => api.patch('/auto-bot/balance', { krw }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })

  const [balanceEdit, setBalanceEdit] = useState(false)
  const [balanceInput, setBalanceInput] = useState('')

  if (isLoading || !status) {
    return <div className="card"><p className="text-slate-500 text-sm">로딩 중...</p></div>
  }

  const exchangeId = status.settings.exchange_id ?? 'upbit'
  const isFutures  = (status.settings.market_type ?? 'spot') === 'futures'
  const isPaper    = status.settings.is_paper ?? true

  const handleModeToggle = () => {
    if (isPaper) {
      // 모의 → 실거래: 검증 모달 열기
      setShowLiveModal(true)
    } else {
      // 실거래 → 모의: 간단 확인
      setConfirmDialog({
        message: '모의투자 모드로 전환합니다.',
        detail: '실거래 봇이 즉시 중단되지는 않습니다. 봇을 별도로 중단해주세요.',
        confirmText: '모의투자로 전환',
        variant: 'info',
        onConfirm: () => settingsMut.mutate({ is_paper: true }),
      })
    }
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

      {showLiveModal && (
        <LiveSwitchModal
          exchangeId={exchangeId}
          onConfirm={() => settingsMut.mutate({ is_paper: false })}
          onClose={() => setShowLiveModal(false)}
        />
      )}

      {confirmDialog && (
        <ConfirmModal
          message={confirmDialog.message}
          detail={confirmDialog.detail}
          confirmText={confirmDialog.confirmText}
          variant={confirmDialog.variant}
          onConfirm={confirmDialog.onConfirm}
          onClose={() => setConfirmDialog(null)}
        />
      )}

      {livePos && (
        <PositionDetailModal
          pos={livePos}
          maxAvgDown={status.settings.max_avg_down}
          maxAdd={status.settings.max_add}
          onClose={() => setSelectedPos(null)}
          exchangeId={exchangeId}
          feeRate={status.fee_rate}
        />
      )}

      <div className="card space-y-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Bot size={18} className={status.running ? 'text-brand-400' : 'text-slate-500'} />
            <h2 className="font-semibold text-slate-100">자동매매봇</h2>
            {/* 거래소 배지 */}
            <span className={clsx('text-xs px-2 py-0.5 rounded font-medium bg-surface-700', EXCHANGE_COLOR[exchangeId] ?? 'text-slate-300')}>
              {EXCHANGE_LABEL[exchangeId] ?? exchangeId}
            </span>
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
            {/* 모의/실거래 토글 */}
            <div className="flex items-center gap-1.5 bg-surface-700 rounded-full px-1 py-1 border border-surface-600">
              <button
                onClick={!isPaper && !status.running ? handleModeToggle : undefined}
                disabled={!isPaper && status.running}
                className={clsx(
                  'px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors',
                  isPaper
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'text-slate-500 hover:text-slate-300'
                )}
              >
                모의
              </button>
              <button
                onClick={isPaper && !status.running ? handleModeToggle : undefined}
                disabled={!isPaper && status.running}
                className={clsx(
                  'px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors',
                  !isPaper
                    ? 'bg-down/20 text-down border border-down/40'
                    : 'text-slate-500 hover:text-slate-300'
                )}
              >
                실거래
              </button>
            </div>
            {status.running && (
              <span className="text-xs text-slate-600">
                (봇 중단 후 전환 가능)
              </span>
            )}

            {/* 실행 상태 배지 */}
            {status.running ? (
              status.paused ? (
                <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-amber-500/20 text-amber-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  일시정지
                </span>
              ) : (
                <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-up/20 text-up">
                  <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
                  실행 중
                </span>
              )
            ) : (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-surface-700 text-slate-400">
                중지됨
              </span>
            )}
            {status.running && uptime && (
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <Clock size={11} /> {uptime}
              </span>
            )}
            {status.paused && (
              <span className="text-xs text-amber-500/70">신규 진입 차단 중</span>
            )}
            {!status.paused && status.scan_in_progress && (
              <span className="text-xs text-amber-400 flex items-center gap-1">
                <RefreshCw size={11} className="animate-spin" /> 스캔 중...
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowSettings(true)} className="p-1.5 text-slate-400 hover:text-slate-200">
              <Settings2 size={16} />
            </button>
            {status.running && (
              <button
                onClick={() => scanMut.mutate()}
                disabled={status.scan_in_progress || status.paused}
                className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 bg-surface-700 hover:bg-surface-600 border border-surface-600 rounded-lg text-slate-300 transition-colors disabled:opacity-50"
              >
                <Zap size={12} /> 시장 스캔
              </button>
            )}
            {status.running ? (
              <>
                {status.paused ? (
                  <button
                    onClick={() => resumeMut.mutate()}
                    disabled={resumeMut.isPending}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-up/20 border border-up/40 text-up rounded-lg hover:bg-up/30 transition-colors disabled:opacity-50"
                  >
                    <Play size={13} /> 재개
                  </button>
                ) : (
                  <button
                    onClick={() => pauseMut.mutate()}
                    disabled={pauseMut.isPending}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-amber-500/20 border border-amber-500/40 text-amber-400 rounded-lg hover:bg-amber-500/30 transition-colors disabled:opacity-50"
                  >
                    <Pause size={13} /> 일시정지
                  </button>
                )}
                <button
                  onClick={() => setConfirmDialog({
                    message: '봇을 중단하시겠습니까?',
                    detail: isPaper
                      ? '모든 포지션이 현재가에 청산되고 모의 잔고·기록이 초기화됩니다.'
                      : '모든 포지션이 현재가에 청산됩니다.',
                    confirmText: '중단',
                    variant: 'danger',
                    onConfirm: () => fullStopMut.mutate(isPaper),
                  })}
                  disabled={fullStopMut.isPending}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-down/20 border border-down/40 text-down rounded-lg hover:bg-down/30 transition-colors disabled:opacity-50"
                >
                  <Square size={13} /> 중단
                </button>
              </>
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
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
          <div className={clsx('bg-surface-700 rounded-lg p-2.5', !isPaper && 'border border-down/30')}>
            <p className="text-xs text-slate-500">
              {isPaper ? '모의 잔고' : '실거래 잔고'}
              <span className="ml-1 text-slate-600">({status.quote_currency ?? (exchangeId === 'upbit' ? 'KRW' : 'USDT')})</span>
            </p>
            {balanceEdit ? (
              <div className="flex items-center gap-1 mt-0.5">
                <input
                  type="number"
                  className="w-full bg-surface-600 text-slate-100 text-xs rounded px-1.5 py-0.5 tabular-nums"
                  placeholder={`${status.quote_currency ?? (exchangeId === 'upbit' ? 'KRW' : 'USDT')} 입력`}
                  value={balanceInput}
                  onChange={e => setBalanceInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const v = Number(balanceInput)
                      if (!isNaN(v) && v >= 0) { balanceMut.mutate(v); setBalanceEdit(false) }
                    }
                    if (e.key === 'Escape') setBalanceEdit(false)
                  }}
                  autoFocus
                />
                <button
                  className="text-xs text-brand-400 hover:text-brand-300 shrink-0"
                  onClick={() => {
                    const v = Number(balanceInput)
                    if (!isNaN(v) && v >= 0) { balanceMut.mutate(v); setBalanceEdit(false) }
                  }}
                >확인</button>
              </div>
            ) : (
              <div className="flex items-center gap-1 mt-0.5">
                <p className="text-sm font-semibold tabular-nums text-slate-100">
                  {fmtCurrency(status.balance_krw, status.quote_currency ?? exchangeId)}
                </p>
                <button
                  className={status.running ? 'text-slate-600 cursor-not-allowed' : 'text-slate-500 hover:text-slate-300'}
                  onClick={() => { if (!status.running) { setBalanceInput(String(status.balance_krw)); setBalanceEdit(true) } }}
                  title={status.running ? '봇 중지 후 수정 가능' : '잔고 수정'}
                  disabled={status.running}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
              </div>
            )}
          </div>
          <StatCard label={`총 평가 (${status.quote_currency ?? (exchangeId === 'upbit' ? 'KRW' : 'USDT')})`} value={fmtCurrency(status.total_value_krw, status.quote_currency ?? exchangeId)} />
          <StatCard label="수수료" value={`${+((status.fee_rate ?? 0.0005) * 100).toFixed(3)}%`} />
          <StatCard
            label={`실현 손익 (${status.quote_currency ?? (exchangeId === 'upbit' ? 'KRW' : 'USDT')})`}
            value={(() => {
              const pnl = tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.total_trades > 0 ? status.realized_pnl_krw : null
              return pnl !== null ? `${pnl >= 0 ? '+' : ''}${fmtCurrency(pnl, status.quote_currency ?? exchangeId)}` : '—'
            })()}
            color={(() => {
              const pnl = tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.total_trades > 0 ? status.realized_pnl_krw : null
              return pnl !== null && pnl > 0 ? 'up' : pnl !== null && pnl < 0 ? 'down' : undefined
            })()}
            sub={(() => {
              const pnl = tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.total_trades > 0 ? status.realized_pnl_krw : null
              if (pnl === null) return undefined
              const initial = status.total_value_krw - status.realized_pnl_krw - status.unrealized_pnl_krw
              if (initial <= 0) return undefined
              const pct = pnl / initial * 100
              return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
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
                  {fmtCurrency(status.unrealized_pnl_krw, exchangeId)}
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
                    {p.unrealized_pnl_krw >= 0 ? '+' : ''}{fmtCurrency(p.unrealized_pnl_krw, exchangeId)}
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
          <span>일손실한도 <b className="text-amber-400">{status.settings.max_daily_loss_pct ?? 5}%</b></span>
          <span>물타기 <b className={status.settings.auto_avg_down ? 'text-amber-400' : 'text-slate-500'}>{status.settings.auto_avg_down ? `ON (${status.settings.avg_down_threshold_pct}%)` : 'OFF'}</b></span>
          <span>추매 <b className={status.settings.auto_add ? 'text-up' : 'text-slate-500'}>{status.settings.auto_add ? `ON (${status.settings.add_threshold_pct}%)` : 'OFF'}</b></span>
          <span>피라미딩 <b className={status.settings.pyramid_enabled ? 'text-brand-400' : 'text-slate-500'}>{status.settings.pyramid_enabled ? `ON (${status.settings.pyramid_threshold_pct ?? 3}%)` : 'OFF'}</b></span>
          {isFutures && (
            <span className="text-amber-400 font-medium">
              선물 {status.settings.leverage ?? 5}x · {status.settings.margin_mode === 'isolated' ? 'Isolated' : 'Cross'}
            </span>
          )}
          {status.paused && (
            <span className="ml-auto text-amber-500/80 font-medium flex items-center gap-1">
              <Pause size={10} /> 신규 진입 차단 중 · SL/TP 모니터 유지
            </span>
          )}
          {!status.paused && status.last_scan_at && <span className="ml-auto text-slate-500">마지막 스캔: {status.last_scan_at}</span>}
        </div>

        {/* 탭 */}
        <div className="flex gap-1 border-b border-surface-700">
          {([
            ['positions', `포지션 (${status.positions.length})`],
            ['scan', `스캔 결과 (${status.scan_results.length})`],
            ['log', `거래 내역 (${tradeStats?.total ?? status.total_trades})`],
            ['ai', `AI 활동 (${status.ai_analysis_log?.length ?? 0})`],
            ['forecast', `예상 수익 (${status.forecast_log?.length ?? 0})`],
            ['perf', '성과 분석'],
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
          (isFutures ? (status.futures_positions ?? []).length : status.positions.length) === 0 ? (
            <p className="text-sm text-slate-500 py-2">
              {status.running
                ? '진입 조건을 탐색 중... 스캔 후 조건 충족 종목에 자동 진입합니다.'
                : '봇을 시작하면 시장을 분석하여 자동으로 종목을 선택하고 매매합니다.'}
            </p>
          ) : isFutures ? (
            /* 선물 포지션 카드 */
            (status.futures_positions ?? []).length === 0 ? (
              <p className="text-sm text-slate-500 py-2">진입 조건을 탐색 중... 스캔 후 조건 충족 종목에 자동 진입합니다.</p>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
                {(status.futures_positions ?? []).map(p => (
                  <FuturesPositionCard key={p.symbol} pos={p} />
                ))}
              </div>
            )
          ) : (
            /* 현물 포지션 카드 */
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
              {status.positions.map(p => (
                <PositionCard
                  key={p.symbol}
                  pos={p}
                  onClick={() => setSelectedPos(p)}
                  exchangeId={exchangeId}
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

        {tab === 'forecast' && (
          <ForecastTab log={status.forecast_log ?? []} />
        )}

        {tab === 'perf' && (
          <PerformancePanel
            perf={status.performance ?? {
              sharpe_ratio: 0, sortino_ratio: 0, calmar_ratio: 0, profit_factor: 0,
              expectancy_pct: 0, max_drawdown_pct: 0, avg_win_pct: 0, avg_loss_pct: 0,
              win_rate: 0, best_trade_pct: 0, worst_trade_pct: 0, total_trades: 0,
            }}
            trades={dbTrades && dbTrades.length > 0 ? dbTrades : status.trade_log}
            dailyPnlKrw={status.daily_pnl_krw ?? 0}
            maxDailyLossPct={status.settings.max_daily_loss_pct ?? 5}
            totalValueKrw={status.total_value_krw}
            exchangeId={exchangeId}
          />
        )}

        {tab === 'log' && (
          <>
            {/* 실현 손익 요약 */}
            {((tradeStats && tradeStats.total > 0) || status.total_trades > 0) && (
              <div className={clsx(
                'rounded-lg border text-xs mb-2 overflow-hidden',
                (tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.realized_pnl_krw) >= 0
                  ? 'border-up/20' : 'border-down/20'
              )}>
                {/* 윗줄: 손익 합산 3분할 */}
                {(() => {
                  const trades = dbTrades && dbTrades.length > 0 ? dbTrades : status.trade_log
                  const pnl = tradeStats && tradeStats.total > 0 ? tradeStats.total_pnl_krw : status.realized_pnl_krw
                  const initial = status.total_value_krw - status.realized_pnl_krw - status.unrealized_pnl_krw
                  const pct = initial > 0 ? pnl / initial * 100 : null
                  const profitSum = trades.filter(t => t.pnl_krw > 0).reduce((s, t) => s + t.pnl_krw, 0)
                  const lossSum   = trades.filter(t => t.pnl_krw < 0).reduce((s, t) => s + t.pnl_krw, 0)
                  const netPos = pnl >= 0
                  return (
                    <div className="grid grid-cols-3 divide-x divide-surface-700">
                      <div className="px-4 py-3 bg-up/5">
                        <p className="text-slate-500 mb-1">+수익 합계</p>
                        <p className="text-up font-bold tabular-nums text-sm">+{fmtCurrency(profitSum, exchangeId)}</p>
                      </div>
                      <div className="px-4 py-3 bg-down/5">
                        <p className="text-slate-500 mb-1">-손해 합계</p>
                        <p className="text-down font-bold tabular-nums text-sm">{fmtCurrency(lossSum, exchangeId)}</p>
                      </div>
                      <div className="px-4 py-3">
                        <p className="text-slate-500 mb-1">합계{!(tradeStats && tradeStats.total > 0) && ' (세션)'}</p>
                        <div className="flex items-baseline gap-1">
                          <p className={clsx('font-bold tabular-nums text-sm', netPos ? 'text-up' : 'text-down')}>
                            {netPos ? '+' : ''}{fmtCurrency(pnl, exchangeId)}
                          </p>
                          {pct !== null && (
                            <span className={clsx('tabular-nums', netPos ? 'text-up/70' : 'text-down/70')}>
                              ({pct >= 0 ? '+' : ''}{pct.toFixed(2)}%)
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })()}
                {/* 아랫줄: 통계 지표 */}
                <div className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-2.5 border-t border-surface-700 bg-surface-800/40">
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-500">총 거래</span>
                    <span className="text-slate-200 font-semibold">{tradeStats?.total ?? status.total_trades}건</span>
                  </div>
                  {tradeStats && tradeStats.total > 0 && <>
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-500">승률</span>
                      <span className="text-slate-200 font-semibold">{tradeStats.win_rate}%</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-500">평균 손익</span>
                      <span className={clsx('font-semibold', tradeStats.avg_pnl_pct >= 0 ? 'text-up' : 'text-down')}>
                        {tradeStats.avg_pnl_pct >= 0 ? '+' : ''}{tradeStats.avg_pnl_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-500">최고</span>
                      <span className="text-up font-semibold">+{tradeStats.best_trade_pct.toFixed(2)}%</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-500">최저</span>
                      <span className="text-down font-semibold">{tradeStats.worst_trade_pct.toFixed(2)}%</span>
                    </div>
                  </>}
                </div>
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
                    <LogRow key={'id' in t ? t.id : i} t={t} exchangeId={exchangeId} />
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

  if (type === 'surge_override') {
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <TrendingUp size={14} className="mt-0.5 flex-shrink-0 text-up" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">급등 오버라이드 진입</span>
              <span className="text-slate-300 font-mono">{entry.symbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-up/20 text-up font-medium">
                vol {entry.volume_ratio?.toFixed(1)}x
              </span>
              <span className="px-1.5 py-0.5 rounded bg-up/20 text-up font-medium">
                {entry.price_change_pct !== undefined ? `+${entry.price_change_pct.toFixed(1)}%` : ''}
              </span>
              <span className="text-slate-500">점수 {entry.score}</span>
            </div>
            <p className="text-slate-400 mt-1">BTC 국면 무관 · short 스타일 적용</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  if (type === 'opportunistic_entry') {
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <Sparkles size={14} className="mt-0.5 flex-shrink-0 text-brand-400" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">기회 진입</span>
              <span className="text-slate-300 font-mono">{entry.symbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-brand-500/20 text-brand-300 font-medium">
                점수 {entry.score}
              </span>
              {entry.style && (
                <span className="px-1.5 py-0.5 rounded bg-surface-600 text-slate-300">{entry.style}</span>
              )}
            </div>
            <p className="text-slate-400 mt-1">시장 국면 무관 개별 강세 종목</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  if (type === 'scalping_parallel') {
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-1">
        <div className="flex items-start gap-2">
          <TrendingUp size={14} className="mt-0.5 flex-shrink-0 text-amber-400" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">초단타 병렬 진입</span>
              <span className="text-slate-300 font-mono">{entry.symbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-medium">
                점수 {entry.score}
              </span>
              <span className="px-1.5 py-0.5 rounded bg-surface-600 text-slate-300">5m</span>
            </div>
            <p className="text-slate-400 mt-1">5m 병렬 스캔 · scalping 스타일</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  if (type === 'entry_forecast') {
    const fc = entry.forecast
    const ev = entry.ev_per_trade ?? 0
    const fmtPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
    const periods: [string, '1d' | '1w' | '1m' | '1y'][] = [['1일', '1d'], ['1주', '1w'], ['1달', '1m'], ['1년', '1y']]
    return (
      <div className="py-3 border-b border-surface-700 last:border-0 text-xs space-y-2">
        <div className="flex items-start gap-2">
          <TrendingUp size={14} className="mt-0.5 flex-shrink-0 text-brand-400" />
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-200">예상 수익 분석</span>
              <span className="text-slate-300 font-mono">{entry.symbol}</span>
              <span className="px-1.5 py-0.5 rounded bg-surface-600 text-slate-400">
                TP +{entry.tp_pct}% / SL -{entry.sl_pct}%
              </span>
              <span className="px-1.5 py-0.5 rounded bg-surface-600 text-slate-400">
                승률 {entry.win_rate}%
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-1 text-slate-400">
              <span>거래당 기대값</span>
              <span className={clsx('font-semibold', ev >= 0 ? 'text-up' : 'text-down')}>{fmtPct(ev)}</span>
              {entry.leverage && entry.leverage > 1 && (
                <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold">{entry.leverage}x</span>
              )}
              {entry.fee_pct !== undefined && (
                <span className="text-slate-600">수수료 -{entry.fee_pct}% 포함</span>
              )}
              {entry.position_style && (
                <span className="text-slate-600">· {entry.position_style}</span>
              )}
            </div>
            {fc && (
              <div className="grid grid-cols-4 gap-1 mt-2">
                {periods.map(([label, key]) => {
                  const val = fc[key]
                  const isMax = val >= 9999
                  return (
                    <div key={label} className="bg-surface-800 rounded px-2 py-1.5 text-center">
                      <div className="text-slate-500 text-[10px] mb-0.5">{label}</div>
                      <div className={clsx('font-semibold text-[11px]', val >= 0 ? 'text-up' : 'text-down')}>
                        {isMax ? '—' : fmtPct(val)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
            <p className="text-slate-600 text-[10px] mt-1.5">* 수수료 포함·선형 추정. 실제 수익을 보장하지 않습니다.</p>
          </div>
          <span className="text-slate-600 flex-shrink-0">{entry.at}</span>
        </div>
      </div>
    )
  }

  return null
}

// ─── 성과 분석 패널 ─────────────────────────────────────────────────────────

function PerfRow({ label, value, color, sub, tooltip }: { label: string; value: string; color?: 'up' | 'down' | 'neutral'; sub?: string; tooltip?: string }) {
  const vc = color === 'up' ? 'text-up' : color === 'down' ? 'text-down' : 'text-slate-200'
  return (
    <div className="flex items-center justify-between py-2 border-b border-surface-700 last:border-0 text-xs">
      <span className="text-slate-400 flex items-center gap-1">
        {label}
        {tooltip && (
          <Tooltip text={tooltip} iconOnly />
        )}
      </span>
      <div className="text-right">
        <span className={`font-semibold tabular-nums ${vc}`}>{value}</span>
        {sub && <span className="text-slate-500 ml-1.5">{sub}</span>}
      </div>
    </div>
  )
}

type TradeLike = { pnl_pct: number; position_style?: string; position_style_label?: string; risk_profile?: string }

function calcBreakdown(trades: TradeLike[], groupBy: 'position_style' | 'risk_profile') {
  const map: Record<string, { wins: number; total: number; pnl: number; label: string }> = {}
  for (const t of trades) {
    const key = t[groupBy] ?? 'unknown'
    const label = groupBy === 'position_style'
      ? (t.position_style_label ?? key)
      : (RISK_PROFILE_META[key]?.label ?? key)
    if (!map[key]) map[key] = { wins: 0, total: 0, pnl: 0, label }
    map[key].total++
    map[key].pnl = +(map[key].pnl + t.pnl_pct).toFixed(2)
    if (t.pnl_pct > 0) map[key].wins++
  }
  return Object.entries(map).map(([key, v]) => ({
    key, label: v.label,
    total: v.total,
    winRate: v.total > 0 ? Math.round(v.wins / v.total * 100) : 0,
    avgPnl: v.total > 0 ? +(v.pnl / v.total).toFixed(2) : 0,
  }))
}

function PerformancePanel({ perf, trades = [], dailyPnlKrw, maxDailyLossPct, totalValueKrw, exchangeId }: {
  perf: PerformanceStats
  trades?: TradeLike[]
  dailyPnlKrw: number
  maxDailyLossPct: number
  totalValueKrw: number
  exchangeId?: string
}) {
  const dailyLimitKrw = Math.round(totalValueKrw * maxDailyLossPct / 100)
  const dailyUsedPct = dailyLimitKrw > 0 ? Math.min(100, Math.abs(Math.min(0, dailyPnlKrw)) / dailyLimitKrw * 100) : 0

  if (perf.total_trades === 0) {
    return <p className="text-sm text-slate-500 py-4 text-center">거래 내역이 없습니다.</p>
  }

  return (
    <div className="space-y-4">
      {/* 일일 손실 한도 게이지 */}
      <div className="bg-surface-700 rounded-lg p-3">
        <div className="flex items-center justify-between text-xs mb-2">
          <span className="text-slate-400">일일 손실 현황</span>
          <span className={dailyPnlKrw < 0 ? 'text-down font-semibold' : 'text-up font-semibold'}>
            {dailyPnlKrw >= 0 ? '+' : ''}{fmtCurrency(dailyPnlKrw, exchangeId)}
            <span className="text-slate-500 font-normal ml-1">/ 한도 -{fmtCurrency(dailyLimitKrw, exchangeId)}</span>
          </span>
        </div>
        <div className="w-full h-2 bg-surface-600 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${dailyUsedPct >= 80 ? 'bg-down' : dailyUsedPct >= 50 ? 'bg-amber-500' : 'bg-up'}`}
            style={{ width: `${dailyUsedPct}%` }}
          />
        </div>
      </div>

      {/* 리스크 조정 수익 지표 */}
      <div>
        <p className="text-xs text-slate-500 mb-1 font-medium">리스크 조정 수익</p>
        <PerfRow label="샤프 비율" value={perf.sharpe_ratio.toFixed(2)}
          color={perf.sharpe_ratio >= 1 ? 'up' : perf.sharpe_ratio >= 0 ? 'neutral' : 'down'}
          sub="(≥1 양호)"
          tooltip="수익률을 변동성(위험)으로 나눈 값입니다. 1 이상이면 감수한 리스크 대비 수익이 충분하다는 의미이고, 클수록 좋습니다." />
        <PerfRow label="소르티노 비율" value={perf.sortino_ratio.toFixed(2)}
          color={perf.sortino_ratio >= 1 ? 'up' : perf.sortino_ratio >= 0 ? 'neutral' : 'down'}
          sub="(하방 리스크)"
          tooltip="샤프 비율과 비슷하지만, 손실이 날 때의 변동성만 위험으로 계산합니다. 수익이 오르내리는 건 위험으로 보지 않으므로 하락 리스크를 더 정확히 반영합니다." />
        <PerfRow label="칼마 비율" value={perf.calmar_ratio.toFixed(2)}
          color={perf.calmar_ratio >= 1 ? 'up' : perf.calmar_ratio >= 0 ? 'neutral' : 'down'}
          sub="(수익/MDD)"
          tooltip="총 수익률을 최대 낙폭(MDD)으로 나눈 값입니다. 최악의 손실 구간 대비 얼마나 벌었는지를 나타내며, 1 이상이면 손실폭보다 수익이 더 크다는 뜻입니다." />
        <PerfRow label="프로핏 팩터" value={perf.profit_factor.toFixed(2)}
          color={perf.profit_factor >= 1.5 ? 'up' : perf.profit_factor >= 1 ? 'neutral' : 'down'}
          sub="(≥1.5 양호)"
          tooltip="전체 수익의 합 ÷ 전체 손실의 합입니다. 1.5이면 손실 1원당 수익이 1.5원이라는 의미로, 1보다 크면 수익이 손실보다 많습니다." />
      </div>

      {/* 거래 통계 */}
      <div>
        <p className="text-xs text-slate-500 mb-1 font-medium">거래 통계</p>
        <PerfRow label="기대값 (Expectancy)" value={`${perf.expectancy_pct >= 0 ? '+' : ''}${perf.expectancy_pct.toFixed(2)}%`}
          color={perf.expectancy_pct >= 0 ? 'up' : 'down'}
          tooltip="거래 1건당 기대되는 평균 수익률입니다. 승률과 평균 손익을 함께 반영하며, 양수면 장기적으로 수익이 쌓인다는 뜻입니다." />
        <PerfRow label="최대 낙폭 (MDD)" value={`-${perf.max_drawdown_pct.toFixed(2)}%`} color="down"
          tooltip="고점에서 저점까지 가장 크게 떨어진 낙폭입니다. 전략이 최악의 구간에서 얼마나 손실을 봤는지를 나타내며, 작을수록 안전합니다." />
        <PerfRow label="평균 수익 거래" value={`+${perf.avg_win_pct.toFixed(2)}%`} color="up"
          tooltip="수익이 난 거래들의 평균 수익률입니다." />
        <PerfRow label="평균 손실 거래" value={`${perf.avg_loss_pct.toFixed(2)}%`} color="down"
          tooltip="손실이 난 거래들의 평균 손실률입니다." />
        <PerfRow label="최고 수익" value={`+${perf.best_trade_pct.toFixed(2)}%`} color="up"
          tooltip="지금까지 가장 수익이 많이 난 단일 거래의 수익률입니다." />
        <PerfRow label="최대 손실" value={`${perf.worst_trade_pct.toFixed(2)}%`} color="down"
          tooltip="지금까지 가장 손실이 많이 난 단일 거래의 손실률입니다." />
      </div>

      {/* 매매 스타일 / 투자 성향별 성과 */}
      {trades.length > 0 && (() => {
        const styleRows = calcBreakdown(trades, 'position_style')
        const riskRows  = calcBreakdown(trades, 'risk_profile')
        const headers = (
          <div className="grid grid-cols-4 gap-1 text-slate-500 text-xs px-1 mb-1">
            <span>구분</span><span className="text-right">거래</span>
            <span className="text-right">승률</span><span className="text-right">평균손익</span>
          </div>
        )
        const row = (key: string, label: string, total: number, winRate: number, avgPnl: number, badge: string) => (
          <div key={key} className="grid grid-cols-4 gap-1 items-center py-1.5 border-b border-surface-700 last:border-0 text-xs px-1">
            <span className={clsx('px-1.5 py-0.5 rounded font-medium w-fit', badge)}>{label}</span>
            <span className="text-right text-slate-300 tabular-nums">{total}</span>
            <span className={clsx('text-right tabular-nums font-semibold', winRate >= 50 ? 'text-up' : 'text-down')}>{winRate}%</span>
            <span className={clsx('text-right tabular-nums font-semibold', avgPnl >= 0 ? 'text-up' : 'text-down')}>
              {avgPnl >= 0 ? '+' : ''}{avgPnl.toFixed(2)}%
            </span>
          </div>
        )
        return (
          <>
            <div>
              <p className="text-xs text-slate-500 mb-1 font-medium">매매 스타일별 성과</p>
              <div className="bg-surface-700/50 rounded-lg p-2">
                {headers}
                {styleRows.map(r => row(r.key, r.label, r.total, r.winRate, r.avgPnl,
                  STYLE_META[r.key]?.badge ?? 'bg-surface-600 text-slate-400'))}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1 font-medium">투자 성향별 성과</p>
              <div className="bg-surface-700/50 rounded-lg p-2">
                {headers}
                {riskRows.map(r => row(r.key, r.label, r.total, r.winRate, r.avgPnl,
                  RISK_PROFILE_META[r.key]?.badge ?? 'bg-surface-600 text-slate-400'))}
              </div>
            </div>
          </>
        )
      })()}
    </div>
  )
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

function ForecastTab({ log }: { log: AiAnalysisLogEntry[] }) {
  if (log.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-slate-500">
        <TrendingUp size={24} className="mx-auto mb-2 text-slate-600" />
        <p>아직 예상 수익 데이터가 없습니다.</p>
        <p className="text-xs mt-1 text-slate-600">봇이 포지션에 진입하면 자동으로 기록됩니다.</p>
      </div>
    )
  }

  const fmtPct = (v: number, isMax: boolean) => isMax ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
  const periods: ('1d' | '1w' | '1m' | '1y')[] = ['1d', '1w', '1m', '1y']

  const colHeaders: { key: string; label: string; tooltip: string }[] = [
    {
      key: 'ev',
      label: '거래 EV',
      tooltip: '거래 1건당 기대 수익률.\n(승률 × TP%) − (패률 × SL%) − 수수료\n양수면 장기적으로 수익, 음수면 손실 구조.',
    },
    {
      key: '1d',
      label: '1일 예상',
      tooltip: '하루 동안 예상되는 누적 수익률.\n거래 EV × 하루 예상 거래 횟수 (선형 추정).',
    },
    {
      key: '1w',
      label: '1주 예상',
      tooltip: '1주일(7일) 동안 예상되는 누적 수익률.\n거래 EV × 주간 예상 거래 횟수 (선형 추정).',
    },
    {
      key: '1m',
      label: '1달 예상',
      tooltip: '1달(30일) 동안 예상되는 누적 수익률.\n거래 EV × 월간 예상 거래 횟수 (선형 추정).',
    },
    {
      key: '1y',
      label: '1년 예상',
      tooltip: '1년(365일) 동안 예상되는 누적 수익률.\n거래 EV × 연간 예상 거래 횟수 (선형 추정).\n단순 참고치로 실제와 큰 차이가 날 수 있습니다.',
    },
    {
      key: 'wr',
      label: '승률',
      tooltip: '최근 거래 이력 기반 실제 승률.\n거래 이력이 5건 미만이면 기본값 50% 적용.',
    },
  ]

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">* 수수료 포함·선형 추정치. 복리 미적용. 실제 수익을 보장하지 않습니다.</p>

      {/* 헤더 */}
      <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-x-3 text-[10px] text-slate-500 px-3 py-1">
        <span>종목 / 진입 시각</span>
        {colHeaders.map(h => (
          <Tooltip key={h.key} text={h.tooltip}>
            <span className="text-right cursor-help underline decoration-dotted decoration-slate-600">{h.label}</span>
          </Tooltip>
        ))}
      </div>

      <div className="divide-y divide-surface-700">
        {log.map((entry, i) => {
          const fc = entry.forecast
          const ev = entry.ev_per_trade ?? 0
          const evPos = ev >= 0
          const isDefaultWr = !entry.win_rate_basis || entry.win_rate_basis === 0
          return (
            <div key={i} className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-x-3 items-center px-3 py-2.5 text-xs hover:bg-surface-700/40 transition-colors">
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-slate-200 font-medium">{entry.symbol}</span>
                  {entry.position_style && (
                    <span className="px-1 rounded bg-surface-600 text-slate-400 text-[10px]">{entry.position_style}</span>
                  )}
                  {entry.leverage && entry.leverage > 1 && (
                    <span className="px-1 rounded bg-amber-500/20 text-amber-300 font-semibold text-[10px]">{entry.leverage}x</span>
                  )}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-1.5">
                  <span>{entry.at}</span>
                  <span className="text-slate-600">TP+{entry.tp_pct}% / SL-{entry.sl_pct}%</span>
                  {entry.fee_pct !== undefined && (
                    <span className="text-slate-600">수수료 {entry.fee_pct}%</span>
                  )}
                </div>
              </div>

              {/* 거래 EV */}
              <span className={clsx('text-right tabular-nums font-semibold', evPos ? 'text-up' : 'text-down')}>
                {evPos ? '+' : ''}{ev.toFixed(2)}%
              </span>

              {/* 1일~1년 */}
              {fc ? periods.map(p => {
                const val = fc[p]
                const isMax = val >= 9999
                return (
                  <span key={p} className={clsx('text-right tabular-nums font-semibold', isMax ? 'text-slate-500' : val >= 0 ? 'text-up' : 'text-down')}>
                    {fmtPct(val, isMax)}
                  </span>
                )
              }) : periods.map(p => <span key={p} className="text-right text-slate-600">—</span>)}

              {/* 승률 */}
              <Tooltip text={isDefaultWr ? '거래 이력 5건 미만 — 기본값 50% 적용 중입니다.\n실거래가 쌓이면 실제 승률로 업데이트됩니다.' : `최근 ${entry.win_rate_basis}건 거래 기반 실제 승률`}>
                <span className={clsx('text-right tabular-nums cursor-help', isDefaultWr ? 'text-slate-500' : 'text-slate-300')}>
                  {entry.win_rate}%
                  {isDefaultWr && <span className="text-slate-600 text-[9px] ml-0.5">(기본)</span>}
                </span>
              </Tooltip>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StatCard({ label, value, color, sub }: { label: string; value: string; color?: 'up' | 'down'; sub?: string }) {
  return (
    <div className="bg-surface-700 rounded-lg p-2.5">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={clsx(
        'text-sm font-semibold mt-0.5 tabular-nums',
        color === 'up' ? 'text-up' : color === 'down' ? 'text-down' : 'text-slate-100'
      )}>{value}</p>
      {sub && (
        <p className={clsx(
          'text-xs tabular-nums mt-0.5',
          color === 'up' ? 'text-up/70' : color === 'down' ? 'text-down/70' : 'text-slate-400'
        )}>{sub}</p>
      )}
    </div>
  )
}
