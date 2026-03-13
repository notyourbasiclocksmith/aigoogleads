"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Pause, Play, Trophy, AlertTriangle, Loader2 } from "lucide-react";

export default function AdPerformancePage() {
  const [ads, setAds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

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
  const sorted = [...ads].sort((a, b) => (b.conversions || 0) - (a.conversions || 0));
  const bestAdId = sorted.length > 0 ? sorted[0].ad_id : null;
  const worstAdId = sorted.length > 1 ? sorted[sorted.length - 1].ad_id : null;

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
        </div>

        {loading ? (
          <Card><CardContent className="p-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" /><p className="text-muted-foreground">Loading ads...</p></CardContent></Card>
        ) : ads.length === 0 ? (
          <Card><CardContent className="p-12 text-center"><p className="text-muted-foreground">No ad performance data. Sync your account first.</p></CardContent></Card>
        ) : (
          <div className="space-y-4">
            {ads.map((ad: any) => (
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
                        <div className="mb-2">
                          <p className="text-sm font-medium text-blue-700">
                            {ad.headlines.slice(0, 3).join(" | ")}
                          </p>
                        </div>
                      )}

                      {/* Descriptions */}
                      {ad.descriptions && ad.descriptions.length > 0 && (
                        <p className="text-sm text-slate-600 mb-3">{ad.descriptions[0]}</p>
                      )}

                      {/* Final URL */}
                      {ad.final_urls && ad.final_urls.length > 0 && (
                        <p className="text-xs text-green-700 mb-3">{ad.final_urls[0]}</p>
                      )}

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
