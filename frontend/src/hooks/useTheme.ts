import { useContext } from "react"
import { ThemeContext } from "@/contexts/ThemeContextValue"
import type { ThemeContextValue } from "@/types/theme"

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme debe usarse dentro de un ThemeProvider")
  return ctx
}
