import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { ThemeContext } from "./ThemeContextValue"
import type { Theme } from "@/types/theme"

const STORAGE_KEY = "zenic-theme"

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark"
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === "light" || stored === "dark") return stored
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme)

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove("dark", "light")
    root.classList.add(theme)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  // BUG P1-6: antes toggleTheme/setTheme eran funciones nuevas en cada render,
  // lo que causaba re-renders innecesarios en TODOS los consumers del contexto.
  // Ahora están estabilizadas con useCallback, y el value del Provider se
  // memoiza con useMemo para que solo cambie cuando `theme` cambie.
  const toggleTheme = useCallback(
    () => setThemeState((prev) => (prev === "dark" ? "light" : "dark")),
    [],
  )
  const setTheme = useCallback((t: Theme) => setThemeState(t), [])

  const value = useMemo(
    () => ({ theme, toggleTheme, setTheme, isDark: theme === "dark" }),
    [theme, toggleTheme, setTheme],
  )

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}
