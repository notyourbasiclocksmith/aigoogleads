"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";

interface KPI {
  label: string;
  value: string;
  change?: number;
}

export default function WorkspaceDashboard() {
  const params = useParams();
  const tenantId = params?.tenantId as string;
  const [kpis, setKpis] = useState<KPI[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (tenantId) loadData();
  }, [tenantId]);

  async function loadData() {
    setLoading(true);
    try {
      const [kpiData, alertData, campData] = await Promise.all([
        api.get("/api/dashboard/kpis"),
        api.get("/api/dashboard/alerts"),
        api.get("/api/dashboard/campaigns"),
      ]);

      const k = kpiData || {};
      setKpis([
        { label: "Spend", value: `$${((k.cost_micros || 0) / 1_000_000).toFixed(0)}`, change: k.cost_change_pct },
        { label: "Clicks", value: String(k.clicks || 0), change: k.clicks_change_pct },
        { label: "Conversions", value: String(k.conversions || 0), change: k.conversions_change_pct },
        { label: "CPA", value: `$${(k.cpa || 0).toFixed(2)}`, change: k.cpa_change_pct },
      ]);
      setAlerts(Array.isArray(alertData) ? alertData : []);
      setCampaigns(Array.isArray(campData) ? campData : []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Dashboard</h1>
        <p className="text-slate-500 text-sm">Loading workspace data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Dashboard</h1>
        <p className="text-slate-500 text-sm mb-6">Workspace overview for this business</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-xs text-slate-500 mb-1">{kpi.label}</div>
            <div className="text-xl font-bold text-slate-900">{kpi.value}</div>
            {kpi.change !== undefined && kpi.change !== null && (
              <div className={`text-xs mt-1 ${kpi.change >= 0 ? "text-green-600" : "text-red-600"}`}>
                {kpi.change >= 0 ? "+" : ""}{kpi.change.toFixed(1)}%
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-slate-900 mb-3">Alerts</h2>
          <div className="space-y-2">
            {alerts.slice(0, 5).map((a: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span className={`w-2 h-2 rounded-full ${a.severity === "critical" ? "bg-red-500" : a.severity === "high" ? "bg-orange-500" : "bg-yellow-500"}`} />
                <span className="text-slate-700">{a.message || a.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Campaigns Summary */}
      {campaigns.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">Campaigns ({campaigns.length})</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="px-4 py-2 text-xs font-medium text-slate-500">Name</th>
                <th className="px-4 py-2 text-xs font-medium text-slate-500">Status</th>
                <th className="px-4 py-2 text-xs font-medium text-slate-500">Budget</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.slice(0, 10).map((c: any) => (
                <tr key={c.id} className="border-b border-slate-50">
                  <td className="px-4 py-2 text-sm font-medium text-slate-900">{c.name}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.status === "ENABLED" ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-600"}`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-sm text-slate-600">
                    ${((c.budget_micros || 0) / 1_000_000).toFixed(0)}/day
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
