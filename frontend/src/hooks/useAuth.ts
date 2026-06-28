import { useContext } from "react"
import { AuthContext } from "@/contexts/AuthContext"
import type { AuthContextValue } from "@/types/auth"

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth debe usarse dentro de un AuthProvider")
  }
  return context
}
