/// <reference types="vite/client" />

/// Tipos para el sistema de autenticación y usuarios

export interface User {
  id: number
  username: string
  role: "admin" | "editor" | "viewer"
  display_name?: string
  email?: string
  last_login_at?: string
  is_active?: boolean
}

export interface AuthState {
  user: User | null
  authenticated: boolean
  loading: boolean
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  status: string
  user: string
  role?: string
  // Campos opcionales para respuestas de error del backend
  message?: string
  error?: string
}

export interface AuthStatusResponse {
  authenticated: boolean
  user?: User
}

export interface UserFormData {
  username: string
  password: string
  role: "admin" | "editor" | "viewer"
  display_name?: string
  email?: string
}

// ── Context types ───────────────────────────────────────

export interface RegisterData {
  username: string
  password: string
  display_name?: string
  email?: string
}

export interface AuthContextValue extends AuthState {
  login: (credentials: LoginCredentials) => Promise<boolean>
  register: (data: RegisterData) => Promise<{ success: boolean; error?: string }>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}
