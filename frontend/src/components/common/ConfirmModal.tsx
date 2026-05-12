import { AlertTriangle, Info, X } from 'lucide-react'

interface Props {
  message: string
  detail?: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'info'
  onConfirm: () => void
  onClose: () => void
}

const VARIANT = {
  danger: {
    icon: <AlertTriangle size={20} className="text-down flex-shrink-0 mt-0.5" />,
    bg: 'bg-down/10 border-down/30',
    btn: 'bg-down/20 border border-down/40 text-down hover:bg-down/30',
  },
  warning: {
    icon: <AlertTriangle size={20} className="text-amber-400 flex-shrink-0 mt-0.5" />,
    bg: 'bg-amber-500/10 border-amber-500/30',
    btn: 'bg-amber-500/20 border border-amber-500/40 text-amber-400 hover:bg-amber-500/30',
  },
  info: {
    icon: <Info size={20} className="text-brand-400 flex-shrink-0 mt-0.5" />,
    bg: 'bg-brand-500/10 border-brand-500/30',
    btn: 'bg-brand-500/20 border border-brand-500/40 text-brand-400 hover:bg-brand-500/30',
  },
}

export default function ConfirmModal({
  message,
  detail,
  confirmText = '확인',
  cancelText = '취소',
  variant = 'danger',
  onConfirm,
  onClose,
}: Props) {
  const v = VARIANT[variant]

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="bg-surface-800 border border-surface-700 rounded-xl shadow-2xl w-full max-w-sm"
        onClick={e => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-surface-700">
          <h3 className="font-semibold text-slate-100">확인</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* 본문 */}
        <div className="px-5 py-5 space-y-4">
          <div className={`flex gap-3 border rounded-lg px-4 py-3 ${v.bg}`}>
            {v.icon}
            <div className="space-y-1">
              <p className="text-sm text-slate-100 leading-relaxed whitespace-pre-line">{message}</p>
              {detail && <p className="text-xs text-slate-400 leading-relaxed whitespace-pre-line">{detail}</p>}
            </div>
          </div>

          {/* 버튼 */}
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="btn-ghost flex-1 text-sm"
            >
              {cancelText}
            </button>
            <button
              onClick={() => { onConfirm(); onClose() }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${v.btn}`}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
