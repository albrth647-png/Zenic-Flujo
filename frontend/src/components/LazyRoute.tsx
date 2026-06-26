import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react"
import { Loader2 } from "lucide-react"

/**
 * LazyRoute — Wrapper que elimina el boilerplate de Suspense + PageLoader.
 *
 * Antes:
 *   <Route path="dashboard" element={
 *     <Suspense fallback={<PageLoader />}><Dashboard /></Suspense>
 *   } />
 *
 * Después:
 *   <Route path="dashboard" element={<LazyRoute loader={() => import("@/pages/Dashboard")} />} />
 */
export function LazyRoute<T extends Record<string, unknown>>({
  loader,
}: {
  loader: () => Promise<{ default: ComponentType<T> }>
}) {
  const LazyComponent = lazy(loader) as LazyExoticComponent<ComponentType<T>>
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="size-8 animate-spin text-primary" />
        </div>
      }
    >
      <LazyComponent />
    </Suspense>
  )
}
