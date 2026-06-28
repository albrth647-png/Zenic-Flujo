import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { useTheme } from "@/hooks/useTheme"

interface SuccessChartProps {
  completed: number
  failed: number
}

export function SuccessChart({ completed, failed }: SuccessChartProps) {
  // BUG P1-7: antes se leía `document.documentElement.classList.contains("dark")`
  // durante el render, lo que (a) no es reactivo y (b) hace que el chart no se
  // actualice al cambiar el tema. Ahora se usa el hook useTheme que subscribe
  // al ThemeContext, forzando re-render cuando el tema cambia.
  const { isDark } = useTheme()
  const textColor = isDark ? "#888" : "#6b7280"
  const total = completed + failed

  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
        Sin datos
      </div>
    )
  }

  const data = [
    { name: "Completadas", value: completed, color: "#22c55e" },
    ...(failed > 0 ? [{ name: "Fallidas", value: failed, color: "#ef4444" }] : []),
  ]

  const successRate = Math.round((completed / total) * 100)

  return (
    <div className="relative h-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={75}
            paddingAngle={2}
            dataKey="value"
            strokeWidth={0}
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Legend
            wrapperStyle={{ fontSize: "11px", color: textColor }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="text-center">
          <p className="text-2xl font-bold">{successRate}%</p>
          <p className="text-[10px] text-muted-foreground">éxito</p>
        </div>
      </div>
    </div>
  )
}
