import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "@/index.css"
import "@/i18n"  // Inicializa react-i18next antes de montar App
import App from "@/App"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)

// ── PWA: registro del Service Worker ──────────────────────────────────────
// Fase 1 (sesión 5): la PWA offline NUNCA funcionó antes porque el sw.js
// existía en disco pero ningún código lo registraba. Ahora lo registramos
// en producción (no en dev, para no interferir con HMR de Vite).
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/static/sw.js", { scope: "/" })
      .then((registration) => {
        console.info("[PWA] Service Worker registrado:", registration.scope)

        // Detectar updates del SW y notificar al usuario
        registration.addEventListener("updatefound", () => {
          const newWorker = registration.installing
          if (!newWorker) return
          newWorker.addEventListener("statechange", () => {
            if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
              // Hay una nueva versión disponible
              console.info("[PWA] Nueva versión disponible. Recarga para actualizar.")
              // Opcional: disparar un evento para mostrar toast en la UI
              window.dispatchEvent(new CustomEvent("sw-update-available"))
            }
          })
        })
      })
      .catch((err) => {
        console.warn("[PWA] Error registrando Service Worker:", err)
      })

    // Permitir que la app fuerce el activate del nuevo SW
    let refreshing = false
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return
      refreshing = true
      window.location.reload()
    })
  })
}
