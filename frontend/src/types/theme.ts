/// Tipos para el sistema de theming

export type Theme = "dark" | "light"

export interface ThemeContextValue {
  theme: Theme
  toggleTheme: () => void
  setTheme: (theme: Theme) => void
  isDark: boolean
}
