"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import {
  ArrowLeft, Pause, Play, Target, Layers, Type,
  MousePointerClick, DollarSign, Eye, PhoneCall, TrendingUp,
  Hash, Star, ExternalLink,
} from "lucide-react";

export default function CampaignDetailPage() {
  const params = useParams();
  const campaignId = params.id as string;
  const [campaign, setCampaign] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/api/campaigns/${campaignId}`)
      .then(setCampaign)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [campaignId]);

  async function toggleStatus() {
    if (!campaign) return;
    try {
      if (campaign.status === "ENABLED") {
        await api.post(`/api/campaigns/${campaignId}/pause`);
      } else {
        await api.post(`/api/campaigns/${campaignId}/enable`);
      }
      const updated = await api.get(`/api/campaigns/${campaignId}`);
      setCampaign(updated);
    } catch (e) {
      console.error(e);
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6"><div className="h-24 bg-slate-200 rounded" /></CardContent>
            </Card>
          ))}
        </div>
      </AppLayout>
    );
  }

  if (!campaign) {
    return (
      <AppLayout>
        <div className="text-center py-12">
          <p className="text-muted-foreground">Campaign not found</p>
          <Button className="mt-4" variant="outline" onClick={() => window.location.href = "/ads/campaigns"}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Campaigns
          </Button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <Button variant="ghost" size="sm" className="mb-2 -ml-2" onClick={() => window.location.href = "/ads/campaigns"}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <h1 className="text-2xl font-bold text-slate-900">{campaign.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant={campaign.status === "ENABLED" ? "success" : campaign.status === "PAUSED" ? "warning" : "secondary"}>
                {campaign.status}
              </Badge>
              <Badge variant="outline">{campaign.type}</Badge>
              {campaign.bidding_strategy && <Badge variant="outline">{campaign.bidding_strategy}</Badge>}
              {campaign.is_draft && <Badge variant="destructive">Draft</Badge>}
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={toggleStatus}>
              {campaign.status === "ENABLED" ? <Pause className="w-4 h-4 mr-2" /> : <Play className="w-4 h-4 mr-2" />}
              {campaign.status === "ENABLED" ? "Pause" : "Enable"}
            </Button>
          </div>
        </div>

        {/* Campaign Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted-foreground">Budget/day</span>
                <DollarSign className="w-4 h-4 text-green-600" />
              </div>
              <div className="text-xl font-bold">{formatCurrency(campaign.budget || 0)}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted-foreground">Ad Groups</span>
                <Layers className="w-4 h-4 text-blue-600" />
              </div>
              <div className="text-xl font-bold">{campaign.ad_groups?.length || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted-foreground">Total Keywords</span>
                <Hash className="w-4 h-4 text-purple-600" />
              </div>
              <div className="text-xl font-bold">
                {campaign.ad_groups?.reduce((sum: number, ag: any) => sum + (ag.keywords?.length || 0), 0) || 0}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-muted-foreground">Total Ads</span>
                <Type className="w-4 h-4 text-orange-600" />
              </div>
              <div className="text-xl font-bold">
                {campaign.ad_groups?.reduce((sum: number, ag: any) => sum + (ag.ads?.length || 0), 0) || 0}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Ad Groups */}
        {campaign.ad_groups && campaign.ad_groups.length > 0 ? (
          campaign.ad_groups.map((ag: any) => (
            <Card key={ag.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base flex items-center gap-2">
                      <Target className="w-4 h-4" />
                      {ag.name}
                    </CardTitle>
                    <CardDescription className="flex items-center gap-2 mt-1">
                      <Badge variant={ag.status === "ENABLED" ? "success" : "secondary"} className="text-xs">
                        {ag.status}
                      </Badge>
                      <span>{ag.keywords?.length || 0} keywords</span>
                      <span>·</span>
                      <span>{ag.ads?.length || 0} ads</span>
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Keywords */}
                {ag.keywords && ag.keywords.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
                      <Hash className="w-3.5 h-3.5" /> Keywords ({ag.keywords.length})
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="pb-2 font-medium">Keyword</th>
                            <th className="pb-2 font-medium">Match Type</th>
                            <th className="pb-2 font-medium">Status</th>
                            <th className="pb-2 font-medium text-right">Quality Score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ag.keywords.map((kw: any) => (
                            <tr key={kw.id} className="border-b last:border-0">
                              <td className="py-2 font-medium">
                                {kw.match_type === "EXACT"
                                  ? `[${kw.text}]`
                                  : kw.match_type === "PHRASE"
                                    ? `"${kw.text}"`
                                    : kw.text}
                              </td>
                              <td className="py-2">
                                <Badge variant="outline" className="text-xs">{kw.match_type}</Badge>
                              </td>
                              <td className="py-2">
                                <Badge variant={kw.status === "ENABLED" ? "success" : "secondary"} className="text-xs">
                                  {kw.status}
                                </Badge>
                              </td>
                              <td className="py-2 text-right">
                                {kw.quality_score ? (
                                  <span className="flex items-center justify-end gap-1">
                                    <Star className={`w-3 h-3 ${kw.quality_score >= 7 ? "text-green-500" : kw.quality_score >= 4 ? "text-yellow-500" : "text-red-500"}`} />
                                    {kw.quality_score}/10
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Ads */}
                {ag.ads && ag.ads.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
                      <Type className="w-3.5 h-3.5" /> Ads ({ag.ads.length})
                    </h4>
                    <div className="space-y-3">
                      {ag.ads.map((ad: any) => (
                        <div key={ad.id} className="border rounded-lg p-4 bg-slate-50">
                          <div className="flex items-center justify-between mb-2">
                            <Badge variant="outline" className="text-xs">{ad.type}</Badge>
                            <Badge variant={ad.status === "ENABLED" ? "success" : "secondary"} className="text-xs">
                              {ad.status}
                            </Badge>
                          </div>
                          {ad.headlines && ad.headlines.length > 0 && (
                            <div className="mb-2">
                              <span className="text-xs text-muted-foreground">Headlines:</span>
                              <div className="flex flex-wrap gap-1 mt-1">
                                {(Array.isArray(ad.headlines) ? ad.headlines : []).map((h: string, hi: number) => (
                                  <span key={hi} className="text-sm bg-white border rounded px-2 py-0.5">
                                    {h}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          {ad.descriptions && ad.descriptions.length > 0 && (
                            <div className="mb-2">
                              <span className="text-xs text-muted-foreground">Descriptions:</span>
                              {(Array.isArray(ad.descriptions) ? ad.descriptions : []).map((d: string, di: number) => (
                                <p key={di} className="text-sm mt-1 bg-white border rounded px-2 py-1">{d}</p>
                              ))}
                            </div>
                          )}
                          {ad.final_urls && ad.final_urls.length > 0 && (
                            <div>
                              <span className="text-xs text-muted-foreground">Final URLs:</span>
                              <div className="flex flex-wrap gap-1 mt-1">
                                {(Array.isArray(ad.final_urls) ? ad.final_urls : []).map((url: string, ui: number) => (
                                  <a key={ui} href={url} target="_blank" rel="noopener noreferrer"
                                     className="text-xs text-blue-600 hover:underline flex items-center gap-0.5">
                                    {url} <ExternalLink className="w-3 h-3" />
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))
        ) : (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-muted-foreground">No ad groups found for this campaign.</p>
              <p className="text-sm text-muted-foreground mt-1">
                Sync your Google Ads account from Settings to pull ad group data, or create a new campaign via Command Console.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Change History */}
        {campaign.changes && campaign.changes.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Change History</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {campaign.changes.map((ch: any) => (
                  <div key={ch.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border text-sm">
                    <div>
                      <Badge variant="outline" className="text-xs mr-2">{ch.actor_type}</Badge>
                      <span>{ch.reason}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {ch.applied_at ? new Date(ch.applied_at).toLocaleString() : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
