import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import api from '../utils/api'
import { useAuthStore } from '../store/auth'

// FastAPI는 유효성 오류 시 detail이 배열, 비즈니스 오류 시 문자열로 옴
function parseApiError(e: unknown): string {
  const res = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail

  if (!res) return '서버에 연결할 수 없습니다.'

  // 배열 형태: Pydantic 유효성 검사 오류
  if (Array.isArray(res)) {
    return res
      .map((err: { loc?: string[]; msg?: string }) => {
        const field = err.loc?.slice(1).join(' → ') ?? ''
        const msg = translatePydanticMsg(err.msg ?? '')
        return field ? `[${field}] ${msg}` : msg
      })
      .join(' / ')
  }

  // 문자열 형태: 비즈니스 로직 오류
  if (typeof res === 'string') return translateApiMsg(res)

  return '알 수 없는 오류가 발생했습니다.'
}

function translatePydanticMsg(msg: string): string {
  if (msg.includes('valid email')) return '올바른 이메일 형식이 아닙니다.'
  if (msg.includes('at least')) return '비밀번호는 8자 이상이어야 합니다.'
  if (msg.includes('missing')) return '필수 항목입니다.'
  if (msg.includes('too short')) return '너무 짧습니다.'
  return msg
}

function translateApiMsg(msg: string): string {
  if (msg === 'Email already registered') return '이미 사용 중인 이메일입니다.'
  if (msg === 'Username already taken') return '이미 사용 중인 사용자 이름입니다.'
  if (msg === 'Invalid credentials') return '이메일 또는 비밀번호가 올바르지 않습니다.'
  return msg
}

export default function LoginPage() {
  const navigate = useNavigate()
  const { setToken } = useAuthStore()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const loginMutation = useMutation({
    mutationFn: () => api.post('/auth/login', { email, password }),
    onSuccess: (res) => {
      setToken(res.data.access_token)
      navigate('/')
    },
    onError: (e) => setError(parseApiError(e)),
  })

  const registerMutation = useMutation({
    mutationFn: () => api.post('/auth/register', { email, username, password }),
    onSuccess: () => {
      setSuccessMsg('회원가입 완료! 로그인해주세요.')
      setMode('login')
      setError('')
      setPassword('')
    },
    onError: (e) => setError(parseApiError(e)),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccessMsg('')

    if (mode === 'register') {
      if (username.trim().length < 2) {
        setError('사용자 이름은 2자 이상이어야 합니다.')
        return
      }
      if (password.length < 8) {
        setError('비밀번호는 8자 이상이어야 합니다.')
        return
      }
    }

    if (mode === 'login') loginMutation.mutate()
    else registerMutation.mutate()
  }

  const isPending = loginMutation.isPending || registerMutation.isPending

  const switchMode = (m: 'login' | 'register') => {
    setMode(m)
    setError('')
    setSuccessMsg('')
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-100">CoAI</h1>
          <p className="text-slate-400 text-sm mt-1">코인 자동매매 시스템</p>
        </div>

        <div className="card">
          <div className="flex gap-2 mb-5">
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                onClick={() => switchMode(m)}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                  mode === m ? 'bg-brand-500 text-white' : 'bg-surface-700 text-slate-400'
                }`}
              >
                {m === 'login' ? '로그인' : '회원가입'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="email"
              className="input"
              placeholder="이메일"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
            {mode === 'register' && (
              <input
                className="input"
                placeholder="사용자 이름 (2자 이상)"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={2}
              />
            )}
            <input
              type="password"
              className="input"
              placeholder="비밀번호 (8자 이상)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />

            {error && (
              <div className="bg-down/10 border border-down/30 rounded-lg px-3 py-2">
                <p className="text-sm text-down">{error}</p>
              </div>
            )}
            {successMsg && (
              <div className="bg-up/10 border border-up/30 rounded-lg px-3 py-2">
                <p className="text-sm text-up">{successMsg}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={isPending}
              className="btn-primary w-full mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isPending ? '처리 중...' : mode === 'login' ? '로그인' : '회원가입'}
            </button>
          </form>

        </div>
      </div>
    </div>
  )
}
