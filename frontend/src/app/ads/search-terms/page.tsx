"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Search, AlertTriangle, AlertCircle, Ban, Plus, DollarSign, Loader2, ArrowUp, ArrowDown, ArrowUpDown, Info, ExternalLink } from "lucide-react";
import { HelpTip, PageInfo } from "@/components/ui/help-tip";

type SortKey = "impressions" | "clicks" | "cost" | "conversions" | "ctr" | "cpc" | "cpa";
type SortDir = "asc" | "desc";

export default function SearchTermsPage() {
  const [terms, setTerms] = useState<any[]>([]);
  const [waste, setWaste] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [showWaste, setShowWaste] = useState(false);
  const [days, setDays] = useState(30);
  const [adding, setAdding] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("cost");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    loadData();
  }, [days]);

  async function loadData() {
    setLoading(true);
    try {
      const [t, w] = await Promise.all([
        api.get(`/api/ads/search-terms?days=${days}&limit=100`),
        api.get(`/api/ads/search-terms/waste?days=${days}`),
      ]);
      setTerms(Array.isArray(t) ? t : []);
      setWaste(w);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function addNegative(term: any) {
    setAdding(term.search_term);
    try {
      await api.post("/api/ads/negative-keywords", {
        campaign_id: term.campaign_id,
        keywords: [term.search_term],
      });
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setAdding(null);
    }
  }

  const filtered = terms.filter(
    (t) =>
      !filter || t.search_term.toLowerCase().includes(filter.toLowerCase())
  );

  const afterWaste = showWaste
    ? filtered.filter((t) => t.conversions === 0 && t.cost > 5)
    : filtered;

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(sortDir === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  }
  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ArrowUpDown className="w-3 h-3 text-slate-300" />;
    return sortDir === "desc" ? <ArrowDown className="w-3 h-3 text-blue-600" /> : <ArrowUp className="w-3 h-3 text-blue-600" />;
  }

  const displayed = [...afterWaste].sort((a, b) => {
    const av = a[sortKey] || 0, bv = b[sortKey] || 0;
    return sortDir === "desc" ? bv - av : av - bv;
  });

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Search Terms</h1>
          <p className="text-muted-foreground">
            Analyze what people are actually searching for when your ads show
          </p>
        </div>

        <PageInfo term="page_search_terms" />

        {/* Conversion Tracking Warning */}
        {waste?.conversion_tracking && waste.conversion_tracking.status !== "healthy" && (
          <Card className={`${
            waste.conversion_tracking.status === "not_setup" ? "border-orange-300 bg-orange-50" :
            waste.conversion_tracking.status === "all_disabled" ? "border-orange-300 bg-orange-50" :
            "border-yellow-300 bg-yellow-50"
          }`}>
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className={`w-5 h-5 mt-0.5 shrink-0 ${
                  waste.conversion_tracking.status === "not_setup" ? "text-orange-600" :
                  waste.conversion_tracking.status === "all_disabled" ? "text-orange-600" :
                  "text-yellow-600"
                }`} />
                <div className="flex-1">
                  <p className={`font-semibold ${
                    waste.conversion_tracking.status === "not_setup" ? "text-orange-900" :
                    waste.conversion_tracking.status === "all_disabled" ? "text-orange-900" :
                    "text-yellow-900"
                  }`}>
                    {waste.conversion_tracking.status === "not_setup" && "Conversion Tracking Not Set Up"}
                    {waste.conversion_tracking.status === "all_disabled" && "All Conversion Actions Disabled"}
                    {waste.conversion_tracking.status === "no_data" && "No Conversions Recorded"}
                  </p>
                  <p className={`text-sm mt-1 ${
                    waste.conversion_tracking.status === "not_setup" ? "text-orange-700" :
                    waste.conversion_tracking.status === "all_disabled" ? "text-orange-700" :
                    "text-yellow-700"
                  }`}>
                    {waste.conversion_tracking.message}
                  </p>
                  {waste.conversion_tracking.status !== "healthy" && (
                    <p className="text-xs mt-2 text-slate-500">
                      <Info className="w-3 h-3 inline mr-1" />
                      The &quot;wasted spend&quot; numbers below may be inaccurate until conversion tracking is working correctly.
                      Without proper tracking, all search terms appear to have zero conversions.
                    </p>
                  )}
                  <div className="flex items-center gap-4 mt-2 text-xs">
                    <span className="text-slate-500">
                      Conversion actions: {waste.conversion_tracking.active_actions} active / {waste.conversion_tracking.total_actions} total
                    </span>
                    <span className="text-slate-500">
                      Conversions in period: {waste.conversion_tracking.conversions_in_period}
                    </span>
                    <Button variant="outline" size="sm" className="h-6 text-xs" onClick={() => window.location.href = "/settings"}>
                      <ExternalLink className="w-3 h-3 mr-1" /> Check Settings
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Waste Summary */}
        {waste && waste.total_waste > 0 && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-red-600" />
                <div>
                  <p className="font-semibold text-red-900">
                    ${waste.total_waste.toLocaleString()} wasted on{" "}
                    {waste.count} search terms with zero conversions
                  </p>
                  <p className="text-sm text-red-700">
                    {waste.conversion_tracking?.status === "healthy"
                      ? "Add these as negative keywords to stop wasting budget"
                      : "This may be due to missing conversion tracking \u2014 verify your setup before adding negative keywords"}
                  </p>
                </div>
              </div>
              <Button
                variant={showWaste ? "default" : "outline"}
                size="sm"
                onClick={() => setShowWaste(!showWaste)}
              >
                {showWaste ? "Show All" : "Show Wasted Only"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Filters */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Filter search terms..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="pl-9"
            />
          </div>
          <select
            className="border rounded-md px-3 py-2 text-sm"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>

        {/* Table */}
        {loading ? (
          <Card>
            <CardContent className="p-8 text-center">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">Loading search terms...</p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-slate-50">
                      <th className="text-left p-3 font-medium">Search Term</th>
                      <th className="text-left p-3 font-medium">Keyword</th>
                      {([
                        { key: "impressions" as SortKey, label: "Impr." },
                        { key: "clicks" as SortKey, label: "Clicks" },
                        { key: "cost" as SortKey, label: "Cost" },
                        { key: "conversions" as SortKey, label: "Conv." },
                        { key: "ctr" as SortKey, label: "CTR" },
                        { key: "cpc" as SortKey, label: "CPC" },
                        { key: "cpa" as SortKey, label: "CPA" },
                      ] as const).map(({ key, label }) => (
                        <th key={key} className="text-right p-3 font-medium">
                          <button onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 hover:text-blue-600 transition-colors">
                            {label} <SortIcon col={key} />
                          </button>
                        </th>
                      ))}
                      <th className="p-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayed.map((t, i) => (
                      <tr
                        key={i}
                        className={`border-b hover:bg-slate-50 ${
                          t.conversions === 0 && t.cost > 5
                            ? "bg-red-50/50"
                            : ""
                        }`}
                      >
                        <td className="p-3 font-medium max-w-[300px] truncate">
                          {t.search_term}
                        </td>
                        <td className="p-3 text-muted-foreground max-w-[200px] truncate">
                          {t.keyword_text || "—"}
                        </td>
                        <td className="p-3 text-right">
                          {t.impressions?.toLocaleString()}
                        </td>
                        <td className="p-3 text-right">
                          {t.clicks?.toLocaleString()}
                        </td>
                        <td className="p-3 text-right font-medium">
                          ${t.cost?.toFixed(2)}
                        </td>
                        <td className="p-3 text-right">
                          {t.conversions === 0 ? (
                            <span className="text-red-600">0</span>
                          ) : (
                            t.conversions?.toFixed(1)
                          )}
                        </td>
                        <td className="p-3 text-right">{t.ctr?.toFixed(2)}%</td>
                        <td className="p-3 text-right">${t.cpc?.toFixed(2)}</td>
                        <td className="p-3 text-right">
                          {t.cpa ? `$${t.cpa.toFixed(2)}` : "—"}
                        </td>
                        <td className="p-3 text-right">
                          <div className="flex gap-1 justify-end">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs text-red-600 hover:text-red-700"
                              onClick={() => addNegative(t)}
                              disabled={adding === t.search_term}
                            >
                              {adding === t.search_term ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <>
                                  <Ban className="w-3 h-3 mr-1" /> Neg
                                </>
                              )}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {displayed.length === 0 && (
                      <tr>
                        <td colSpan={10} className="p-8 text-center text-muted-foreground">
                          No search terms found. Sync your account first.
                        </td>
                      </tr>
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
