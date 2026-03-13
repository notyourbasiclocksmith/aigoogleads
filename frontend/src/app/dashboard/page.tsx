"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import {
  TrendingUp, TrendingDown, DollarSign, MousePointerClick,
  Eye, PhoneCall, AlertTriangle, Zap, ArrowRight, Calendar,
  Lightbulb, Target, CheckCircle2, Brain, Shield, Play,
  Loader2, Banknote, XCircle, Flame, BarChart3, Star,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";

interface KPIs {
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  conv_value: number;
  ctr: number;
  cpc: number;
  cpa: number;
  roas: number;
}

interface HealthCheck {
  problems_found: number;
  total_wasted_spend: number;
  wasted_spend: {
    keywords: { cost: number; count: number };
    search_terms: { cost: number; count: number };
    low_ctr_ads: { cost: number; count: number };
    budget_limited: { count: number };
  };
  money_keywords: {
    keyword: string;
    keyword_id: string;
    spend: number;
    revenue: number;
    conversions: number;
    clicks: number;
    roas: number;
  }[];
  account_status: {
    campaigns_total: number;
    campaigns_enabled: number;
    autonomy_mode: string;
    last_optimization: string | null;
    last_optimization_status: string | null;
    last_scan_id: string | null;
    last_scan_problems: number;
  };
}

const DATE_RANGES = [
  { label: "7d", value: 7 },
  { label: "14d", value: 14 },
  { label: "30d", value: 30 },
  { label: "60d", value: 60 },
  { label: "90d", value: 90 },
];

const MODE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  suggest: { label: "Suggest Only", color: "text-slate-600", bg: "bg-slate-100" },
  semi_auto: { label: "Semi-Autopilot", color: "text-blue-700", bg: "bg-blue-100" },
  full_auto: { label: "Full Autopilot", color: "text-emerald-700", bg: "bg-emerald-100" },
};

