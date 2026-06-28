import { useCallback, useState } from "react"
import { error as humanError } from "@/utils/humanize"

interface ApiOptions extends RequestInit {
  skipAuth?: boolean
  signal?: AbortSignal
}

export function useApi() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const api = useCallback(async <T = unknown>(path: string, options: ApiOptions = {}): Promise<T | null> => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(path, {
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
        credentials: "include",
        ...options,
      })
      if (res.status === 401 && !options.skipAuth) {
        // Si la sesión expiró, redirige al login
        window.location.href = "/login?expired=1"
        return null
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        // Soporta formato ErrorResponse: { error: "code", message: "text", details: {} }
        // y formato legacy: { error: "text" }
        const errMsg = data.message || data.error || `Error ${res.status}`
        setError(humanError(errMsg))
        return null
      }
      const data = await res.json()
      return data as T
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        return null  // Petición cancelada intencionalmente
      }        const errMsg = e instanceof Error ? e.message : "Error de conexión"
      setError(humanError(errMsg))
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  // API helper con métodos HTTP. Mantiene compatibilidad con páginas que usan
  // el patrón `const api = getApi(); api.get(...)` — ver BUG-FE-01.
  //
  // BUG-1-FE: antes `request` devolvía `null` en cualquier error (401, 500,
  // error de red). Eso hacía que los bloques `try/catch` de las 12 páginas que
  // usan `getApi()` fueran código muerto: el `catch` nunca se ejecutaba, los
  // errores eran invisibles. Ahora `request` lanza excepciones explícitas para
  // que los `catch` de las páginas puedan mostrar toasts y manejar el fallo.
  // El único caso en que se devuelve `null` sin lanzar es `204 No Content`
  // (respuesta exitosa sin cuerpo) y respuesta vacía — esos NO son errores.
  //
  // BUG-2-FE: cada método acepta un `options.signal` para permitir cancelar
  // el fetch desde el `useEffect` cleanup con `AbortController.abort()`.
  // El signal se pasa a `fetch` para que el request se cancele de verdad y
  // no quede zombie tras unmount.
  //
  // BUG-P0-3: `options` ahora acepta `headers` para que callers como
  // FacturacionElectronicaPage puedan enviar `X-License-Key`. Antes el tipo
  // solo permitía `{ signal?: AbortSignal }`, lo que causaba un TS error y
  // que el header se perdiera en runtime.
  const getApi = useCallback(() => {
    const request = async <T = unknown>(
      method: string,
      path: string,
      body?: unknown,
      options?: { signal?: AbortSignal; headers?: Record<string, string> },
    ): Promise<T | null> => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(path, {
          method,
          headers: {
            "Content-Type": "application/json",
            ...options?.headers,
          },
          credentials: "include",
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal: options?.signal,
        })
        if (res.status === 401) {
          // Sesión expirada: redirige al login y propaga el error para que
          // los `catch` blocks de las páginas se ejecuten (BUG-1-FE).
          window.location.href = "/login?expired=1"
          throw new Error("API no inicializada. Verifica auth.")
        }
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          const errMsg = data.message || data.error || `Error ${res.status}`
          setError(humanError(errMsg))
          throw new Error(errMsg)
        }
        // 204 No Content o respuesta vacía: no es error, devolvemos null.
        if (res.status === 204) return null
        const text = await res.text()
        if (!text) return null
        return JSON.parse(text) as T
      } catch (e) {
        // AbortError: el caller canceló intencionalmente via AbortController.
        // Relanzamos para que el `catch` de la página pueda identificarlo por
        // `e.name === "AbortError"` y silenciarlo (BUG-2-FE).
        if (e instanceof DOMException && e.name === "AbortError") {
          throw e
        }
        // TypeError de fetch: red caída o backend no responde. Mensaje
        // genérico "Error de conexión" para el usuario (no "Failed to fetch").
        if (e instanceof TypeError) {
          const errMsg = "Error de conexión"
          setError(humanError(errMsg))
          throw new Error(errMsg, { cause: e })
        }
        // Errores que ya lanzamos arriba (401, !res.ok) — relanzamos tal cual.
        if (e instanceof Error) {
          setError(humanError(e.message))
          throw e
        }
        // Fallback para errores desconocidos.
        const errMsg = "Error de conexión"
        setError(humanError(errMsg))
        throw new Error(errMsg, { cause: e })
      } finally {
        setLoading(false)
      }
    }

    return {
      get: <T = unknown>(path: string, options?: { signal?: AbortSignal; headers?: Record<string, string> }) =>
        request<T>("GET", path, undefined, options),
      post: <T = unknown>(path: string, body?: unknown, options?: { signal?: AbortSignal; headers?: Record<string, string> }) =>
        request<T>("POST", path, body, options),
      put: <T = unknown>(path: string, body?: unknown, options?: { signal?: AbortSignal; headers?: Record<string, string> }) =>
        request<T>("PUT", path, body, options),
      patch: <T = unknown>(path: string, body?: unknown, options?: { signal?: AbortSignal; headers?: Record<string, string> }) =>
        request<T>("PATCH", path, body, options),
      delete: <T = unknown>(path: string, options?: { signal?: AbortSignal; headers?: Record<string, string> }) =>
        request<T>("DELETE", path, undefined, options),
    }
  }, [])

  return { api, apiFetch, getApi, loading, error }
}

export async function apiFetch<T = unknown>(path: string, options: ApiOptions = {}): Promise<T | null> {
  try {
    const res = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      credentials: "include",
      ...options,
    })
    if (res.status === 401 && !options.skipAuth) {
      window.location.href = "/login?expired=1"
      return null
    }
    if (!res.ok) return null
    return await res.json() as T
  } catch {
    return null
  }
}
