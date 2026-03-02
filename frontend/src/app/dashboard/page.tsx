"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import {
  TrendingUp, TrendingDown, DollarSign, MousePointerClick,
  Eye, PhoneCall, AlertTriangle, Zap, ArrowRight,
} from "lucide-react";

interface KPIs {
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  ctr: number;
  cpc: number;
  cpa: number;
  roas: number;
}

export default function DashboardPage() {
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [kpiData, alertData, campData] = await Promise.all([
          api.get("/api/dashboard/kpis").catch(() => null),
          api.get("/api/dashboard/alerts").catch(() => []),
          api.get("/api/dashboard/campaigns").catch(() => []),
        ]);
        setKpis(kpiData);
        setAlerts(Array.isArray(alertData) ? alertData : []);
        setCampaigns(Array.isArray(campData) ? campData : []);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const kpiCards = kpis
    ? [
        { label: "Impressions", value: formatNumber(kpis.impressions), icon: Eye, color: "text-blue-600" },
        { label: "Clicks", value: formatNumber(kpis.clicks), icon: MousePointerClick, color: "text-green-600" },
        { label: "Cost", value: formatCurrency(kpis.cost), icon: DollarSign, color: "text-orange-600" },
        { label: "Conversions", value: kpis.conversions.toFixed(1), icon: PhoneCall, color: "text-purple-600" },
        { label: "CTR", value: formatPercent(kpis.ctr), icon: TrendingUp, color: "text-blue-500" },
        { label: "CPC", value: formatCurrency(kpis.cpc), icon: DollarSign, color: "text-slate-600" },
        { label: "CPA", value: formatCurrency(kpis.cpa), icon: DollarSign, color: "text-red-600" },
        { label: "ROAS", value: `${kpis.roas?.toFixed(2) || "0.00"}x`, icon: TrendingUp, color: "text-emerald-600" },
      ]
    : [];

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Executive Dashboard</h1>
            <p className="text-muted-foreground">Last 30 days performance overview</p>
          </div>
          <Button variant="outline" onClick={() => window.location.href = "/ads/prompt"}>
            <Zap className="w-4 h-4 mr-2" />
            Command Console
          </Button>
        </div>

        {loading ? (
          <div className="grid grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6">
                  <div className="h-4 bg-slate-200 rounded w-20 mb-2" />
                  <div className="h-8 bg-slate-200 rounded w-28" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {kpiCards.map((kpi) => {
              const Icon = kpi.icon;
              return (
                <Card key={kpi.label}>
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-muted-foreground">{kpi.label}</span>
                      <Icon className={`w-4 h-4 ${kpi.color}`} />
                    </div>
                    <div className="text-2xl font-bold">{kpi.value}</div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {alerts.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-500" />
                Active Alerts
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {alerts.map((a: any, i: number) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-yellow-50 border border-yellow-100">
                    <Badge variant={a.severity === "critical" ? "destructive" : "warning"}>
                      {a.severity}
                    </Badge>
                    <p className="text-sm">{a.message}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">Campaign Summary</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => window.location.href = "/ads/campaigns"}>
              View All <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          </CardHeader>
          <CardContent>
            {campaigns.length === 0 ? (
              <p className="text-muted-foreground text-sm">No campaigns found. Use the Command Console to create your first campaign.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="pb-2 font-medium">Campaign</th>
                      <th className="pb-2 font-medium">Status</th>
                      <th className="pb-2 font-medium text-right">Impressions</th>
                      <th className="pb-2 font-medium text-right">Clicks</th>
                      <th className="pb-2 font-medium text-right">Cost</th>
                      <th className="pb-2 font-medium text-right">Conv.</th>
                      <th className="pb-2 font-medium text-right">CPA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.map((c: any) => (
                      <tr key={c.campaign_id || c.name} className="border-b last:border-0">
                        <td className="py-2.5 font-medium">{c.name}</td>
                        <td className="py-2.5">
                          <Badge variant={c.status === "ENABLED" ? "success" : "secondary"}>
                            {c.status}
                          </Badge>
                        </td>
                        <td className="py-2.5 text-right">{formatNumber(c.impressions || 0)}</td>
                        <td className="py-2.5 text-right">{formatNumber(c.clicks || 0)}</td>
                        <td className="py-2.5 text-right">{formatCurrency(c.cost || 0)}</td>
                        <td className="py-2.5 text-right">{(c.conversions || 0).toFixed(1)}</td>
                        <td className="py-2.5 text-right">{formatCurrency(c.cpa || 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
