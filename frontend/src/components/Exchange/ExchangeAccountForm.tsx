import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, AlertTriangle } from 'lucide-react'
import api from '../../utils/api'

type ExchangeId = 'upbit' | 'binance' | 'bybit'

interface ExchangeCfg {
  displayName: string
  quote: string
  fee: string
  apiKeyLabel: string
  apiSecretLabel: string
  apiKeyPlaceholder: string
  apiSecretPlaceholder: string
  defaultLabel: (isPaper: boolean) => string
  securityNote: string
}

const EXCHANGE_CONFIG: Record<ExchangeId, ExchangeCfg> = {
  upbit: {
    displayName: 'Upbit (업비트)',
    quote: 'KRW',
    fee: '0.05%',
    apiKeyLabel: 'Access Key',
    apiSecretLabel: 'Secret Key',
    apiKeyPlaceholder: '업비트 Access Key',
    apiSecretPlaceholder: '업비트 Secret Key',
    defaultLabel: (isPaper) => `업비트 ${isPaper ? '(모의)' : '(실거래)'}`,
    securityNote:
      'API 키는 AES-256 암호화하여 저장됩니다. 업비트에서 출금 권한을 제외한 자산조회·거래 권한만 부여하세요.',
  },
  binance: {
    displayName: 'Binance (바이낸스)',
    quote: 'USDT',
    fee: '0.1%',
    apiKeyLabel: 'API Key',
    apiSecretLabel: 'Secret Key',
    apiKeyPlaceholder: 'Binance API Key',
    apiSecretPlaceholder: 'Binance Secret Key',
    defaultLabel: (isPaper) => `바이낸스 ${isPaper ? '(모의)' : '(실거래)'}`,
    securityNote:
      'API 키는 AES-256 암호화하여 저장됩니다. Binance에서 IP 화이트리스트를 설정하고 출금 권한을 제외하세요.',
  },
  bybit: {
    displayName: 'Bybit (바이비트)',
    quote: 'USDT',
    fee: '0.1%',
    apiKeyLabel: 'API Key',
    apiSecretLabel: 'API Secret',
    apiKeyPlaceholder: 'Bybit API Key',
    apiSecretPlaceholder: 'Bybit API Secret',
    defaultLabel: (isPaper) => `바이비트 ${isPaper ? '(모의)' : '(실거래)'}`,
    securityNote:
      'API 키는 AES-256 암호화하여 저장됩니다. Bybit에서 IP 화이트리스트를 설정하고 출금 권한을 제외하세요.',
  },
}

interface Props {
  onClose: () => void
}

export default function ExchangeAccountForm({ onClose }: Props) {
  const qc = useQueryClient()
  const [exchange, setExchange] = useState<ExchangeId>('upbit')
  const [label, setLabel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [isPaper, setIsPaper] = useState(true)
  const [showKey, setShowKey] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [error, setError] = useState('')

  const cfg = EXCHANGE_CONFIG[exchange]

  const handleExchangeChange = (ex: ExchangeId) => {
    setExchange(ex)
    setApiKey('')
    setApiSecret('')
    setError('')
  }

  const mutation = useMutation({
    mutationFn: () =>
      api.post('/exchange-accounts/', {
        exchange,
        label: label.trim() || cfg.defaultLabel(isPaper),
        api_key: apiKey,
        api_secret: apiSecret,
        is_paper: isPaper,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['exchange-accounts'] })
      onClose()
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setError(detail || '저장에 실패했습니다.')
    },
  })

  const handleSubmit = () => {
    setError('')
    if (!apiKey.trim() || !apiSecret.trim()) {
      setError('API 키와 시크릿을 모두 입력해주세요.')
      return
    }
    mutation.mutate()
  }

  return (
    <div className="space-y-4">
      {/* 거래소 선택 */}
      <div>
        <label className="text-xs text-slate-400 mb-2 block">거래소</label>
        <div className="grid grid-cols-3 gap-2">
          {(Object.keys(EXCHANGE_CONFIG) as ExchangeId[]).map((ex) => (
            <button
              key={ex}
              onClick={() => handleExchangeChange(ex)}
              className={`py-2 rounded-lg text-sm font-medium border transition-colors ${
                exchange === ex
                  ? 'bg-brand-500/20 border-brand-500 text-brand-400'
                  : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
              }`}
            >
              {ex === 'upbit' ? 'Upbit' : ex === 'binance' ? 'Binance' : 'Bybit'}
            </button>
          ))}
        </div>

        {/* 거래소 정보 */}
        <div className="mt-2 bg-surface-700 rounded-lg px-3 py-2 flex justify-between text-xs">
          <span className="text-slate-400">
            기준 통화: <span className="text-slate-200 font-medium">{cfg.quote}</span>
          </span>
          <span className="text-slate-400">
            수수료: <span className="text-slate-200 font-medium">{cfg.fee}</span>
          </span>
        </div>
      </div>

      {/* 계정 이름 */}
      <div>
        <label className="text-xs text-slate-400 mb-1 block">계정 이름 (선택)</label>
        <input
          className="input"
          placeholder={cfg.defaultLabel(isPaper)}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </div>

      {/* API Key */}
      <div>
        <label className="text-xs text-slate-400 mb-1 block">{cfg.apiKeyLabel}</label>
        <div className="relative">
          <input
            type={showKey ? 'text' : 'password'}
            className="input pr-10"
            placeholder={cfg.apiKeyPlaceholder}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
          >
            {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      </div>

      {/* API Secret */}
      <div>
        <label className="text-xs text-slate-400 mb-1 block">{cfg.apiSecretLabel}</label>
        <div className="relative">
          <input
            type={showSecret ? 'text' : 'password'}
            className="input pr-10"
            placeholder={cfg.apiSecretPlaceholder}
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => setShowSecret(!showSecret)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
          >
            {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      </div>

      {/* 거래 모드 */}
      <div>
        <label className="text-xs text-slate-400 mb-2 block">거래 모드</label>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setIsPaper(true)}
            className={`py-2 rounded-lg text-sm font-medium border transition-colors ${
              isPaper
                ? 'bg-amber-500/20 border-amber-500 text-amber-400'
                : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
            }`}
          >
            모의 거래
          </button>
          <button
            onClick={() => setIsPaper(false)}
            className={`py-2 rounded-lg text-sm font-medium border transition-colors ${
              !isPaper
                ? 'bg-down/20 border-down text-down'
                : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
            }`}
          >
            실거래
          </button>
        </div>
      </div>

      {/* 보안 안내 */}
      <div className="bg-brand-500/10 border border-brand-500/30 rounded-lg p-3 flex gap-2">
        <AlertTriangle size={15} className="text-brand-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-slate-300">{cfg.securityNote}</p>
      </div>

      {error && (
        <div className="bg-down/10 border border-down/30 rounded-lg px-3 py-2">
          <p className="text-sm text-down">{error}</p>
        </div>
      )}

      <div className="flex gap-3 pt-1">
        <button onClick={onClose} className="btn-ghost flex-1">
          취소
        </button>
        <button
          onClick={handleSubmit}
          disabled={mutation.isPending}
          className="btn-primary flex-1 disabled:opacity-50"
        >
          {mutation.isPending ? '저장 중...' : '저장'}
        </button>
      </div>
    </div>
  )
}
