"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Search, AlertTriangle, Ban, Plus, DollarSign, Loader2 } from "lucide-react";

export default function SearchTermsPage() {
  const [terms, setTerms] = useState<any[]>([]);
  const [waste, setWaste] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [showWaste, setShowWaste] = useState(false);
  const [days, setDays] = useState(30);
  const [adding, setAdding] = useState<string | null>(null);

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

  const displayed = showWaste
    ? filtered.filter((t) => t.conversions === 0 && t.cost > 5)
    : filtered;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Search Terms</h1>
          <p className="text-muted-foreground">
            Analyze what people are actually searching for when your ads show
          </p>
        </div>

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
                    Add these as negative keywords to stop wasting budget
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
                      <th className="text-right p-3 font-medium">Impr.</th>
                      <th className="text-right p-3 font-medium">Clicks</th>
                      <th className="text-right p-3 font-medium">Cost</th>
                      <th className="text-right p-3 font-medium">Conv.</th>
                      <th className="text-right p-3 font-medium">CTR</th>
                      <th className="text-right p-3 font-medium">CPC</th>
                      <th className="text-right p-3 font-medium">CPA</th>
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
