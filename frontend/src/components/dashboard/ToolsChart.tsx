import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { useTheme } from "@/hooks/useTheme"

import type { ToolData } from "@/types/reports"

interface ToolsChartProps {
  data: ToolData[]
}

const toolLabels: Record<string, string> = {
  crm: "CRM",
  invoice: "Facturas",
  inventory: "Inventario",
  notification: "Notificaciones",
  system: "Sistema",
  api_connector: "API Connector",
  data_keeper: "Data Keeper",
  autopilot: "Autopilot",
  logic_gate: "Logic Gate",
}

export function ToolsChart({ data }: ToolsChartProps) {
  // BUG P1-7: antes se leía `document.documentElement.classList.contains("dark")`
  // durante el render (no reactivo). Ahora useTheme subscribe al ThemeContext.
  const { isDark } = useTheme()
  const textColor = isDark ? "#888" : "#6b7280"
  const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"

  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Sin datos de herramientas
      </div>
    )
  }

  const chartData = data.map((d) => ({
    ...d,
    label: toolLabels[d.tool] || d.tool,
  }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ left: 20, right: 20, top: 5, bottom: 5 }}
        barGap={2}
      >
        <XAxis
          type="number"
          tick={{ fill: textColor, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          allowDecimals={false}
        />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: textColor, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={100}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: isDark ? "#1a1a1a" : "#fff",
            border: `1px solid ${gridColor}`,
            borderRadius: "8px",
            fontSize: "12px",
          }}
          labelStyle={{ color: textColor }}
          // Recharts v3 cambió la firma del formatter: ahora recibe (value, name, item, index, payload).
          // Sin tipar explícito, TS infiere los tipos correctos desde el componente Tooltip.
          formatter={(value) => [String(value), "Ejecuciones"]}
        />
        <Bar
          dataKey="count"
          fill="#6366f1"
          radius={[0, 4, 4, 0]}
          barSize={16}
          label={{
            position: "right",
            fill: textColor,
            fontSize: 10,
            // En label de Bar, formatter recibe el valor y debe retornar ReactNode.
            formatter: (value: unknown) => String(value),
          }}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

export { type ToolData }
