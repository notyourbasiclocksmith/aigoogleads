"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Pause, Play, Trophy, AlertTriangle, Loader2, ExternalLink, Eye, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";

type SortKey = "impressions" | "clicks" | "cost" | "conversions" | "ctr" | "cpc";
type SortDir = "asc" | "desc";

export default function AdPerformancePage() {
  const [ads, setAds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("cost");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    loadData();
  }, [days]);

  async function loadData() {
    setLoading(true);
    try {
      const data = await api.get(`/api/ads/ads/performance?days=${days}&limit=100`);
      setAds(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function toggleAdStatus(ad: any) {
    const newStatus = ad.status === "ENABLED" ? "PAUSED" : "ENABLED";
    setActionLoading(ad.ad_id);
    try {
      await api.patch(`/api/ads/ads/${ad.ad_id}/status`, { status: newStatus });
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  }

  // Determine best and worst ads
  const bySortKey = [...ads].sort((a, b) => {
    const av = a[sortKey] || 0, bv = b[sortKey] || 0;
    return sortDir === "desc" ? bv - av : av - bv;
  });
  const byConv = [...ads].sort((a, b) => (b.conversions || 0) - (a.conversions || 0));
  const bestAdId = byConv.length > 0 ? byConv[0].ad_id : null;
  const worstAdId = byConv.length > 1 ? byConv[byConv.length - 1].ad_id : null;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ad Performance</h1>
          <p className="text-muted-foreground">Compare ad performance and identify winners and losers</p>
        </div>

        <div className="flex items-center gap-3">
          <select className="border rounded-md px-3 py-2 text-sm" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <select className="border rounded-md px-3 py-2 text-sm" value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
            <option value="cost">Sort: Cost</option>
            <option value="impressions">Sort: Impressions</option>
            <option value="clicks">Sort: Clicks</option>
            <option value="conversions">Sort: Conversions</option>
            <option value="ctr">Sort: CTR</option>
            <option value="cpc">Sort: CPC</option>
          </select>
          <button
            onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
            className="inline-flex items-center gap-1 border rounded-md px-3 py-2 text-sm hover:bg-slate-50 transition-colors"
          >
            {sortDir === "desc" ? <ArrowDown className="w-3.5 h-3.5 text-blue-600" /> : <ArrowUp className="w-3.5 h-3.5 text-blue-600" />}
            {sortDir === "desc" ? "High → Low" : "Low → High"}
          </button>
        </div>

        {loading ? (
          <Card><CardContent className="p-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" /><p className="text-muted-foreground">Loading ads...</p></CardContent></Card>
        ) : ads.length === 0 ? (
          <Card><CardContent className="p-12 text-center"><p className="text-muted-foreground">No ad performance data. Sync your account first.</p></CardContent></Card>
        ) : (
          <div className="space-y-4">
            {bySortKey.map((ad: any) => (
              <Card key={ad.ad_id} className={`${ad.ad_id === bestAdId ? "border-green-300 bg-green-50/30" : ad.ad_id === worstAdId ? "border-red-200 bg-red-50/30" : ""}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        {ad.ad_id === bestAdId && (
                          <Badge className="bg-green-100 text-green-800 border-green-200">
                            <Trophy className="w-3 h-3 mr-1" /> Best Performer
                          </Badge>
                        )}
                        {ad.ad_id === worstAdId && ads.length > 1 && (
                          <Badge className="bg-red-100 text-red-800 border-red-200">
                            <AlertTriangle className="w-3 h-3 mr-1" /> Worst Performer
                          </Badge>
                        )}
                        {ad.status && (
                          <Badge variant={ad.status === "ENABLED" ? "default" : "secondary"}>
                            {ad.status}
                          </Badge>
                        )}
                        <span className="text-xs text-muted-foreground">Ad ID: {ad.ad_id}</span>
                      </div>

                      {/* Headlines */}
                      {ad.headlines && ad.headlines.length > 0 && (
                        <div className="mb-1">
                          {ad.final_urls && ad.final_urls.length > 0 ? (
                            <a
                              href={ad.final_urls[0]}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-medium text-blue-700 hover:underline hover:text-blue-900"
                            >
                              {ad.headlines.slice(0, 3).join(" | ")}
                            </a>
                          ) : (
                            <p className="text-sm font-medium text-blue-700">
                              {ad.headlines.slice(0, 3).join(" | ")}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Descriptions */}
                      {ad.descriptions && ad.descriptions.length > 0 && (
                        <p className="text-sm text-slate-600 mb-1">{ad.descriptions[0]}</p>
                      )}

                      {/* Final URL */}
                      {ad.final_urls && ad.final_urls.length > 0 && (
                        <a
                          href={ad.final_urls[0]}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-green-700 hover:text-green-900 hover:underline inline-flex items-center gap-1 mb-3"
                        >
                          {ad.final_urls[0]}
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}

                      {/* Action links */}
                      <div className="flex items-center gap-3 mb-3">
                        {ad.final_urls && ad.final_urls.length > 0 && (
                          <a
                            href={ad.final_urls[0]}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline"
                          >
                            <Eye className="w-3 h-3" /> Preview Landing Page
                          </a>
                        )}
                        <a
                          href={`https://ads.google.com/aw/ads/versions?adId=${ad.ad_id}&adGroupId=${ad.ad_group_id}&campaignId=${ad.campaign_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-800 hover:underline"
                        >
                          <ExternalLink className="w-3 h-3" /> View in Google Ads
                        </a>
                      </div>

                      {/* Metrics */}
                      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                        <div>
                          <div className="text-xs text-muted-foreground">Impressions</div>
                          <div className="font-medium">{(ad.impressions || 0).toLocaleString()}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Clicks</div>
                          <div className="font-medium">{(ad.clicks || 0).toLocaleString()}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Cost</div>
                          <div className="font-medium">${(ad.cost || 0).toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Conversions</div>
                          <div className={`font-medium ${ad.conversions === 0 ? "text-red-600" : "text-green-600"}`}>
                            {(ad.conversions || 0).toFixed(1)}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">CTR</div>
                          <div className="font-medium">{(ad.ctr || 0).toFixed(2)}%</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">CPC</div>
                          <div className="font-medium">${(ad.cpc || 0).toFixed(2)}</div>
                        </div>
                      </div>
                    </div>
                    <div className="ml-4">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => toggleAdStatus(ad)}
                        disabled={actionLoading === ad.ad_id}
                        title={ad.status === "ENABLED" ? "Pause ad" : "Enable ad"}
                      >
                        {actionLoading === ad.ad_id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : ad.status === "ENABLED" ? (
                          <Pause className="w-4 h-4" />
                        ) : (
                          <Play className="w-4 h-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
