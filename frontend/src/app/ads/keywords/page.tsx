"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Search, Pause, Play, TrendingUp, TrendingDown, Loader2, Star, Banknote, DollarSign, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";

type SortKey = "quality_score" | "impressions" | "clicks" | "cost" | "conversion_value" | "roas" | "conversions" | "cpc";
type SortDir = "asc" | "desc";

export default function KeywordPerformancePage() {
  const [keywords, setKeywords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [days, setDays] = useState(30);
  const [sortBy, setSortBy] = useState("cost");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("cost");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    loadData();
  }, [days, sortBy]);

  async function loadData() {
    setLoading(true);
    try {
      const data = await api.get(`/api/ads/keywords/performance?days=${days}&sort_by=${sortBy}&limit=100`);
      setKeywords(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function toggleStatus(kw: any) {
    const newStatus = kw.status === "ENABLED" ? "PAUSED" : "ENABLED";
    setActionLoading(kw.keyword_id);
    try {
      await api.patch(`/api/ads/keywords/${kw.keyword_id}/status`, { status: newStatus });
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  }

  async function adjustBid(kw: any, direction: "up" | "down") {
    const currentBid = kw.cpc * 1_000_000;
    const newBid = direction === "up" ? Math.round(currentBid * 1.2) : Math.round(currentBid * 0.8);
    setActionLoading(kw.keyword_id);
    try {
      await api.patch(`/api/ads/keywords/${kw.keyword_id}/bid`, {
        ad_group_id: kw.ad_group_id,
        criterion_id: kw.keyword_id,
        new_cpc_bid_micros: newBid,
      });
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(sortDir === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  }
  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ArrowUpDown className="w-3 h-3 text-slate-300" />;
    return sortDir === "desc" ? <ArrowDown className="w-3 h-3 text-blue-600" /> : <ArrowUp className="w-3 h-3 text-blue-600" />;
  }

  const preFiltered = keywords.filter(
    (k) => !filter || k.keyword_text?.toLowerCase().includes(filter.toLowerCase())
  );

  const filtered = [...preFiltered].sort((a, b) => {
    let av: number, bv: number;
    if (sortKey === "roas") {
      av = a.cost > 0 ? (a.conversion_value || 0) / a.cost : 0;
      bv = b.cost > 0 ? (b.conversion_value || 0) / b.cost : 0;
    } else {
      av = a[sortKey] || 0;
      bv = b[sortKey] || 0;
    }
    return sortDir === "desc" ? bv - av : av - bv;
  });

  const totalCost = filtered.reduce((s: number, k: any) => s + (k.cost || 0), 0);
  const totalConv = filtered.reduce((s: number, k: any) => s + (k.conversions || 0), 0);
  const totalClicks = filtered.reduce((s: number, k: any) => s + (k.clicks || 0), 0);
  const totalRevenue = filtered.reduce((s: number, k: any) => s + (k.conversion_value || 0), 0);
  const overallRoas = totalCost > 0 ? totalRevenue / totalCost : 0;

  return (
    <AppLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Keyword Performance</h1>
          <p className="text-[13px] text-slate-400 mt-0.5">Monitor and manage individual keyword performance</p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-6 gap-5">
          <Card className="border-0">
            <CardContent className="p-5">
              <p className="text-[12px] text-slate-400 font-medium">Keywords</p>
              <p className="text-[22px] font-semibold tracking-tight text-slate-900 mt-1">{filtered.length}</p>
            </CardContent>
          </Card>
          <Card className="border-0">
            <CardContent className="p-5">
              <p className="text-[12px] text-slate-400 font-medium">Total Spend</p>
              <p className="text-[22px] font-semibold tracking-tight text-slate-900 mt-1">${totalCost.toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
            </CardContent>
          </Card>
          <Card className="border-0 bg-emerald-50/50">
            <CardContent className="p-5">
              <p className="text-[12px] text-emerald-600 font-medium">Revenue</p>
              <p className="text-[22px] font-semibold tracking-tight text-emerald-700 mt-1">${totalRevenue.toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
            </CardContent>
          </Card>
          <Card className={`border-0 ${overallRoas >= 2 ? "bg-emerald-50/50" : ""}`}>
            <CardContent className="p-5">
              <p className="text-[12px] text-slate-400 font-medium">ROAS</p>
              <p className={`text-[22px] font-semibold tracking-tight mt-1 ${overallRoas >= 3 ? "text-emerald-700" : overallRoas >= 1 ? "text-blue-700" : "text-red-600"}`}>{overallRoas.toFixed(1)}x</p>
            </CardContent>
          </Card>
          <Card className="border-0">
            <CardContent className="p-5">
              <p className="text-[12px] text-slate-400 font-medium">Clicks</p>
              <p className="text-[22px] font-semibold tracking-tight text-slate-900 mt-1">{totalClicks.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card className="border-0">
            <CardContent className="p-5">
              <p className="text-[12px] text-slate-400 font-medium">Conversions</p>
              <p className="text-[22px] font-semibold tracking-tight text-slate-900 mt-1">{totalConv.toFixed(1)}</p>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300" />
            <Input placeholder="Filter keywords..." value={filter} onChange={(e: any) => setFilter(e.target.value)} className="pl-9 rounded-xl border-slate-200 text-[13px] h-10 bg-white" />
          </div>
          <select className="border border-slate-200 rounded-xl px-3.5 py-2.5 text-[13px] text-slate-600 bg-white appearance-none cursor-pointer hover:border-slate-300 transition-colors" value={days} onChange={(e: any) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <select className="border border-slate-200 rounded-xl px-3.5 py-2.5 text-[13px] text-slate-600 bg-white appearance-none cursor-pointer hover:border-slate-300 transition-colors" value={sortBy} onChange={(e: any) => setSortBy(e.target.value)}>
            <option value="cost">Sort: Cost</option>
            <option value="conversion_value">Sort: Revenue</option>
            <option value="clicks">Sort: Clicks</option>
            <option value="conversions">Sort: Conversions</option>
            <option value="quality_score">Sort: Quality Score</option>
          </select>
        </div>

        {/* Table */}
        {loading ? (
          <Card className="border-0"><CardContent className="p-12 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto mb-3 text-slate-300" /><p className="text-[13px] text-slate-400">Loading keywords...</p></CardContent></Card>
        ) : (
          <Card className="border-0 overflow-hidden">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="text-left px-4 py-3 font-medium text-slate-400">Keyword</th>
                      <th className="text-left px-3 py-3 font-medium text-slate-400">Match</th>
                      {([
                        { key: "quality_score" as SortKey, label: "QS", align: "text-center" },
                        { key: "impressions" as SortKey, label: "Impr.", align: "text-right" },
                        { key: "clicks" as SortKey, label: "Clicks", align: "text-right" },
                        { key: "cost" as SortKey, label: "Cost", align: "text-right" },
                        { key: "conversion_value" as SortKey, label: "Revenue", align: "text-right", color: "text-emerald-500" },
                        { key: "roas" as SortKey, label: "ROAS", align: "text-right", color: "text-emerald-500" },
                        { key: "conversions" as SortKey, label: "Conv.", align: "text-right" },
                        { key: "cpc" as SortKey, label: "CPC", align: "text-right" },
                      ] as const).map(({ key, label, align, color }) => (
                        <th key={key} className={`${align} px-3 py-3 font-medium ${color || "text-slate-400"}`}>
                          <button onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 hover:text-blue-600 transition-colors">
                            {label} <SortIcon col={key} />
                          </button>
                        </th>
                      ))}
                      <th className="px-3 py-3 font-medium text-slate-400">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((k: any, i: number) => (
                      <tr key={i} className={`border-b border-slate-50 last:border-0 hover:bg-slate-50/50 transition-colors ${k.conversions === 0 && k.cost > 20 ? "bg-red-50/30" : ""}`}>
                        <td className="px-4 py-3 font-medium text-slate-800 max-w-[280px] truncate">{k.keyword_text}</td>
                        <td className="px-3 py-3">
                          <span className="inline-flex px-2 py-0.5 rounded-lg text-[11px] font-medium bg-slate-100 text-slate-500">{k.match_type}</span>
                        </td>
                        <td className="px-3 py-3 text-center">
                          {k.quality_score ? (
                            <div className="flex items-center justify-center gap-1">
                              <Star className={`w-3 h-3 ${k.quality_score >= 7 ? "text-emerald-500" : k.quality_score >= 4 ? "text-amber-500" : "text-red-500"}`} />
                              <span className={`font-medium ${k.quality_score >= 7 ? "text-emerald-600" : k.quality_score >= 4 ? "text-amber-600" : "text-red-600"}`}>
                                {k.quality_score}
                              </span>
                            </div>
                          ) : <span className="text-slate-300">{"\u2014"}</span>}
                        </td>
                        <td className="px-3 py-3 text-right text-slate-500">{k.impressions?.toLocaleString()}</td>
                        <td className="px-3 py-3 text-right text-slate-500">{k.clicks?.toLocaleString()}</td>
                        <td className="px-3 py-3 text-right font-medium text-slate-700">${k.cost?.toFixed(2)}</td>
                        <td className="px-3 py-3 text-right">
                          {(k.conversion_value || 0) > 0 ? (
                            <span className="font-semibold text-emerald-600">${(k.conversion_value || 0).toFixed(0)}</span>
                          ) : (
                            <span className="text-slate-300">$0</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-right">
                          {k.cost > 0 && (k.conversion_value || 0) > 0 ? (
                            <span className={`inline-flex px-2 py-0.5 rounded-lg text-[11px] font-semibold ${
                              (k.conversion_value / k.cost) >= 5 ? "bg-emerald-50 text-emerald-600" :
                              (k.conversion_value / k.cost) >= 2 ? "bg-blue-50 text-blue-600" :
                              (k.conversion_value / k.cost) >= 1 ? "bg-amber-50 text-amber-600" :
                              "bg-red-50 text-red-600"
                            }`}>{(k.conversion_value / k.cost).toFixed(1)}x</span>
                          ) : (
                            <span className="text-slate-300">{"\u2014"}</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-right">
                          {k.conversions === 0 ? <span className="text-red-500">0</span> : <span className="text-slate-500">{k.conversions?.toFixed(1)}</span>}
                        </td>
                        <td className="px-3 py-3 text-right text-slate-500">${k.cpc?.toFixed(2)}</td>
                        <td className="px-3 py-3">
                          <div className="flex gap-0.5">
                            <button className="h-7 w-7 rounded-lg flex items-center justify-center hover:bg-slate-100 transition-colors disabled:opacity-30" onClick={() => adjustBid(k, "up")} title="Increase bid 20%"
                              disabled={actionLoading === k.keyword_id}>
                              <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                            </button>
                            <button className="h-7 w-7 rounded-lg flex items-center justify-center hover:bg-slate-100 transition-colors disabled:opacity-30" onClick={() => adjustBid(k, "down")} title="Decrease bid 20%"
                              disabled={actionLoading === k.keyword_id}>
                              <TrendingDown className="w-3.5 h-3.5 text-red-500" />
                            </button>
                            <button className="h-7 w-7 rounded-lg flex items-center justify-center hover:bg-slate-100 transition-colors disabled:opacity-30" onClick={() => toggleStatus(k)}
                              disabled={actionLoading === k.keyword_id} title="Pause/Enable">
                              {actionLoading === k.keyword_id ? <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400" /> :
                                <Pause className="w-3.5 h-3.5 text-slate-400" />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {filtered.length === 0 && (
                      <tr><td colSpan={12} className="p-12 text-center text-[13px] text-slate-400">No keyword performance data. Sync your account first.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
