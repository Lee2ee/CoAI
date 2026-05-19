import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Wifi, WifiOff, KeyRound, RefreshCw, Copy, ChevronDown } from 'lucide-react'
import api from '../utils/api'
import Modal from '../components/common/Modal'
import ConfirmModal from '../components/common/ConfirmModal'
import ExchangeAccountForm from '../components/Exchange/ExchangeAccountForm'
import type { ExchangeAccount } from '../types'

// 거래소별 표시 정보
const EXCHANGE_META: Record<string, { name: string; quote: string; color: string; depositNote: string }> = {
  upbit:   { name: 'Upbit',   quote: 'KRW',  color: 'text-blue-400',   depositNote: 'KRW 입금은 업비트 앱 → 입출금 → 원화 입금에서 계좌이체로 진행하세요.' },
  binance: { name: 'Binance', quote: 'USDT', color: 'text-yellow-400', depositNote: 'USDT 또는 코인을 Binance 앱/웹에서 입금하세요.' },
  bybit:   { name: 'Bybit',   quote: 'USDT', color: 'text-orange-400', depositNote: 'USDT 또는 코인을 Bybit 앱/웹에서 입금하세요.' },
}

const getExchangeMeta = (exchange: string) =>
  EXCHANGE_META[exchange] ?? { name: exchange, quote: 'USDT', color: 'text-slate-300', depositNote: '거래소 앱을 통해 입금하세요.' }

interface Balance {
  currency: string
  free: number
  used: number
  total: number
}

interface DepositAddress {
  currency: string
  address: string | null
  tag: string | null
}

