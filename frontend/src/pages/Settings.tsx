import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SettingsSmtpTab } from "@/components/settings/SettingsSmtpTab"
import { SettingsWhatsAppTab } from "@/components/settings/SettingsWhatsAppTab"
import { SettingsPasswordTab } from "@/components/settings/SettingsPasswordTab"
import { SettingsApiKeyTab } from "@/components/settings/SettingsApiKeyTab"
import { SettingsLicenseTab } from "@/components/settings/SettingsLicenseTab"
import { SettingsSystemTab } from "@/components/settings/SettingsSystemTab"
import {
  Mail,
  MessageCircle,
  Lock,
  Key,
  Award,
  Server,
} from "lucide-react"

export default function Settings() {
  const tabs = [
    { value: "smtp", label: "Correo SMTP", icon: Mail },
    { value: "whatsapp", label: "WhatsApp", icon: MessageCircle },
    { value: "password", label: "Contraseña", icon: Lock },
    { value: "api-key", label: "API Key", icon: Key },
    { value: "license", label: "Licencia", icon: Award },
    { value: "system", label: "Sistema", icon: Server },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Configuración</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Administra las opciones de tu sistema
        </p>
      </div>

      <Tabs defaultValue="smtp" className="space-y-4">
        <TabsList className="w-full justify-start overflow-x-auto">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="gap-2 data-[state=active]:shadow-none"
            >
              <tab.icon className="size-4 shrink-0" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="smtp" className="mt-0">
          <SettingsSmtpTab />
        </TabsContent>
        <TabsContent value="whatsapp" className="mt-0">
          <SettingsWhatsAppTab />
        </TabsContent>
        <TabsContent value="password" className="mt-0">
          <SettingsPasswordTab />
        </TabsContent>
        <TabsContent value="api-key" className="mt-0">
          <SettingsApiKeyTab />
        </TabsContent>
        <TabsContent value="license" className="mt-0">
          <SettingsLicenseTab />
        </TabsContent>
        <TabsContent value="system" className="mt-0">
          <SettingsSystemTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
