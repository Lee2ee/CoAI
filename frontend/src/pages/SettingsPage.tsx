import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bot, CheckCircle, XCircle, Loader2, Eye, EyeOff,
  ExternalLink, ChevronDown, Save, Zap, Cpu,
} from 'lucide-react'
import { useSettingsStore } from '../store/settings'
import api from '../utils/api'
import type { AutoBotStatus } from '../types'

// ── 타입 ──────────────────────────────────────────────────────────────────

interface ProviderMeta {
  label: string
  desc: string
  tier: 'free' | 'paid'
  needs_key: boolean
  needs_url: boolean
  models: string[]
  key_url: string | null
}

interface AIConfig {
  provider: string
  model: string
  api_key_masked: string
  api_key_set: boolean
  ollama_url: string
  providers: Record<string, ProviderMeta>
}

// ── 프로바이더 아이콘 (텍스트) ────────────────────────────────────────────

const PROVIDER_ICON: Record<string, string> = {
  ollama:    '🦙',
  groq:      '⚡',
  anthropic: '◆',
  openai:    '✦',
}

// ── 토글 컴포넌트 ─────────────────────────────────────────────────────────

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-12 flex-shrink-0 rounded-full transition-colors duration-200 ${
        checked ? 'bg-brand-500' : 'bg-surface-600'
      }`}
    >
      <span
        className={`absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? 'translate-x-6' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { aiEnabled, setAiEnabled } = useSettingsStore()
  const queryClient = useQueryClient()

  // 현재 설정 로드
  const { data: cfg, isLoading } = useQuery<AIConfig>({
    queryKey: ['ai-config'],
    queryFn: async () => (await api.get('/ai-config')).data,
  })

  // 봇 설정 로드 (AI 기능 토글용)
  const { data: botStatus } = useQuery<AutoBotStatus>({
    queryKey: ['auto-bot-status'],
    queryFn: async () => (await api.get('/auto-bot/status')).data,
    refetchInterval: false,
  })

  const botFeatureMut = useMutation({
    mutationFn: (patch: object) => api.patch('/auto-bot/settings', patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['auto-bot-status'] }),
  })

  // 폼 상태
  const [provider, setProvider] = useState('')
  const [model, setModel]       = useState('')
  const [apiKey, setApiKey]     = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [showKey, setShowKey]   = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  // cfg 로드 후 폼 초기화
  useEffect(() => {
    if (cfg) {
      setProvider(cfg.provider)
      setModel(cfg.model)
      setOllamaUrl(cfg.ollama_url)
    }
  }, [cfg])

  // provider 변경 시 모델 자동 선택 (첫 번째 모델)
  useEffect(() => {
    if (cfg && provider && cfg.providers[provider]) {
      const models = cfg.providers[provider].models
      if (!models.includes(model)) {
        setModel(models[0])
      }
    }
  }, [provider])

  // 저장
  const saveMutation = useMutation({
    mutationFn: () =>
      api.post('/ai-config', {
        provider,
        model,
        api_key: apiKey || undefined,
        ollama_url: ollamaUrl,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-config'] })
      setApiKey('')
      setTestResult(null)
    },
  })

  // 연결 테스트
  const testMutation = useMutation({
    mutationFn: async () => {
      // 저장 먼저 (임시 키 반영)
      if (apiKey) {
        await api.post('/ai-config', {
          provider,
          model,
          api_key: apiKey,
          ollama_url: ollamaUrl,
        })
        queryClient.invalidateQueries({ queryKey: ['ai-config'] })
      }
      return (await api.post('/ai-config/test')).data
    },
    onSuccess: (data) => {
      setTestResult(data)
      if (apiKey) setApiKey('')
    },
  })

  if (isLoading || !cfg) {
    return (
      <div className="flex items-center gap-2 text-slate-400">
        <Loader2 size={16} className="animate-spin" /> 설정 불러오는 중...
      </div>
    )
  }

  const providers = cfg.providers
  const freeProviders  = Object.entries(providers).filter(([, m]) => m.tier === 'free')
  const paidProviders  = Object.entries(providers).filter(([, m]) => m.tier === 'paid')
  const currentMeta    = providers[provider]
  const currentModels  = currentMeta?.models ?? []
  const isDirty        = provider !== cfg.provider || model !== cfg.model || !!apiKey

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-100">설정</h1>
        <p className="text-sm text-slate-400 mt-0.5">시스템 환경설정</p>
      </div>

      {/* ── AI 기능 개별 설정 ────────────────────────────────────────────── */}
      {aiEnabled && botStatus && (
        <div className="card space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-surface-700">
            <Cpu size={16} className="text-brand-400" />
            <h2 className="font-semibold text-slate-100">AI 기능 설정</h2>
          </div>

          {(
            [
              {
                key: 'ai_entry_validation',
                label: '진입 확인',
                desc: 'AI가 진입 신호의 신뢰도를 검증합니다. 신뢰도가 낮으면 진입을 차단합니다.',
              },
              {
                key: 'ai_regime_detection',
                label: '시장 국면 감지',
                desc: 'BTC 흐름을 분석해 추세장·횡보장을 판단하고, 매매 스타일을 자동으로 전환합니다.',
              },
              {
                key: 'ai_loss_analysis',
                label: '연속 손절 분석',
                desc: '손절이 3회 연속 발생하면 원인을 분석하고 손절/최소점수 설정을 자동으로 조정합니다.',
              },
              {
                key: 'ai_exit_assist',
                label: '청산 타이밍 보조',
                desc: '이익 중인 포지션에서 추세 반전 신호를 감지하면 조기 청산 또는 손절선 상향을 수행합니다.',
              },
            ] as const
          ).map(({ key, label, desc }) => (
            <div key={key} className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm text-slate-200">{label}</p>
                <p className="text-xs text-slate-400 mt-0.5">{desc}</p>
              </div>
              <Toggle
                checked={botStatus.settings[key] ?? true}
                onChange={v => botFeatureMut.mutate({ [key]: v })}
              />
            </div>
          ))}

          {/* 현재 국면 상태 */}
          {botStatus.ai_available && botStatus.ai_regime && (
            <div className="bg-surface-700 rounded-lg px-3 py-2 text-xs space-y-1">
              <p className="text-slate-400 font-medium">현재 감지된 시장 국면</p>
              <div className="flex flex-wrap gap-3">
                <span className="text-slate-300">
                  국면: <b className="text-brand-300">{
                    botStatus.ai_regime.regime === 'trending' ? '추세장' :
                    botStatus.ai_regime.regime === 'ranging' ? '횡보장' :
                    botStatus.ai_regime.regime === 'volatile' ? '급등락' : botStatus.ai_regime.regime
                  }</b>
                </span>
                <span className="text-slate-300">
                  추천 스타일: <b className="text-brand-300">{botStatus.ai_regime.style}</b>
                </span>
              </div>
              <p className="text-slate-500">{botStatus.ai_regime.reason}</p>
            </div>
          )}
        </div>
      )}

      {/* ── AI 사용 여부 ───────────────────────────────────────────────── */}
      <div className="card space-y-5">
        <div className="flex items-center gap-2 pb-3 border-b border-surface-700">
          <Bot size={16} className="text-brand-400" />
          <h2 className="font-semibold text-slate-100">AI 설정</h2>
        </div>

        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-slate-200">AI 자동 전략 사용</p>
            <p className="text-xs text-slate-400 mt-0.5">
              활성화 시 AI 전략 자동 생성 기능을 사용합니다.
            </p>
          </div>
          <Toggle checked={aiEnabled} onChange={setAiEnabled} />
        </div>

        {/* ── 프로바이더 선택 ─────────────────────────────────────────── */}
        <div className="space-y-3">
          {/* 무료 */}
          <div className="space-y-1.5">
            <p className="text-xs text-slate-400 font-medium flex items-center gap-1">
              <span className="text-up">●</span> 무료
            </p>
            <div className="grid grid-cols-2 gap-2">
              {freeProviders.map(([key, meta]) => (
                <ProviderCard
                  key={key}
                  id={key}
                  meta={meta}
                  selected={provider === key}
                  onSelect={() => setProvider(key)}
                />
              ))}
            </div>
          </div>

          {/* 유료 */}
          <div className="space-y-1.5">
            <p className="text-xs text-slate-400 font-medium flex items-center gap-1">
              <span className="text-brand-400">●</span> 유료
            </p>
            <div className="grid grid-cols-3 gap-2">
              {paidProviders.map(([key, meta]) => (
                <ProviderCard
                  key={key}
                  id={key}
                  meta={meta}
                  selected={provider === key}
                  onSelect={() => setProvider(key)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* ── 선택된 프로바이더 상세 설정 ─────────────────────────────── */}
        {currentMeta && (
          <div className="bg-surface-700 rounded-lg p-4 space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-lg">{PROVIDER_ICON[provider] ?? '🤖'}</span>
              <div>
                <p className="text-sm font-medium text-slate-100">{currentMeta.label}</p>
                <p className="text-xs text-slate-400">{currentMeta.desc}</p>
              </div>
              {currentMeta.key_url && (
                <a
                  href={currentMeta.key_url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto flex items-center gap-1 text-xs text-brand-400 hover:text-brand-300"
                >
                  API 키 발급 <ExternalLink size={11} />
                </a>
              )}
            </div>

            {/* 모델 선택 */}
            <div className="space-y-1">
              <label className="text-xs text-slate-400">모델</label>
              <div className="relative">
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full appearance-none bg-surface-600 text-slate-100 text-sm rounded px-3 py-2 pr-8 border border-surface-500 focus:outline-none focus:border-brand-500"
                >
                  {currentModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-2.5 top-2.5 text-slate-400 pointer-events-none" />
              </div>
            </div>

            {/* Ollama URL */}
            {currentMeta.needs_url && (
              <div className="space-y-1">
                <label className="text-xs text-slate-400">Ollama 서버 주소</label>
                <input
                  type="text"
                  value={ollamaUrl}
                  onChange={(e) => setOllamaUrl(e.target.value)}
                  className="w-full bg-surface-600 text-slate-100 text-sm rounded px-3 py-2 border border-surface-500 focus:outline-none focus:border-brand-500 font-mono"
                  placeholder="http://localhost:11434"
                />
              </div>
            )}

            {/* API 키 입력 */}
            {currentMeta.needs_key && (
              <div className="space-y-1">
                <label className="text-xs text-slate-400">
                  API 키
                  {cfg.api_key_set && provider === cfg.provider && (
                    <span className="ml-2 text-up">● 설정됨 ({cfg.api_key_masked})</span>
                  )}
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full bg-surface-600 text-slate-100 text-sm rounded px-3 py-2 pr-10 border border-surface-500 focus:outline-none focus:border-brand-500 font-mono"
                    placeholder={
                      cfg.api_key_set && provider === cfg.provider
                        ? '변경하려면 새 키를 입력하세요'
                        : 'API 키를 입력하세요'
                    }
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-200"
                  >
                    {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            )}

            {/* 연결 테스트 결과 */}
            {testResult && (
              <div className={`flex items-center gap-2 text-xs p-2 rounded ${
                testResult.ok
                  ? 'bg-up/10 text-up'
                  : 'bg-down/10 text-down'
              }`}>
                {testResult.ok
                  ? <CheckCircle size={13} />
                  : <XCircle size={13} />}
                {testResult.message}
              </div>
            )}

            {/* 버튼 */}
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => testMutation.mutate()}
                disabled={testMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-surface-600 hover:bg-surface-500 text-slate-200 disabled:opacity-50"
              >
                {testMutation.isPending
                  ? <Loader2 size={13} className="animate-spin" />
                  : <Zap size={13} />}
                연결 테스트
              </button>

              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || !isDirty}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-brand-600 hover:bg-brand-500 text-white disabled:opacity-40"
              >
                {saveMutation.isPending
                  ? <Loader2 size={13} className="animate-spin" />
                  : <Save size={13} />}
                저장
              </button>

              {saveMutation.isSuccess && !isDirty && (
                <span className="flex items-center gap-1 text-xs text-up">
                  <CheckCircle size={12} /> 저장됨
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── 프로바이더 카드 ────────────────────────────────────────────────────────

function ProviderCard({
  id, meta, selected, onSelect,
}: {
  id: string
  meta: ProviderMeta
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-left transition-colors ${
        selected
          ? 'border-brand-500 bg-brand-500/10 text-slate-100'
          : 'border-surface-600 bg-surface-700 text-slate-400 hover:border-surface-500 hover:text-slate-300'
      }`}
    >
      <span className="text-base">{PROVIDER_ICON[id] ?? '🤖'}</span>
      <div className="min-w-0">
        <p className="text-xs font-medium truncate">{meta.label}</p>
        <p className="text-xs opacity-60 truncate">
          {meta.tier === 'free' ? '무료' : '유료'}
        </p>
      </div>
      {selected && <CheckCircle size={13} className="ml-auto flex-shrink-0 text-brand-400" />}
    </button>
  )
}
