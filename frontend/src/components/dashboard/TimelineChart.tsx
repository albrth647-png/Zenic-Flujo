import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { useTheme } from "@/hooks/useTheme"

import type { TimelineData } from "@/types/reports"

interface TimelineChartProps {
  data: TimelineData[]
}

export function TimelineChart({ data }: TimelineChartProps) {
  // BUG P1-7: antes se leía `document.documentElement.classList.contains("dark")`
  // durante el render (no reactivo). Ahora useTheme subscribe al ThemeContext.
  const { isDark } = useTheme()
  const textColor = isDark ? "#888" : "#6b7280"
  const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"

  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Sin datos suficientes
      </div>
    )
  }

  // Format day labels to DD/MM
  const chartData = data.map((d) => {
    const parts = d.day.split("-")
    return {
      ...d,
      dayLabel: `${parts[2]}/${parts[1]}`,
    }
  })

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} barGap={2} barCategoryGap="20%">
        <XAxis
          dataKey="dayLabel"
          tick={{ fill: textColor, fontSize: 10 }}
          axisLine={{ stroke: gridColor }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: textColor, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: isDark ? "#1a1a1a" : "#fff",
            border: `1px solid ${gridColor}`,
            borderRadius: "8px",
            fontSize: "12px",
          }}
          labelStyle={{ color: textColor }}
        />
        <Legend
          wrapperStyle={{ fontSize: "11px", color: textColor }}
        />
        <Bar
          dataKey="completed"
          name="✅ Completadas"
          fill="#22c55e"
          radius={[4, 4, 0, 0]}
          stackId="a"
        />
        <Bar
          dataKey="failed"
          name="❌ Fallidas"
          fill="#ef4444"
          radius={[4, 4, 0, 0]}
          stackId="a"
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

export { type TimelineData }
