/// Tipos de propiedades para componentes UI compartidos

// ── Button ───────────────────────────────────────────────
// Nota: variant y size se definen como union literal en lugar
// de depender de VariantProps<typeof buttonVariants> para
// evitar una dependencia runtime de cva().

export type ButtonVariant = "default" | "destructive" | "outline" | "secondary" | "ghost" | "link"
export type ButtonSize = "default" | "sm" | "lg" | "icon"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean
  variant?: ButtonVariant
  size?: ButtonSize
}

// ── Badge ────────────────────────────────────────────────

export type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: BadgeVariant
}
