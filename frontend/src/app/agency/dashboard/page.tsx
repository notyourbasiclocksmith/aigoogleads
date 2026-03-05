"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Building2, TrendingUp, TrendingDown, DollarSign, Target, AlertTriangle, Search } from "lucide-react";

interface TenantInfo {
  id: string;
  name: string;
  role: string;
  industry?: string;
  tier: string;
}

interface TenantKPI {
  id: string;
  name: string;
  industry: string;
  tier: string;
  spend: number;
  conversions: number;
  cpa: number;
  alerts: number;
}

export default function AgencyDashboardPage() {
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [kpis, setKpis] = useState<TenantKPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"name" | "spend" | "conversions" | "cpa">("name");
  const router = useRouter();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const data = await api.get("/api/me");
      const list: TenantInfo[] = data.tenants || [];

      if (list.length < 2) {
        router.push("/tenant/select");
        return;
      }

      setTenants(list);

      // Fetch real KPIs per tenant from rollup endpoint
      const kpiResults: TenantKPI[] = await Promise.all(
        list.map(async (t) => {
          try {
            const rollup = await api.get(`/api/v2/mcc/rollups/kpis?tenant_id=${t.id}&range_days=30`);
            const totals = rollup.totals || {};
            const costDollars = (totals.cost_micros || 0) / 1_000_000;
            const conversions = totals.conversions || 0;
            // Fetch alert count
            let alertCount = 0;
            try {
              const alerts = await api.get(`/api/dashboard/alerts`);
              alertCount = Array.isArray(alerts) ? alerts.length : 0;
            } catch { /* ignore if no tenant scope */ }
            return {
              id: t.id,
              name: t.name,
              industry: t.industry || "Other",
              tier: t.tier,
              spend: Math.round(costDollars),
              conversions: Math.round(conversions),
              cpa: conversions > 0 ? Math.round(costDollars / conversions) : 0,
              alerts: alertCount,
            };
          } catch {
            return {
              id: t.id, name: t.name, industry: t.industry || "Other",
              tier: t.tier, spend: 0, conversions: 0, cpa: 0, alerts: 0,
            };
          }
        })
      );
      setKpis(kpiResults);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }

  const filtered = search
    ? kpis.filter((k) => k.name.toLowerCase().includes(search.toLowerCase()) || k.industry.toLowerCase().includes(search.toLowerCase()))
    : kpis;

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === "name") return a.name.localeCompare(b.name);
    if (sortBy === "spend") return b.spend - a.spend;
    if (sortBy === "conversions") return b.conversions - a.conversions;
    if (sortBy === "cpa") return a.cpa - b.cpa;
    return 0;
  });

  const totalSpend = kpis.reduce((s, k) => s + k.spend, 0);
  const totalConversions = kpis.reduce((s, k) => s + k.conversions, 0);
  const avgCPA = totalConversions > 0 ? Math.round(totalSpend / totalConversions) : 0;
  const totalAlerts = kpis.reduce((s, k) => s + k.alerts, 0);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-pulse text-slate-400">Loading agency view...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto p-6 lg:p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Agency Overview</h1>
            <p className="text-slate-500 mt-1">Aggregated metrics across all {tenants.length} workspaces</p>
          </div>
          <button
            onClick={() => router.push("/tenant/select")}
            className="text-sm text-slate-500 hover:text-blue-600 transition-colors"
          >
            Switch to workspace view
          </button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-medium text-slate-500">Total Spend</span>
            </div>
            <div className="text-2xl font-bold text-slate-900">${totalSpend.toLocaleString()}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <Target className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-medium text-slate-500">Total Conversions</span>
            </div>
            <div className="text-2xl font-bold text-slate-900">{totalConversions.toLocaleString()}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <TrendingDown className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-medium text-slate-500">Avg CPA</span>
            </div>
            <div className="text-2xl font-bold text-slate-900">${avgCPA}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4 text-slate-400" />
              <span className="text-xs font-medium text-slate-500">Active Alerts</span>
            </div>
            <div className={`text-2xl font-bold ${totalAlerts > 0 ? "text-red-600" : "text-green-600"}`}>{totalAlerts}</div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-4 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name or industry..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="name">Sort by Name</option>
            <option value="spend">Sort by Spend</option>
            <option value="conversions">Sort by Conversions</option>
            <option value="cpa">Sort by CPA</option>
          </select>
        </div>

        {/* Tenant KPI Table */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Business</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Industry</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Tier</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase text-right">Spend</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase text-right">Conversions</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase text-right">CPA</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase text-right">Alerts</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((k) => (
                <tr
                  key={k.id}
                  onClick={() => router.push(`/workspace/${k.id}/dashboard`)}
                  className="border-b border-slate-50 hover:bg-blue-50 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-md bg-slate-100 flex items-center justify-center text-sm font-bold text-slate-600">
                        {k.name.charAt(0).toUpperCase()}
                      </div>
                      <span className="text-sm font-medium text-slate-900">{k.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-500">{k.industry}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-slate-100 text-slate-600">{k.tier}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-900 text-right font-medium">${k.spend.toLocaleString()}</td>
                  <td className="px-4 py-3 text-sm text-slate-900 text-right">{k.conversions}</td>
                  <td className="px-4 py-3 text-sm text-right">
                    <span className={k.cpa > 40 ? "text-red-600 font-medium" : "text-green-600 font-medium"}>
                      ${k.cpa}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-right">
                    {k.alerts > 0 ? (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-medium">{k.alerts}</span>
                    ) : (
                      <span className="text-slate-300">0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