export default function DashboardPage() {
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [trends, setTrends] = useState<any[]>([]);
  const [campaignSummary, setCampaignSummary] = useState<any>(null);
  const [recCount, setRecCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [chartMetric, setChartMetric] = useState<"clicks" | "cost" | "conversions">("clicks");
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState("");

  useEffect(() => {
    loadData();
  }, [days]);

  async function loadData() {
    setLoading(true);
    try {
      const [kpiData, healthData, alertData, campData, trendData, summaryData, recsData] = await Promise.all([
        api.get(`/api/dashboard/kpis?days=${days}`).catch(() => null),
        api.get(`/api/dashboard/health-check?days=${days}`).catch(() => null),
        api.get("/api/dashboard/alerts").catch(() => []),
        api.get("/api/dashboard/campaigns").catch(() => []),
        api.get(`/api/dashboard/trends?days=${days}`).catch(() => []),
        api.get("/api/dashboard/campaign-summary").catch(() => null),
        api.get("/api/ads/google-recommendations?status=pending").catch(() => []),
      ]);
      setKpis(kpiData);
      setHealth(healthData);
      setAlerts(Array.isArray(alertData) ? alertData : []);
      setCampaigns(Array.isArray(campData) ? campData : []);
      setTrends(Array.isArray(trendData) ? trendData : []);
      setCampaignSummary(summaryData);
      setRecCount(Array.isArray(recsData) ? recsData.length : 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  const chartData = useMemo(() => {
    return trends.map((d: any) => ({
      date: d.date?.slice(5) || "",
      clicks: d.clicks || 0,
      cost: Math.round((d.cost || 0) * 100) / 100,
      conversions: d.conversions || 0,
      impressions: d.impressions || 0,
    }));
  }, [trends]);

  // ── Fix My Ads: triggers operator scan on first connected account ──────
  const handleFixMyAds = useCallback(async () => {
    setScanning(true);
    setScanStatus("Starting scan...");
    try {
      const accounts = await api.get("/api/ads/accounts");
      const valid = (Array.isArray(accounts) ? accounts : []).filter(
        (a: any) => a.customer_id && a.customer_id !== "pending"
      );
      if (valid.length === 0) {
        setScanStatus("No connected account found");
        setScanning(false);
        return;
      }
      const res = await api.post("/api/v2/operator/scan", {
        account_id: valid[0].id,
        date_range: `${days}d`,
        scan_goal: "full_review",
      });
      setScanStatus("Scanning your account...");
      // Poll until ready
      const poll = setInterval(async () => {
        try {
          const s = await api.get(`/api/v2/operator/scan/${res.scan_id}/status`);
          if (s.status === "ready") {
            clearInterval(poll);
            setScanning(false);
            window.location.href = `/operator?scan=${res.scan_id}`;
          } else if (s.status === "failed") {
            clearInterval(poll);
            setScanStatus("Scan failed");
            setScanning(false);
          } else {
            const labels: Record<string, string> = {
              queued: "Queued...",
              collecting_data: "Collecting data...",
              analyzing: "Analyzing account...",
              generating_recommendations: "Finding problems...",
              building_projections: "Calculating savings...",
              running_creative_audit: "Reviewing ads...",
            };
            setScanStatus(labels[s.status] || s.status);
          }
        } catch { /* retry */ }
      }, 2000);
    } catch (e: any) {
      setScanStatus(e.message || "Failed to start scan");
      setScanning(false);
    }
  }, [days]);

  // ── Stop Waste: triggers scan with reduce_waste goal ────────────────────
  const handleStopWaste = useCallback(async () => {
    setScanning(true);
    setScanStatus("Analyzing waste...");
    try {
      const accounts = await api.get("/api/ads/accounts");
      const valid = (Array.isArray(accounts) ? accounts : []).filter(
        (a: any) => a.customer_id && a.customer_id !== "pending"
      );
      if (valid.length === 0) { setScanning(false); return; }
      const res = await api.post("/api/v2/operator/scan", {
        account_id: valid[0].id,
        date_range: `${days}d`,
        scan_goal: "reduce_waste",
      });
      const poll = setInterval(async () => {
        try {
          const s = await api.get(`/api/v2/operator/scan/${res.scan_id}/status`);
          if (s.status === "ready") {
            clearInterval(poll);
            setScanning(false);
            window.location.href = `/operator?scan=${res.scan_id}`;
          } else if (s.status === "failed") {
            clearInterval(poll);
            setScanning(false);
          }
        } catch { /* retry */ }
      }, 2000);
    } catch {
      setScanning(false);
    }
  }, [days]);

  const kpiCards = kpis
    ? [
        { label: "Spend", value: formatCurrency(kpis.cost), icon: DollarSign, color: "text-orange-600", bg: "bg-orange-50" },
        { label: "Revenue", value: formatCurrency(kpis.conv_value || 0), icon: Banknote, color: "text-emerald-600", bg: "bg-emerald-50" },
        { label: "Conversions", value: kpis.conversions.toFixed(1), icon: PhoneCall, color: "text-purple-600", bg: "bg-purple-50" },
        { label: "ROAS", value: `${kpis.roas?.toFixed(1) || "0.0"}x`, icon: TrendingUp, color: "text-blue-600", bg: "bg-blue-50" },
        { label: "CPA", value: formatCurrency(kpis.cpa), icon: Target, color: "text-red-600", bg: "bg-red-50" },
        { label: "Clicks", value: formatNumber(kpis.clicks), icon: MousePointerClick, color: "text-green-600", bg: "bg-green-50" },
        { label: "CTR", value: formatPercent(kpis.ctr), icon: BarChart3, color: "text-indigo-600", bg: "bg-indigo-50" },
        { label: "CPC", value: formatCurrency(kpis.cpc), icon: DollarSign, color: "text-slate-600", bg: "bg-slate-50" },
      ]
    : [];

  const chartColors: Record<string, string> = {
    clicks: "#22c55e",
    cost: "#f97316",
    conversions: "#8b5cf6",
  };

  const modeInfo = MODE_LABELS[health?.account_status?.autonomy_mode || "suggest"] || MODE_LABELS.suggest;

  return (
    <AppLayout>
      <div className="space-y-8">

        {/* ── STATUS HERO ─────────────────────────────────────────────── */}
        {!loading && kpis && (
          <div className="rounded-3xl bg-gradient-to-br from-[#1a1a2e] via-[#16213e] to-[#0f3460] p-8 text-white relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(99,102,241,0.15),transparent_50%)]" />
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h1 className="text-[22px] font-semibold tracking-tight">Your Ads at a Glance</h1>
                  <p className="text-white/40 text-[13px] mt-0.5">Performance overview for the last {days} days</p>
                </div>
                <div className="flex items-center gap-1.5 bg-white/[0.08] backdrop-blur-sm rounded-2xl p-1">
                  <Calendar className="w-3.5 h-3.5 text-white/30 ml-2.5" />
                  {DATE_RANGES.map((r) => (
                    <button
                      key={r.value}
                      onClick={() => setDays(r.value)}
                      className={`px-3 py-1.5 rounded-xl text-[12px] font-medium transition-all duration-200 ${
                        days === r.value ? "bg-white text-slate-900 shadow-sm" : "text-white/50 hover:text-white/80"
                      }`}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-8">
                <div className="flex items-center gap-4">
                  <div className="w-11 h-11 rounded-2xl bg-emerald-500/15 flex items-center justify-center ring-1 ring-emerald-500/20">
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div>
                    <p className="text-[13px] text-white/40 font-medium">Ads Status</p>
                    <p className="text-[17px] font-semibold tracking-tight mt-0.5">
                      {(health?.account_status?.campaigns_enabled || 0) > 0 ? "Running" : "No Active Ads"}
                      {(health?.account_status?.campaigns_enabled || 0) > 0 && (
                        <span className="text-emerald-400/70 ml-1.5 text-[13px] font-normal">
                          {health?.account_status?.campaigns_enabled} campaigns
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-11 h-11 rounded-2xl bg-blue-500/15 flex items-center justify-center ring-1 ring-blue-500/20">
                    <Brain className="w-5 h-5 text-blue-400" />
                  </div>
                  <div>
                    <p className="text-[13px] text-white/40 font-medium">AI Optimizer</p>
                    <p className="text-[17px] font-semibold tracking-tight mt-0.5">
                      <span className={health?.account_status?.autonomy_mode === "full_auto" ? "text-emerald-400" : health?.account_status?.autonomy_mode === "semi_auto" ? "text-blue-400" : "text-amber-400"}>
                        {modeInfo.label}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-11 h-11 rounded-2xl bg-amber-500/15 flex items-center justify-center ring-1 ring-amber-500/20">
                    <TrendingUp className="w-5 h-5 text-amber-400" />
                  </div>
                  <div>
                    <p className="text-[13px] text-white/40 font-medium">Revenue ({days}d)</p>
                    <p className="text-[17px] font-semibold tracking-tight mt-0.5">
                      {formatCurrency(kpis.conv_value || 0)}
                      {kpis.roas > 0 && (
                        <span className="text-emerald-400/70 ml-1.5 text-[13px] font-normal">{kpis.roas.toFixed(1)}x ROAS</span>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── ACTION CARDS ─────────────────────────────────────────── */}
        {!loading && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card className="border-0 bg-gradient-to-br from-blue-50/80 to-indigo-50/40 hover:premium-shadow-lg transition-all duration-300">
              <CardContent className="p-7">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-2xl bg-blue-100 flex items-center justify-center">
                    <Brain className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight">Fix My Ads</h2>
                    <p className="text-[12px] text-slate-400">AI-powered account audit</p>
                  </div>
                </div>
                <p className="text-[13px] text-slate-500 leading-relaxed mb-4">
                  Scans your entire account for wasted keywords, underperforming ads, budget issues, and missed opportunities.
                </p>
                {health && health.problems_found > 0 && !scanning && (
                  <div className="flex items-center gap-2 text-[13px] font-medium text-red-600 bg-red-50 rounded-xl px-3.5 py-2.5 mb-4">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                    {health.problems_found} problems — {formatCurrency(health.total_wasted_spend)} wasted
                  </div>
                )}
                {health && health.problems_found === 0 && !scanning && (
                  <div className="flex items-center gap-2 text-[13px] font-medium text-emerald-600 bg-emerald-50 rounded-xl px-3.5 py-2.5 mb-4">
                    <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> Account looks healthy
                  </div>
                )}
                {scanning && (
                  <div className="flex items-center gap-2.5 text-[13px] text-blue-600 bg-blue-50/80 rounded-xl px-3.5 py-2.5 mb-4">
                    <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" /> {scanStatus}
                  </div>
                )}
                <Button
                  onClick={handleFixMyAds}
                  disabled={scanning}
                  className="bg-blue-600 hover:bg-blue-700 text-white h-11 text-[13px] font-semibold w-full rounded-xl"
                >
                  {scanning ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Scanning...</>
                  ) : (
                    <><Zap className="w-4 h-4 mr-2" /> Fix My Ads</>
                  )}
                </Button>
              </CardContent>
            </Card>

            <Card className="border-0 bg-gradient-to-br from-red-50/60 to-orange-50/30 hover:premium-shadow-lg transition-all duration-300">
              <CardContent className="p-7">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-2xl bg-red-100 flex items-center justify-center">
                      <Flame className="w-5 h-5 text-red-500" />
                    </div>
                    <div>
                      <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight">Wasted Spend</h2>
                      <p className="text-[12px] text-slate-400">Last {days} days</p>
                    </div>
                  </div>
                </div>
                {health ? (
                  <>
                    <div className="text-[32px] font-bold text-red-600 tracking-tight mb-4">
                      {formatCurrency(health.total_wasted_spend)}
                    </div>
                    <div className="space-y-2.5 mb-5">
                      {health.wasted_spend.keywords.count > 0 && (
                        <div className="flex items-center justify-between text-[13px]">
                          <span className="text-slate-500">{health.wasted_spend.keywords.count} wasted keywords</span>
                          <span className="font-semibold text-red-600">{formatCurrency(health.wasted_spend.keywords.cost)}</span>
                        </div>
                      )}
                      {health.wasted_spend.search_terms.count > 0 && (
                        <div className="flex items-center justify-between text-[13px]">
                          <span className="text-slate-500">{health.wasted_spend.search_terms.count} bad search terms</span>
                          <span className="font-semibold text-red-600">{formatCurrency(health.wasted_spend.search_terms.cost)}</span>
                        </div>
                      )}
                      {health.wasted_spend.low_ctr_ads.count > 0 && (
                        <div className="flex items-center justify-between text-[13px]">
                          <span className="text-slate-500">{health.wasted_spend.low_ctr_ads.count} low CTR ads</span>
                          <span className="font-semibold text-red-600">{formatCurrency(health.wasted_spend.low_ctr_ads.cost)}</span>
                        </div>
                      )}
                      {health.wasted_spend.budget_limited.count > 0 && (
                        <div className="flex items-center justify-between text-[13px]">
                          <span className="text-slate-500">{health.wasted_spend.budget_limited.count} budget-limited</span>
                          <span className="font-medium text-amber-600">Limited</span>
                        </div>
                      )}
                      {health.total_wasted_spend === 0 && (
                        <div className="flex items-center gap-2 text-[13px] text-emerald-600">
                          <CheckCircle2 className="w-4 h-4" /> No significant waste detected
                        </div>
                      )}
                    </div>
                    <Button
                      onClick={handleStopWaste}
                      disabled={scanning || health.total_wasted_spend === 0}
                      variant={health.total_wasted_spend > 0 ? "default" : "outline"}
                      className={health.total_wasted_spend > 0 ? "bg-red-600 hover:bg-red-700 text-white w-full h-11 text-[13px] font-semibold rounded-xl" : "w-full h-11 text-[13px] rounded-xl"}
                    >
                      <Shield className="w-4 h-4 mr-2" /> Stop Waste
                    </Button>
                  </>
                ) : (
                  <div className="h-32 flex items-center justify-center">
                    <Loader2 className="w-5 h-5 animate-spin text-slate-300" />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* ── KPI CARDS ─────────────────────────────────────────────── */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
            {[...Array(8)].map((_, i) => (
              <Card key={i} className="animate-pulse border-0">
                <CardContent className="p-6">
                  <div className="h-3 bg-slate-100 rounded-full w-16 mb-3" />
                  <div className="h-7 bg-slate-100 rounded-xl w-24" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
            {kpiCards.map((kpi) => {
              const Icon = kpi.icon;
              return (
                <Card key={kpi.label} className="border-0 hover:premium-shadow-lg transition-all duration-300 group">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[13px] text-slate-400 font-medium">{kpi.label}</span>
                      <div className={`w-9 h-9 rounded-xl ${kpi.bg} flex items-center justify-center transition-transform duration-200 group-hover:scale-110`}>
                        <Icon className={`w-[18px] h-[18px] ${kpi.color}`} />
                      </div>
                    </div>
                    <div className="text-[24px] font-semibold tracking-tight text-slate-900">{kpi.value}</div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {/* ── QUICK ACTIONS ─────────────────────────────────────────── */}
        {(recCount > 0 || alerts.length > 0) && (
          <div className="flex gap-5">
            {recCount > 0 && (
              <div
                onClick={() => (window.location.href = "/ads/recommendations")}
                className="flex-1 flex items-center gap-4 px-5 py-4 rounded-2xl bg-blue-50/70 border border-blue-100/60 cursor-pointer hover:bg-blue-50 transition-all duration-200 group"
              >
                <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
                  <Lightbulb className="w-5 h-5 text-blue-600" />
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-[14px] text-blue-900">{recCount} Google Recommendations</p>
                  <p className="text-[12px] text-blue-600/60">Review and apply to improve performance</p>
                </div>
                <ArrowRight className="w-4 h-4 text-blue-300 group-hover:translate-x-0.5 transition-transform" />
              </div>
            )}
            {alerts.length > 0 && (
              <div className="flex-1 flex items-center gap-4 px-5 py-4 rounded-2xl bg-amber-50/70 border border-amber-100/60">
                <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-amber-600" />
                </div>
                <div>
                  <p className="font-semibold text-[14px] text-amber-900">{alerts.length} Active Alerts</p>
                  <p className="text-[12px] text-amber-600/60">{alerts[0]?.message}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── MONEY KEYWORDS ──────────────────────────────────────── */}
        {health && health.money_keywords.length > 0 && (
          <Card className="border-0 overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between pb-0">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-amber-50 flex items-center justify-center">
                  <Star className="w-4 h-4 text-amber-500" />
                </div>
                <div>
                  <CardTitle className="text-[15px] tracking-tight">Money Keywords</CardTitle>
                  <p className="text-[12px] text-slate-400 mt-0.5">Top revenue generators</p>
                </div>
              </div>
              <Button variant="ghost" size="sm" className="text-[13px] text-slate-400 hover:text-slate-600" onClick={() => (window.location.href = "/ads/keywords")}>
                View All <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </CardHeader>
            <CardContent className="pt-4">
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="pb-3 text-left font-medium text-slate-400">Keyword</th>
                      <th className="pb-3 text-right font-medium text-slate-400">Spend</th>
                      <th className="pb-3 text-right font-medium text-slate-400">Revenue</th>
                      <th className="pb-3 text-right font-medium text-slate-400">ROAS</th>
                      <th className="pb-3 text-right font-medium text-slate-400">Conv.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.money_keywords.slice(0, 5).map((kw: any, i: number) => (
                      <tr key={kw.keyword_id || i} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50 transition-colors">
                        <td className="py-3 font-medium text-slate-800">{kw.keyword}</td>
                        <td className="py-3 text-right text-slate-500">{formatCurrency(kw.spend)}</td>
                        <td className="py-3 text-right font-semibold text-emerald-600">{formatCurrency(kw.revenue)}</td>
                        <td className="py-3 text-right">
                          <span className={`inline-flex px-2 py-0.5 rounded-lg text-[11px] font-semibold ${
                            kw.roas >= 5 ? "bg-emerald-50 text-emerald-600" :
                            kw.roas >= 2 ? "bg-blue-50 text-blue-600" :
                            "bg-amber-50 text-amber-600"
                          }`}>{kw.roas.toFixed(1)}x</span>
                        </td>
                        <td className="py-3 text-right text-slate-500">{kw.conversions.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ── PERFORMANCE CHART ─────────────────────────────────────── */}
        {chartData.length > 0 && (
          <Card className="border-0 overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between pb-0">
              <CardTitle className="text-[15px] tracking-tight">Daily Performance</CardTitle>
              <div className="flex gap-1 bg-slate-100/80 rounded-xl p-1">
                {(["clicks", "cost", "conversions"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setChartMetric(m)}
                    className={`px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all duration-200 capitalize ${
                      chartMetric === m
                        ? "bg-white text-slate-900 shadow-sm"
                        : "text-slate-400 hover:text-slate-600"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="colorMetric" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={chartColors[chartMetric]} stopOpacity={0.15} />
                      <stop offset="95%" stopColor={chartColors[chartMetric]} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="0" stroke="#f1f5f9" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#94a3b8" }} stroke="transparent" />
                  <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} stroke="transparent" />
                  <Tooltip
                    contentStyle={{ borderRadius: "12px", border: "none", boxShadow: "0 4px 20px rgba(0,0,0,0.08)", fontSize: "13px" }}
                    formatter={(value: any) =>
                      chartMetric === "cost" ? `$${value}` : value
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey={chartMetric}
                    stroke={chartColors[chartMetric]}
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#colorMetric)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Campaign Status Summary */}
          {campaignSummary && (
            <Card className="border-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-[15px] tracking-tight">Campaign Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(campaignSummary).map(([status, count]: [string, any]) => (
                    <div key={status} className="text-center p-4 bg-slate-50/80 rounded-2xl">
                      <div className="text-[11px] text-slate-400 uppercase tracking-wider font-medium">{status}</div>
                      <div className="text-[22px] font-semibold tracking-tight mt-1 text-slate-900">{count}</div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Cost per campaign bar chart */}
          {campaigns.length > 0 && (
            <Card className="border-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-[15px] tracking-tight">Cost by Campaign</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart
                    data={campaigns.slice(0, 6).map((c: any) => ({
                      name: c.name?.length > 18 ? c.name.slice(0, 18) + "..." : c.name,
                      cost: c.cost || 0,
                      conversions: c.conversions || 0,
                    }))}
                    layout="vertical"
                  >
                    <CartesianGrid strokeDasharray="0" stroke="#f1f5f9" vertical={false} />
                    <XAxis type="number" tick={{ fontSize: 11, fill: "#94a3b8" }} stroke="transparent" />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} width={120} stroke="transparent" />
                    <Tooltip
                      contentStyle={{ borderRadius: "12px", border: "none", boxShadow: "0 4px 20px rgba(0,0,0,0.08)", fontSize: "13px" }}
                      formatter={(value: any) => `$${value.toFixed(2)}`}
                    />
                    <Bar dataKey="cost" fill="#f97316" radius={[0, 6, 6, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>

        {/* ── CAMPAIGN TABLE ──────────────────────────────────────── */}
        <Card className="border-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between pb-0">
            <CardTitle className="text-[15px] tracking-tight">Campaign Summary</CardTitle>
            <Button variant="ghost" size="sm" className="text-[13px] text-slate-400 hover:text-slate-600" onClick={() => (window.location.href = "/ads/campaigns")}>
              View All <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          </CardHeader>
          <CardContent className="pt-4">
            {campaigns.length === 0 ? (
              <p className="text-slate-400 text-[13px]">No campaigns found. Use the Command Console to create your first campaign.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="pb-3 text-left font-medium text-slate-400">Campaign</th>
                      <th className="pb-3 text-left font-medium text-slate-400">Status</th>
                      <th className="pb-3 text-right font-medium text-slate-400">Clicks</th>
                      <th className="pb-3 text-right font-medium text-slate-400">Cost</th>
                      <th className="pb-3 text-right font-medium text-slate-400">Conv.</th>
                      <th className="pb-3 text-right font-medium text-slate-400">CPA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.map((c: any) => (
                      <tr key={c.campaign_id || c.name} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50 cursor-pointer transition-colors"
                        onClick={() => c.id && (window.location.href = `/ads/campaigns/${c.id}`)}>
                        <td className="py-3 font-medium text-slate-800">{c.name}</td>
                        <td className="py-3">
                          <span className={`inline-flex px-2.5 py-0.5 rounded-lg text-[11px] font-semibold ${
                            c.status === "ENABLED" ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500"
                          }`}>
                            {c.status}
                          </span>
                        </td>
                        <td className="py-3 text-right text-slate-500">{formatNumber(c.clicks || 0)}</td>
                        <td className="py-3 text-right text-slate-500">{formatCurrency(c.cost || 0)}</td>
                        <td className="py-3 text-right text-slate-500">{(c.conversions || 0).toFixed(1)}</td>
                        <td className="py-3 text-right text-slate-500">{formatCurrency(c.cpa || 0)}</td>
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
