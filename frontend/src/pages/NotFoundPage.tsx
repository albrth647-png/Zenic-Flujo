import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Home, ArrowLeft } from "lucide-react"

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="text-center max-w-md">
        <div className="text-7xl font-bold text-primary/20 mb-4">404</div>
        <h1 className="text-2xl font-bold tracking-tight mb-2">
          ¡Ups! Página no encontrada
        </h1>
        <p className="text-muted-foreground text-sm mb-8">
          La página que buscas no existe o fue movida a otro lugar.
          Revisa la dirección o vuelve al inicio.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Button variant="outline" onClick={() => window.history.back()}>
            <ArrowLeft className="size-4 mr-2" />
            Volver atrás
          </Button>
          <Link to="/app/dashboard">
            <Button>
              <Home className="size-4 mr-2" />
              Ir al inicio
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
