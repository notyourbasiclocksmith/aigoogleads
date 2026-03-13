"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import { Pause, Play, ExternalLink, ArrowUp, ArrowDown } from "lucide-react";
import { HelpTip, PageInfo } from "@/components/ui/help-tip";
import { CSVExportButton } from "@/components/ui/csv-export-button";

type SortKey = "impressions" | "clicks" | "ctr" | "conversions" | "cpa" | "budget_micros";
type SortDir = "asc" | "desc";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>("clicks");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    api.get("/api/campaigns").then(setCampaigns).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function togglePause(campaignId: string, currentStatus: string) {
    try {
      if (currentStatus === "ENABLED") {
        await api.post(`/api/campaigns/${campaignId}/pause`);
      } else {
        await api.post(`/api/campaigns/${campaignId}/enable`);
      }
      const updated = await api.get("/api/campaigns");
      setCampaigns(updated);
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Campaigns</h1>
            <p className="text-muted-foreground">Manage and monitor your Google Ads campaigns</p>
          </div>
          <div className="flex items-center gap-2">
            <CSVExportButton entityType="campaigns" days={30} />
            <Button onClick={() => (window.location.href = "/ads/prompt")}>
              + New Campaign
            </Button>
          </div>
        </div>

        <PageInfo term="page_campaigns" />

        <div className="flex items-center gap-3">
          <select className="border rounded-md px-3 py-2 text-sm" value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
            <option value="clicks">Sort: Clicks</option>
            <option value="impressions">Sort: Impressions</option>
            <option value="conversions">Sort: Conversions</option>
            <option value="ctr">Sort: CTR</option>
            <option value="cpa">Sort: CPA</option>
            <option value="budget_micros">Sort: Budget</option>
          </select>
          <button
            onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
            className="inline-flex items-center gap-1 border rounded-md px-3 py-2 text-sm hover:bg-slate-50 transition-colors"
          >
            {sortDir === "desc" ? <ArrowDown className="w-3.5 h-3.5 text-blue-600" /> : <ArrowUp className="w-3.5 h-3.5 text-blue-600" />}
            {sortDir === "desc" ? "High \u2192 Low" : "Low \u2192 High"}
          </button>
        </div>

        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6">
                  <div className="h-6 bg-slate-200 rounded w-64 mb-2" />
                  <div className="h-4 bg-slate-200 rounded w-48" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : campaigns.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <p className="text-muted-foreground">No campaigns yet. Use the Command Console to create your first campaign.</p>
              <Button className="mt-4" onClick={() => (window.location.href = "/ads/prompt")}>
                Create Campaign
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {[...campaigns].sort((a, b) => {
              const av = a[sortKey] || 0, bv = b[sortKey] || 0;
              return sortDir === "desc" ? bv - av : av - bv;
            }).map((c: any) => (
              <Card key={c.id || c.campaign_id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => (window.location.href = `/ads/campaigns/${c.id}`)}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold text-lg">{c.name}</h3>
                        <Badge variant={c.status === "ENABLED" ? "success" : c.status === "PAUSED" ? "warning" : "secondary"}>
                          {c.status}
                        </Badge>
                        <Badge variant="outline">{c.type}</Badge>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mt-3">
                        <div>
                          <div className="text-xs text-muted-foreground">Budget/day</div>
                          <div className="font-medium">{formatCurrency((c.budget_micros || 0) / 1_000_000)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Impressions</div>
                          <div className="font-medium">{formatNumber(c.impressions || 0)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Clicks</div>
                          <div className="font-medium">{formatNumber(c.clicks || 0)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">CTR</div>
                          <div className="font-medium">{formatPercent(c.ctr || 0)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">Conversions</div>
                          <div className="font-medium">{(c.conversions || 0).toFixed(1)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground">CPA</div>
                          <div className="font-medium">{formatCurrency(c.cpa || 0)}</div>
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e: any) => { e.stopPropagation(); togglePause(c.id, c.status); }}
                        title={c.status === "ENABLED" ? "Pause" : "Enable"}
                      >
                        {c.status === "ENABLED" ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e: any) => { e.stopPropagation(); window.location.href = `/ads/campaigns/${c.id}`; }}
                      >
                        <ExternalLink className="w-4 h-4" />
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
