import { useState } from 'react'
import { Plus, Trash2, Zap, ChevronDown, ChevronUp } from 'lucide-react'
import type { IndicatorCondition } from '../../types'

// ─── 지표 정의 ──────────────────────────────────────────────────────────────

const INDICATORS = [
  {
    value: 'RSI',
    label: 'RSI (과매수/과매도)',
    desc: '14기간 기준. 30 이하 → 과매도(매수기회), 70 이상 → 과매수(매도기회)',
    params: [{ key: 'length', label: '기간', default: 14 }],
  },
  {
    value: 'EMA',
    label: 'EMA (지수이동평균)',
    desc: '최근 가격에 더 높은 가중치. 가격이 EMA 위면 상승추세',
    params: [{ key: 'length', label: '기간', default: 20 }],
  },
  {
    value: 'SMA',
    label: 'SMA (단순이동평균)',
    desc: '일정 기간 평균가격. 가격이 SMA 위면 강세',
    params: [{ key: 'length', label: '기간', default: 20 }],
  },
  {
    value: 'EMA_CROSS',
    label: 'EMA 크로스',
    desc: '빠른 EMA가 느린 EMA를 상향 돌파 → 골든크로스(매수), 하향 돌파 → 데드크로스(매도)',
    params: [
      { key: 'fast', label: '빠른 기간', default: 9 },
      { key: 'slow', label: '느린 기간', default: 21 },
    ],
  },
  {
    value: 'MACD',
    label: 'MACD',
    desc: 'MACD선이 시그널선을 상향 돌파 → 매수, 하향 돌파 → 매도',
    params: [
      { key: 'fast', label: 'Fast', default: 12 },
      { key: 'slow', label: 'Slow', default: 26 },
      { key: 'signal', label: 'Signal', default: 9 },
    ],
  },
  {
    value: 'STOCH',
    label: 'Stochastic (%K)',
    desc: '%K가 20 이하 → 과매도, 80 이상 → 과매수',
    params: [
      { key: 'k', label: '%K', default: 14 },
      { key: 'd', label: '%D', default: 3 },
    ],
  },
  {
    value: 'BB_UPPER',
    label: '볼린저밴드 상단',
    desc: '가격이 상단 밴드 근처 → 과매수(매도기회). 상향 돌파 시 강한 상승 신호',
    params: [
      { key: 'length', label: '기간', default: 20 },
      { key: 'std', label: '표준편차', default: 2 },
    ],
  },
  {
    value: 'BB_LOWER',
    label: '볼린저밴드 하단',
    desc: '가격이 하단 밴드 근처 → 과매도(매수기회). 하향 돌파 시 강한 하락 신호',
    params: [
      { key: 'length', label: '기간', default: 20 },
      { key: 'std', label: '표준편차', default: 2 },
    ],
  },
  {
    value: 'BB_WIDTH',
    label: '볼린저밴드 폭 (%)',
    desc: '밴드 폭이 좁아지면 변동성 수축(큰 움직임 임박), 넓어지면 변동성 확대',
    params: [
      { key: 'length', label: '기간', default: 20 },
      { key: 'std', label: '표준편차', default: 2 },
    ],
  },
]

const OPERATORS = [
  { value: '<', label: '미만 (<)' },
  { value: '>', label: '초과 (>)' },
  { value: '<=', label: '이하 (≤)' },
  { value: '>=', label: '이상 (≥)' },
  { value: 'cross_above', label: '상향 돌파 ↑' },
  { value: 'cross_below', label: '하향 돌파 ↓' },
]

const CROSS_OPERATORS = ['cross_above', 'cross_below']

// ─── 프리셋 ──────────────────────────────────────────────────────────────────

interface Preset {
  label: string
  desc: string
  entry: Omit<IndicatorCondition, 'id'>[]
  exit: Omit<IndicatorCondition, 'id'>[]
}

