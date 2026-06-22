import { useEffect, useState } from 'react';
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

export default function MiNegocioPage() {
  const [stats, setStats] = useState<Stats>(defaultStats);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const token = localStorage.getItem('token');
        const headers = { Authorization: `Bearer ${token}` };
        const base = import.meta.env.VITE_API_URL || 'http://localhost:8000';

        const [crmRes, invRes, inv2Res] = await Promise.all([
          fetch(`${base}/api/v2/crm/stats`, { headers }),
          fetch(`${base}/api/v2/inventory/stats`, { headers }),
          fetch(`${base}/api/v2/invoices/stats`, { headers }),
        ]);

        const [crm, inv, inv2] = await Promise.all([
          crmRes.json(),
          invRes.json(),
          inv2Res.json(),
        ]);

        setStats({
          crm: crm || defaultStats.crm,
          inventory: inv || defaultStats.inventory,
          invoice: inv2 || defaultStats.invoice,
        });
      } catch (err) {
        console.error('Error loading stats:', err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Mi Negocio</h1>
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
      <h1 className="text-3xl font-bold">Mi Negocio</h1>

      {/* Top row: 3 KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Leads</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">{stats.crm.total}</p>
            <p className="text-sm text-muted-foreground">en pipeline</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Facturas Pendientes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">{stats.invoice.pending}</p>
            <p className="text-sm text-muted-foreground">{stats.invoice.overdue} vencidas</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Ingresos del Mes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold text-green-600">
              ${stats.invoice.total_revenue.toFixed(2)}
            </p>
            <p className="text-sm text-muted-foreground">total facturado</p>
          </CardContent>
        </Card>
      </div>

      {/* Bottom row: Stock + Pipeline */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Stock Crítico</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-3xl font-bold text-orange-600">{stats.inventory.low_stock}</p>
                <p className="text-sm">productos bajo mínimos</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-red-600">{stats.inventory.out_of_stock}</p>
                <p className="text-sm">agotados</p>
              </div>
            </div>
            <div className="mt-4">
              <p className="text-sm text-muted-foreground">
                Valor total inventario: ${stats.inventory.total_value.toFixed(2)}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Pipeline de Ventas</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.entries(stats.crm.by_stage || {}).map(([stage, count]) => (
              <div key={stage} className="flex justify-between items-center py-2 border-b last:border-0">
                <Badge variant="outline">{stage}</Badge>
                <span className="font-mono text-lg">{count}</span>
              </div>
            ))}
            {Object.keys(stats.crm.by_stage || {}).length === 0 && (
              <p className="text-sm text-muted-foreground">No hay leads en el pipeline</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
