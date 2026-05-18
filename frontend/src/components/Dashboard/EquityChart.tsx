import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { format } from 'date-fns'

interface Props {
  data: { time: string; value: number }[]
  title?: string
}

export default function EquityChart({ data, title = '자산 곡선' }: Props) {
  const values = data.map((d) => d.value)
  const min = values.length > 0 ? Math.min(...values) * 0.99 : 0
  const max = values.length > 0 ? Math.max(...values) * 1.01 : 100

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="equity-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="time"
            tickFormatter={(v) => {
              try {
                return format(new Date(v), 'MM/dd')
              } catch {
                return v
              }
            }}
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            axisLine={{ stroke: '#334155' }}
            tickLine={false}
          />
          <YAxis
            domain={[min, max]}
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            axisLine={{ stroke: '#334155' }}
            tickLine={false}
            tickFormatter={(v) => `$${v.toLocaleString()}`}
            width={70}
          />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            labelStyle={{ color: '#94a3b8', fontSize: 11 }}
            itemStyle={{ color: '#0ea5e9' }}
            formatter={(v: number) => [`$${v.toLocaleString()}`, '자산']}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#0ea5e9"
            strokeWidth={2}
            fill="url(#equity-gradient)"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