const PRESETS: Preset[] = [
  {
    label: 'RSI 과매도 반등',
    desc: 'RSI 30 이하 진입 / RSI 70 이상 청산',
    entry: [{ indicator: 'RSI', params: { length: 14 }, operator: '<=', value: 30 }],
    exit: [{ indicator: 'RSI', params: { length: 14 }, operator: '>=', value: 70 }],
  },
  {
    label: 'EMA 골든크로스',
    desc: '단기 EMA(9)가 장기 EMA(21) 상향 돌파 시 진입',
    entry: [{ indicator: 'EMA_CROSS', params: { fast: 9, slow: 21 }, operator: 'cross_above', value: 0 }],
    exit: [{ indicator: 'EMA_CROSS', params: { fast: 9, slow: 21 }, operator: 'cross_below', value: 0 }],
  },
  {
    label: 'MACD 크로스',
    desc: 'MACD 상향 돌파 진입 / 하향 돌파 청산',
    entry: [{ indicator: 'MACD', params: { fast: 12, slow: 26, signal: 9 }, operator: 'cross_above', value: 0 }],
    exit: [{ indicator: 'MACD', params: { fast: 12, slow: 26, signal: 9 }, operator: 'cross_below', value: 0 }],
  },
  {
    label: '볼린저 밴드 반등',
    desc: '하단 밴드 터치 시 진입, 상단 밴드 도달 시 청산',
    entry: [{ indicator: 'BB_LOWER', params: { length: 20, std: 2 }, operator: 'cross_above', value: 0 }],
    exit: [{ indicator: 'BB_UPPER', params: { length: 20, std: 2 }, operator: 'cross_below', value: 0 }],
  },
  {
    label: 'RSI + EMA 복합',
    desc: 'RSI 과매도 + 가격이 EMA 위 → 추세 확인 후 진입',
    entry: [
      { indicator: 'RSI', params: { length: 14 }, operator: '<=', value: 35 },
      { indicator: 'EMA', params: { length: 50 }, operator: '>', value: 0 },
    ],
    exit: [{ indicator: 'RSI', params: { length: 14 }, operator: '>=', value: 65 }],
  },
]

// ─── 타입/유틸 ───────────────────────────────────────────────────────────────

interface Props {
  label: string
  conditions: IndicatorCondition[]
  onChange: (conditions: IndicatorCondition[]) => void
}

let _id = 0
const newId = () => `cond_${++_id}`

// ─── 컴포넌트 ─────────────────────────────────────────────────────────────────

