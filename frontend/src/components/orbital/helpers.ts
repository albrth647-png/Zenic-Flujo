/**
 * helpers — Utilidades puras para ORBITAL (sin estado, sin side-effects).
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 */
export function degrees(rad: number): number {
  return ((rad * 180) / Math.PI) % 360
}

export function torColor(value: number): string {
  const abs = Math.abs(value)
  if (abs < 0.1) return "text-zinc-500"
  if (value > 0) return "text-emerald-400"
  return "text-red-400"
}

export function torBg(value: number): string {
  const abs = Math.min(Math.abs(value) / 100, 1)
  if (value > 0) return `rgba(52,211,153,${abs * 0.2})`
  if (value < 0) return `rgba(248,113,113,${abs * 0.2})`
  return "transparent"
}
