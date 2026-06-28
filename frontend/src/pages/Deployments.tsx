import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Server,
  Container,
  Cloud,
  Shield,
  GitBranch,
  Terminal,
  Copy,
  CheckCircle2,
} from "lucide-react"
import { useState } from "react"

const SECTIONS = [
  {
    id: "helm",
    icon: Server,
    title: "Helm Chart (recomendado)",
    color: "text-blue-500",
    bg: "bg-blue-500/10",
    steps: [
      "helm install zenic-flujo ./deploy/helm/zenic-flujo --namespace zenic-flujo --create-namespace",
      "kubectl get pods -n zenic-flujo -w",
      "kubectl get ingress -n zenic-flujo",
    ],
  },
  {
    id: "kustomize",
    icon: GitBranch,
    title: "K8s Manifests (Kustomize)",
    color: "text-purple-500",
    bg: "bg-purple-500/10",
    steps: [
      "kubectl apply -k deploy/k8s/",
      "kubectl get all -n zenic-flujo",
    ],
  },
  {
    id: "compose",
    icon: Container,
    title: "Docker Compose",
    color: "text-emerald-500",
    bg: "bg-emerald-500/10",
    steps: [
      'cat > .env << EOF\nWFD_SESSION_SECRET=cambio-en-produccion\nWFD_PRODUCTION=false\nEOF',
      "docker compose up -d",
      "docker compose logs -f zenic-flujo",
    ],
  },
  {
    id: "docker",
    icon: Container,
    title: "Docker standalone",
    color: "text-cyan-500",
    bg: "bg-cyan-500/10",
    steps: [
      'docker run -d --name zenic-flujo -p 8080:8080 -p 8081:8081 -e WFD_SESSION_SECRET="$(openssl rand -hex 32)" -v zenic-data:/app/data ghcr.io/albrth647-png/zenic-flujo:latest',
    ],
  },
  {
    id: "istio",
    icon: Shield,
    title: "Service Mesh (Istio)",
    color: "text-rose-500",
    bg: "bg-rose-500/10",
    steps: [
      "kubectl apply -f deploy/istio/",
      "istioctl authn tls-check zenic-flujo.zenic-flujo.svc.cluster.local",
    ],
  },
]

export default function Deployments() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleCopy = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Despliegue</h1>
        <p className="text-muted-foreground text-sm">
          Guía de despliegue para Kubernetes, Docker Compose y Service Mesh
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid gap-4 md:grid-cols-4">
        {[
          { label: "Helm Chart", value: "1.0.0", icon: Server },
          { label: "K8s Manifests", value: "8 recursos", icon: GitBranch },
          { label: "HPA Range", value: "2–10 pods", icon: Cloud },
          { label: "mTLS", value: "Strict", icon: Shield },
        ].map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.label}>
              <CardContent className="p-4 flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Icon className="size-4 text-primary" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                  <p className="text-sm font-semibold">{stat.value}</p>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Method cards */}
      <div className="space-y-4">
        {SECTIONS.map((section) => {
          const Icon = section.icon
          return (
            <Card key={section.id}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={cn("rounded-lg p-2", section.bg)}>
                      <Icon className={cn("size-4", section.color)} />
                    </div>
                    <div>
                      <CardTitle className="text-base">{section.title}</CardTitle>
                    </div>
                  </div>
                  <Badge variant="outline" className="text-[10px]">
                    {section.steps.length} pasos
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {section.steps.map((step, i) => (
                    <div key={i} className="group relative">
                      <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-3">
                        <span className="mt-0.5 size-5 shrink-0 rounded-full bg-primary/10 text-primary flex items-center justify-center text-[10px] font-bold">
                          {i + 1}
                        </span>
                        <code className="flex-1 text-xs font-mono leading-relaxed whitespace-pre-wrap break-all">
                          {step}
                        </code>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => handleCopy(step, `${section.id}-${i}`)}
                          aria-label={copiedId === `${section.id}-${i}` ? "Comando copiado" : "Copiar comando al portapapeles"}
                        >
                          {copiedId === `${section.id}-${i}` ? (
                            <CheckCircle2 className="size-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="size-3.5" />
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Env vars */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Terminal className="size-4" />
            Variables de entorno esenciales
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 font-medium text-muted-foreground">Variable</th>
                  <th className="text-left py-2 font-medium text-muted-foreground">Descripción</th>
                  <th className="text-left py-2 font-medium text-muted-foreground">Obligatoria</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["WFD_SESSION_SECRET", "Clave para firmar sesiones", "✅"],
                  ["WFD_LICENSE_SECRET", "Clave para validar licencias", "✅"],
                  ["WFD_ENCRYPTION_MASTER_KEY", "Clave maestra BYOK (32 bytes hex)", "❌"],
                  ["WFD_POSTGRES_URL", "URL PostgreSQL (producción)", "❌ (usa SQLite)"],
                  ["WFD_REDIS_URL", "URL Redis (sesiones, caché)", "❌"],
                  ["WFD_PRODUCTION", "'true' en producción", "✅"],
                ].map(([variable, desc, required]) => (
                  <tr key={variable} className="border-b last:border-0">
                    <td className="py-2 font-mono text-xs">{variable}</td>
                    <td className="py-2 text-muted-foreground">{desc}</td>
                    <td className="py-2">{required}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
