import { useState, useRef } from 'react'
import { HelpCircle } from 'lucide-react'

interface TooltipProps {
  text: string
  children?: React.ReactNode
  /** 아이콘만 표시할 때 children 없이 사용 */
  iconOnly?: boolean
  className?: string
}

/**
 * 마우스를 올리면 설명 툴팁이 표시됩니다.
 * - children을 감싸거나 (iconOnly=false, 기본)
 * - iconOnly=true 시 ? 아이콘만 렌더링
 */
export default function Tooltip({ text, children, iconOnly = false, className }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const [pos, setPos] = useState<'top' | 'bottom'>('top')
  const ref = useRef<HTMLSpanElement>(null)

  const show = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect()
      setPos(rect.top < 120 ? 'bottom' : 'top')
    }
    setVisible(true)
  }

  const tooltipClass =
    pos === 'top'
      ? 'bottom-full mb-2 left-1/2 -translate-x-1/2'
      : 'top-full mt-2 left-1/2 -translate-x-1/2'

  const arrowClass =
    pos === 'top'
      ? 'top-full left-1/2 -translate-x-1/2 border-t-surface-700'
      : 'bottom-full left-1/2 -translate-x-1/2 border-b-surface-700'

  return (
    <span
      ref={ref}
      className={`relative inline-flex items-center gap-0.5 ${className ?? ''}`}
      onMouseEnter={show}
      onMouseLeave={() => setVisible(false)}
    >
      {iconOnly ? (
        <HelpCircle size={12} className="text-slate-500 hover:text-slate-300 cursor-help flex-shrink-0" />
      ) : (
        <span className="cursor-help">{children}</span>
      )}

      {visible && (
        <span
          className={`absolute z-[999] w-56 text-xs bg-surface-900 border border-surface-700 text-slate-300 rounded-lg px-3 py-2 shadow-2xl pointer-events-none leading-relaxed whitespace-normal ${tooltipClass}`}
        >
          {text}
          <span
            className={`absolute border-4 border-transparent ${arrowClass}`}
          />
        </span>
      )}
    </span>
  )
}