function BalancePanel({ accountId, quote }: { accountId: number; quote: string }) {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['balance', accountId],
    queryFn: async () => {
      const res = await api.get(`/exchange-accounts/${accountId}/balance`)
      return res.data.balances as Balance[]
    },
    staleTime: 30_000,
  })

  const errMsg = isError
    ? ((error as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? '잔고 조회 실패')
    : null

  const formatAmount = (currency: string, amount: number) => {
    if (currency === 'KRW') return amount.toLocaleString('ko-KR') + ' ₩'
    if (currency === 'USDT') return '$' + amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return amount.toFixed(8).replace(/\.?0+$/, '')
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">잔고</span>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-40"
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-slate-500">불러오는 중...</p>
      ) : errMsg ? (
        <p className="text-xs text-down">{errMsg}</p>
      ) : !data || data.length === 0 ? (
        <p className="text-xs text-slate-500">보유 자산 없음</p>
      ) : (
        <div className="space-y-1">
          {/* quote 통화 맨 앞 */}
          {[...data].sort((a, b) => (a.currency === quote ? -1 : b.currency === quote ? 1 : 0)).map((b) => (
            <div key={b.currency} className="flex items-center justify-between text-sm">
              <span className="text-slate-300 font-medium w-16">{b.currency}</span>
              <span className="text-slate-100 font-mono">{formatAmount(b.currency, b.free)}</span>
              {b.used > 0 && (
                <span className="text-xs text-slate-500 ml-2">주문중 {b.used}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DepositPanel({ accountId, exchange }: { accountId: number; exchange: string }) {
  const meta = getExchangeMeta(exchange)
  const [open, setOpen] = useState(false)
  const [currency, setCurrency] = useState('BTC')
  const [fetched, setFetched] = useState<DepositAddress | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  const CRYPTOS = exchange === 'upbit' ? ['BTC', 'ETH', 'XRP', 'USDT'] : ['BTC', 'ETH', 'USDT', 'XRP']

  const fetchAddress = async () => {
    setLoading(true)
    setErr('')
    setFetched(null)
    try {
      const res = await api.get(`/exchange-accounts/${accountId}/deposit-address/${currency}`)
      setFetched(res.data)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setErr(detail ?? '입금 주소 조회 실패')
    } finally {
      setLoading(false)
    }
  }

  const copyAddress = () => {
    if (!fetched?.address) return
    navigator.clipboard.writeText(fetched.address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="border-t border-surface-700 pt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors w-full"
      >
        <ChevronDown size={13} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        암호화폐 입금
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {/* 거래소별 입금 안내 */}
          <div className="bg-surface-700 rounded-lg px-3 py-2 text-xs text-slate-400">
            {meta.depositNote}
          </div>

          {/* 코인 선택 */}
          <div className="flex gap-2">
            {CRYPTOS.map((c) => (
              <button
                key={c}
                onClick={() => { setCurrency(c); setFetched(null); setErr('') }}
                className={`px-3 py-1 rounded text-xs font-medium border transition-colors ${
                  currency === c
                    ? 'bg-brand-500/20 border-brand-500 text-brand-400'
                    : 'bg-surface-700 border-surface-600 text-slate-400 hover:border-surface-500'
                }`}
              >
                {c}
              </button>
            ))}
          </div>

          <button
            onClick={fetchAddress}
            disabled={loading}
            className="btn-ghost w-full text-sm disabled:opacity-50"
          >
            {loading ? '조회 중...' : `${currency} 입금 주소 조회`}
          </button>

          {err && <p className="text-xs text-down">{err}</p>}

          {fetched?.address && (
            <div className="space-y-2">
              <div className="bg-surface-700 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">{fetched.currency} 입금 주소</p>
                <div className="flex items-center gap-2">
                  <p className="text-xs font-mono text-slate-200 break-all flex-1">{fetched.address}</p>
                  <button onClick={copyAddress} className="text-slate-400 hover:text-slate-200 flex-shrink-0">
                    <Copy size={14} />
                  </button>
                </div>
                {copied && <p className="text-xs text-up mt-1">복사됨</p>}
              </div>
              {fetched.tag && (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
                  <p className="text-xs text-amber-400">태그(메모): {fetched.tag}</p>
                  <p className="text-xs text-slate-400 mt-0.5">태그를 반드시 함께 입력하세요.</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ExchangePage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [testResults, setTestResults] = useState<Record<number, { ok: boolean; msg: string }>>({})
  const [testing, setTesting] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ExchangeAccount | null>(null)

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['exchange-accounts'],
    queryFn: async () => {
      const res = await api.get('/exchange-accounts/')
      return res.data as ExchangeAccount[]
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/exchange-accounts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exchange-accounts'] }),
  })

  const testConnection = async (account: ExchangeAccount) => {
    setTesting(account.id)
    const meta = getExchangeMeta(account.exchange)
    try {
      const res = await api.get(`/exchange-accounts/${account.id}/test`)
      const price = res.data.btc_price
      const quote = res.data.quote ?? (meta.quote === 'KRW' ? 'KRW' : 'USDT')
      const priceStr = quote === 'KRW'
        ? price?.toLocaleString('ko-KR') + ' ₩'
        : price?.toLocaleString('en-US', { minimumFractionDigits: 1 }) + ' USDT'
      setTestResults((prev) => ({
        ...prev,
        [account.id]: res.data.ok
          ? { ok: true, msg: `연결 성공 · BTC ${priceStr}` }
          : { ok: false, msg: res.data.error || '연결 실패' },
      }))
    } catch {
      setTestResults((prev) => ({
        ...prev,
        [account.id]: { ok: false, msg: '서버 오류' },
      }))
    } finally {
      setTesting(null)
    }
  }

  return (
    <div className="space-y-4">
      {deleteTarget && (
        <ConfirmModal
          message={`'${deleteTarget.label}' 계정을 삭제하시겠습니까?`}
          detail="삭제 후에는 복구할 수 없으며, 연결된 자동매매도 중단됩니다."
          confirmText="삭제"
          variant="danger"
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onClose={() => setDeleteTarget(null)}
        />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100">거래소 계정</h1>
          <p className="text-sm text-slate-400 mt-0.5">API 키는 AES-256 암호화하여 저장됩니다.</p>
        </div>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-1.5">
          <Plus size={16} />
          계정 추가
        </button>
      </div>

      {isLoading ? (
        <div className="card text-slate-400 text-sm">불러오는 중...</div>
      ) : accounts.length === 0 ? (
        <div className="card text-center py-12">
          <KeyRound size={40} className="mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400">등록된 거래소 계정이 없습니다.</p>
          <p className="text-slate-500 text-sm mt-1">계정 추가 버튼을 눌러 거래소 API 키를 등록하세요.</p>
          <button onClick={() => setShowForm(true)} className="btn-primary mt-4">
            계정 추가
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {accounts.map((account) => {
            const meta = getExchangeMeta(account.exchange)
            const testResult = testResults[account.id]
            const isTesting = testing === account.id

            return (
              <div key={account.id} className="card space-y-3">
                {/* 헤더 */}
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`font-semibold text-base ${meta.color}`}>{meta.name}</span>
                      <span className="text-xs text-slate-500 font-mono">{meta.quote}</span>
                      <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                        account.is_paper
                          ? 'bg-amber-500/20 text-amber-400'
                          : 'bg-down/20 text-down'
                      }`}>
                        {account.is_paper ? '모의' : '실거래'}
                      </span>
                      {account.is_active && (
                        <span className="text-xs bg-up/20 text-up px-2 py-0.5 rounded">활성</span>
                      )}
                    </div>
                    <p className="text-sm text-slate-300 mt-0.5">{account.label}</p>
                  </div>
                  <button
                    onClick={() => setDeleteTarget(account)}
                    className="text-slate-500 hover:text-down transition-colors p-1"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                {/* API 키 표시 */}
                <div className="bg-surface-700 rounded-lg px-3 py-2">
                  <p className="text-xs text-slate-400 mb-0.5">Access Key</p>
                  <p className="text-sm font-mono text-slate-200">{account.api_key_masked}</p>
                </div>

                {/* 잔고 (실거래만) */}
                {!account.is_paper && <BalancePanel accountId={account.id} quote={meta.quote} />}

                {/* 연결 테스트 결과 */}
                {testResult && (
                  <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${
                    testResult.ok ? 'bg-up/10 text-up' : 'bg-down/10 text-down'
                  }`}>
                    {testResult.ok ? <Wifi size={14} /> : <WifiOff size={14} />}
                    {testResult.msg}
                  </div>
                )}

                {/* 연결 테스트 버튼 */}
                <button
                  onClick={() => testConnection(account)}
                  disabled={isTesting}
                  className="btn-ghost w-full flex items-center justify-center gap-2 text-sm disabled:opacity-50"
                >
                  <Wifi size={14} />
                  {isTesting ? '테스트 중...' : '연결 테스트'}
                </button>

                {/* 입금 (실거래만) */}
                {!account.is_paper && <DepositPanel accountId={account.id} exchange={account.exchange} />}
              </div>
            )
          })}
        </div>
      )}

      {showForm && (
        <Modal title="거래소 계정 추가" onClose={() => setShowForm(false)}>
          <ExchangeAccountForm onClose={() => setShowForm(false)} />
        </Modal>
      )}
    </div>
  )
}
