"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import { Pause, Play, ExternalLink } from "lucide-react";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

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
          <Button onClick={() => (window.location.href = "/ads/prompt")}>
            + New Campaign
          </Button>
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
            {campaigns.map((c: any) => (
              <Card key={c.id || c.campaign_id}>
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
                        onClick={() => togglePause(c.id, c.status)}
                        title={c.status === "ENABLED" ? "Pause" : "Enable"}
                      >
                        {c.status === "ENABLED" ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => (window.location.href = `/ads/campaigns/${c.id}`)}
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