export default function ConditionBuilder({ label, conditions, onChange }: Props) {
  const [showPresets, setShowPresets] = useState(false)
  const [expandedDesc, setExpandedDesc] = useState<string | null>(null)

  const addCondition = () => {
    onChange([
      ...conditions,
      { id: newId(), indicator: 'RSI', params: { length: 14 }, operator: '<', value: 30 },
    ])
  }

  const removeCondition = (id: string) => onChange(conditions.filter((c) => c.id !== id))

  const updateCondition = (id: string, patch: Partial<IndicatorCondition>) => {
    onChange(
      conditions.map((c) => {
        if (c.id !== id) return c
        const updated = { ...c, ...patch }
        if (patch.indicator) {
          const def = INDICATORS.find((i) => i.value === patch.indicator)
          if (def) updated.params = Object.fromEntries(def.params.map((p) => [p.key, p.default]))
        }
        return updated
      })
    )
  }

  const applyPreset = (preset: Preset) => {
    onChange(preset.entry.map(c => ({ ...c, id: newId() })))
    setShowPresets(false)
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-300">{label}</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPresets(!showPresets)}
            className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300"
          >
            <Zap size={13} />
            빠른 설정
            {showPresets ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          <button
            onClick={addCondition}
            className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400"
          >
            <Plus size={14} />
            조건 추가
          </button>
        </div>
      </div>

      {/* 프리셋 목록 */}
      {showPresets && (
        <div className="bg-surface-700 rounded-lg p-3 space-y-1.5 border border-amber-500/20">
          <p className="text-xs text-amber-400 font-medium mb-2">대표 전략 프리셋 (클릭 시 진입 조건 적용)</p>
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              onClick={() => applyPreset(preset)}
              className="w-full text-left bg-surface-600 hover:bg-surface-500 rounded-lg px-3 py-2 transition-colors"
            >
              <p className="text-sm font-medium text-slate-200">{preset.label}</p>
              <p className="text-xs text-slate-400 mt-0.5">{preset.desc}</p>
            </button>
          ))}
        </div>
      )}

      {conditions.length === 0 && (
        <p className="text-xs text-slate-500 italic py-1">
          "빠른 설정"으로 프리셋을 선택하거나 "조건 추가"로 직접 설정하세요.
        </p>
      )}

      {conditions.map((cond) => {
        const indicatorDef = INDICATORS.find((i) => i.value === cond.indicator)
        const isCross = CROSS_OPERATORS.includes(cond.operator)
        const isExpanded = expandedDesc === cond.id

        return (
          <div key={cond.id} className="bg-surface-700 rounded-lg p-3 space-y-2 border border-surface-600">
            {/* 상단: 지표 + 연산자 + 값 + 삭제 */}
            <div className="flex items-center gap-2">
              <select
                value={cond.indicator}
                onChange={(e) => updateCondition(cond.id, { indicator: e.target.value })}
                className="input flex-1 min-w-0"
              >
                {INDICATORS.map((i) => (
                  <option key={i.value} value={i.value}>{i.label}</option>
                ))}
              </select>

              <select
                value={cond.operator}
                onChange={(e) =>
                  updateCondition(cond.id, {
                    operator: e.target.value as IndicatorCondition['operator'],
                  })
                }
                className="input w-36 flex-shrink-0"
              >
                {OPERATORS.map((op) => (
                  <option key={op.value} value={op.value}>{op.label}</option>
                ))}
              </select>

              {!isCross && (
                <input
                  type="number"
                  value={cond.value ?? ''}
                  onChange={(e) => updateCondition(cond.id, { value: parseFloat(e.target.value) })}
                  className="input w-20 flex-shrink-0"
                  placeholder="값"
                />
              )}

              <button
                onClick={() => removeCondition(cond.id)}
                className="text-slate-500 hover:text-down transition-colors flex-shrink-0"
              >
                <Trash2 size={16} />
              </button>
            </div>

            {/* 파라미터 */}
            {indicatorDef && indicatorDef.params.length > 0 && (
              <div className="flex gap-3 flex-wrap items-center">
                <span className="text-xs text-slate-500">파라미터:</span>
                {indicatorDef.params.map((param) => (
                  <div key={param.key} className="flex items-center gap-1.5">
                    <label className="text-xs text-slate-400">{param.label}</label>
                    <input
                      type="number"
                      value={cond.params[param.key] ?? param.default}
                      onChange={(e) =>
                        updateCondition(cond.id, {
                          params: { ...cond.params, [param.key]: parseInt(e.target.value) },
                        })
                      }
                      className="input w-16 text-xs py-1"
                    />
                  </div>
                ))}

                {/* 지표 설명 토글 */}
                {indicatorDef.desc && (
                  <button
                    onClick={() => setExpandedDesc(isExpanded ? null : cond.id)}
                    className="text-xs text-slate-500 hover:text-slate-300 underline underline-offset-2 ml-auto"
                  >
                    {isExpanded ? '설명 닫기' : '지표 설명'}
                  </button>
                )}
              </div>
            )}

            {/* 설명 */}
            {isExpanded && indicatorDef?.desc && (
              <p className="text-xs text-slate-400 bg-surface-600 rounded px-2 py-1.5 leading-relaxed">
                {indicatorDef.desc}
              </p>
            )}
          </div>
        )
      })}

      {conditions.length > 1 && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-px bg-surface-600" />
          <span className="text-xs text-slate-500 font-medium">AND — 위 조건 모두 동시 충족 시 신호</span>
          <div className="flex-1 h-px bg-surface-600" />
        </div>
      )}
    </div>
  )
}
