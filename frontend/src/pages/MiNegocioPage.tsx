import { useEffect, useState } from 'react';
import { error as humanError } from "@/utils/humanize"
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface Stats {
  crm: { total: number; by_stage: Record<string, number> };
  inventory: { total: number; low_stock: number; out_of_stock: number; total_value: number };
  invoice: { total: number; pending: number; paid: number; overdue: number; total_revenue: number };
}

const defaultStats: Stats = {
  crm: { total: 0, by_stage: {} },
  inventory: { total: 0, low_stock: 0, out_of_stock: 0, total_value: 0 },
  invoice: { total: 0, pending: 0, paid: 0, overdue: 0, total_revenue: 0 },
};

/**
 * Mapea stage interno (new, contacted, qualified, ...) → clave i18n.
 * Cualquier stage desconocido se renderiza tal cual (sin traducción).
 */
function stageLabel(stage: string, t: (k: string) => string): string {
  const key = `crm.stage_${stage}`;
  const translated = t(key);
  // Si la clave no se traduce (devuelve el key), mostrar el stage original.
  return translated === key ? stage : translated;
}

export default function MiNegocioPage() {
  const { t } = useTranslation();
  const [stats, setStats] = useState<Stats>(defaultStats);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // BUG P0-2: antes se usaba `localStorage.getItem('token')` (siempre null
    // porque la app usa cookies httpOnly vía `credentials: 'include'`) y una
    // URL hardcoded `localhost:8000` que no existe en producción. Ahora se
    // usan rutas relativas (el proxy/nginx las resuelve) y cookies de sesión.
    // Además se añade AbortController para cancelar en unmount (BUG P1-8).
    // El controller se declara en el scope del effect (no del IIFE) para que
    // el cleanup lo alcance.
    const controller = new AbortController();
    (async () => {
      try {
        const opts: RequestInit = { credentials: 'include', signal: controller.signal };
        const [crmRes, invRes, inv2Res] = await Promise.all([
          fetch('/api/v2/crm/stats', opts),
          fetch('/api/v2/inventory/stats', opts),
          fetch('/api/v2/invoices/stats', opts),
        ]);

        const [crm, inv, inv2] = await Promise.all([
          crmRes.ok ? crmRes.json() : defaultStats.crm,
          invRes.ok ? invRes.json() : defaultStats.inventory,
          inv2Res.ok ? inv2Res.json() : defaultStats.invoice,
        ]);

        if (controller.signal.aborted) return;
        setStats({
          crm: crm || defaultStats.crm,
          inventory: inv || defaultStats.inventory,
          invoice: inv2 || defaultStats.invoice,
        });
      } catch (err) {
        if (controller.signal.aborted) return;
        console.error('Error loading stats:', humanError(err));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">{t('minegocio.title')}</h1>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="h-8 w-24 bg-muted animate-pulse rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">{t('minegocio.title')}</h1>

      {/* Top row: 3 KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('crm.leads')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">{stats.crm.total}</p>
            <p className="text-sm text-muted-foreground">{t('minegocio.leads_in_pipeline')}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('minegocio.pending_invoices')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">{stats.invoice.pending}</p>
            <p className="text-sm text-muted-foreground">
              {stats.invoice.overdue} {t('minegocio.overdue_invoices')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('minegocio.month_revenue')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold text-green-600">
              ${stats.invoice.total_revenue.toFixed(2)}
            </p>
            <p className="text-sm text-muted-foreground">{t('minegocio.total_invoiced')}</p>
          </CardContent>
        </Card>
      </div>

      {/* Bottom row: Stock + Pipeline */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('minegocio.critical_stock')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-3xl font-bold text-orange-600">{stats.inventory.low_stock}</p>
                <p className="text-sm">{t('minegocio.products_below_min')}</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-red-600">{stats.inventory.out_of_stock}</p>
                <p className="text-sm">{t('minegocio.out_of_stock')}</p>
              </div>
            </div>
            <div className="mt-4">
              <p className="text-sm text-muted-foreground">
                {t('inventory.stats_value')}: ${stats.inventory.total_value.toFixed(2)}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t('minegocio.sales_pipeline')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.entries(stats.crm.by_stage || {}).map(([stage, count]) => (
              <div key={stage} className="flex justify-between items-center py-2 border-b last:border-0">
                <Badge variant="outline">{stageLabel(stage, t)}</Badge>
                <span className="font-mono text-lg">{count}</span>
              </div>
            ))}
            {Object.keys(stats.crm.by_stage || {}).length === 0 && (
              <p className="text-sm text-muted-foreground">
                {t('crm.leads') === 'Leads' ? 'No leads in pipeline' : t('crm.leads')}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
