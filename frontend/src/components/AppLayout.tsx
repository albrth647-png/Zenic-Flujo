import { Outlet, Link, useLocation, useNavigate } from "react-router-dom"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  Workflow,
  Settings,
  MessageSquare,
  Package,
  Shield,
  ShieldOff,
  Cloud,
  Server,
  ChevronLeft,
  ChevronRight,
  LogOut,
  UserCircle,
  Bot,
  Users,
  BarChart3,
  FileText,
  Link2,
  Cpu,
  Handshake,
  Sun,
  Moon,
  Zap,
  GitMerge,
  BrainCircuit,
  Receipt,
  Store,
  Building2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ToastContainer } from "@/components/ui/toast"
import { useState } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useAuth } from "@/hooks/useAuth"
import { useTheme } from "@/hooks/useTheme"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import {
  PATH_DASHBOARD,
  PATH_EDITOR,
  PATH_WORKFLOWS,
  PATH_CRM,
  PATH_INVENTORY,
  PATH_INVOICES,
  PATH_CHAT,
  PATH_INTEGRATIONS,
  PATH_ORBITAL,
  PATH_PARTNERS,
  PATH_AIRGAP,
  PATH_PLUGINS,
  PATH_COMPLIANCE,
  PATH_ADMIN,
  PATH_REPORTS,
  PATH_SYNC,
  PATH_DEPLOY,
  PATH_AGENTS,
  PATH_BPMN,
  PATH_NLU,
  PATH_TENANTS,
  PATH_MI_NEGOCIO,
  PATH_FACTURACION_ELECTRONICA,
  PATH_SETTINGS,
} from "@/router/paths"

const NAV_ITEMS = [
  { to: PATH_DASHBOARD, icon: LayoutDashboard, label: "Panel" },
  { to: PATH_EDITOR, icon: Workflow, label: "Editor" },
  { to: PATH_WORKFLOWS, icon: MessageSquare, label: "Flujos" },
  { to: PATH_CRM, icon: Users, label: "CRM" },
  { to: PATH_INVENTORY, icon: Package, label: "Inventario" },
  { to: PATH_INVOICES, icon: FileText, label: "Facturación" },
  { to: PATH_CHAT, icon: Bot, label: "Chat Inteligente" },
  { to: PATH_INTEGRATIONS, icon: Link2, label: "Integraciones" },
  { to: PATH_ORBITAL, icon: Cpu, label: "ORBITAL" },
  { to: PATH_PARTNERS, icon: Handshake, label: "Socios" },
  { to: PATH_AIRGAP, icon: ShieldOff, label: "Aislamiento" },
  { to: PATH_PLUGINS, icon: Package, label: "Extensiones" },
  { to: PATH_COMPLIANCE, icon: Shield, label: "Cumplimiento" },
  { to: PATH_ADMIN, icon: Users, label: "Administración" },
  { to: PATH_REPORTS, icon: BarChart3, label: "Reportes" },
  { to: PATH_SYNC, icon: Cloud, label: "Sincronización" },
  { to: PATH_DEPLOY, icon: Server, label: "Despliegue" },
  { to: PATH_AGENTS, icon: Zap, label: "Agentes" },
  { to: PATH_BPMN, icon: GitMerge, label: "BPMN" },
  { to: PATH_NLU, icon: BrainCircuit, label: "Lenguaje Natural" },
  { to: PATH_TENANTS, icon: Building2, label: "Organizaciones" },
  { to: PATH_FACTURACION_ELECTRONICA, icon: Receipt, label: "Facturación Electrónica" },
  { to: PATH_MI_NEGOCIO, icon: Store, label: "Mi Negocio" },
  { to: PATH_SETTINGS, icon: Settings, label: "Configuración" },
]

export function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { toggleTheme, isDark } = useTheme()
  const [collapsed, setCollapsed] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate("/login", { replace: true })
  }

  const userLabel = user?.display_name || user?.username || "Usuario"
  const userInitial = userLabel.charAt(0).toUpperCase()

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside
        className={cn(
          "flex flex-col border-r bg-sidebar-background transition-all duration-300",
          collapsed ? "w-16" : "w-56"
        )}
      >
        {/* Brand */}
        <div className="flex h-14 items-center gap-2 border-b px-4">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
            ZF
          </div>
          {!collapsed && (
            <span className="font-semibold text-sm truncate">Zenic Flujo</span>
          )}
        </div>

        {/* Nav */}
        <ScrollArea className="flex-1 py-2">
          <nav className="flex flex-col gap-1 px-2">
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname.startsWith(item.to)
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground hover:bg-sidebar-accent/50"
                  )}
                >
                  <item.icon className="size-4 shrink-0" />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </Link>
              )
            })}
          </nav>
        </ScrollArea>

        <Separator />

        {/* User info */}
        <div className={cn("p-2", collapsed && "flex justify-center")}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className={cn(
                  "w-full justify-start gap-3 px-3 h-10 hover:bg-sidebar-accent/50",
                  collapsed && "justify-center px-2"
                )}
              >
                <div className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold shrink-0">
                  {userInitial}
                </div>
                {!collapsed && (
                  <div className="flex-1 text-left min-w-0">
                    <p className="text-xs font-medium truncate">{userLabel}</p>
                    <p className="text-[10px] text-muted-foreground capitalize">
                      {user?.role || "usuario"}
                    </p>
                  </div>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                {userLabel}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => navigate("/app/settings")}>
                <UserCircle className="size-3.5 mr-2" />
                Mi cuenta
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleLogout}
                className="text-destructive focus:text-destructive"
              >
                <LogOut className="size-3.5 mr-2" />
                Cerrar sesión
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Theme toggle + Collapse */}
        <div className="flex items-center gap-1 p-2 pt-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-zinc-400 hover:text-zinc-200"
            onClick={toggleTheme}
            title={isDark ? "Modo claro" : "Modo oscuro"}
            aria-label={isDark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          >
            {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8 shrink-0 text-zinc-400 hover:text-zinc-200", collapsed ? "" : "ml-auto")}
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Expandir menú lateral" : "Contraer menú lateral"}
          >
            {collapsed ? (
              <ChevronRight className="size-4" />
            ) : (
              <ChevronLeft className="size-4" />
            )}
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto bg-background">
        <div className="container mx-auto p-6 max-w-7xl">
          <Outlet />
        </div>
      </main>
      <ToastContainer />
    </div>
  )
}
