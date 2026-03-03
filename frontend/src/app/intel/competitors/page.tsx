"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Search, Globe, BarChart3, RefreshCw } from "lucide-react";

export default function CompetitorsPage() {
  const [competitors, setCompetitors] = useState<any[]>([]);
  const [auctionInsights, setAuctionInsights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/api/intel/competitors/profiles").catch(() => []),
      api.get("/api/intel/competitors/auction-insights").catch(() => []),
    ]).then(([c, a]) => {
      setCompetitors(Array.isArray(c) ? c : []);
      setAuctionInsights(Array.isArray(a) ? a : []);
    }).finally(() => setLoading(false));
  }, []);

  async function triggerScan() {
    try {
      await api.post("/api/intel/competitors/serp-scan", { keywords: ["locksmith near me", "emergency locksmith"] });
      alert("SERP scan triggered. Results will appear shortly.");
    } catch (e) { console.error(e); }
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Competitor Intelligence</h1>
            <p className="text-muted-foreground">Monitor competitors and find market opportunities</p>
          </div>
          <Button variant="outline" onClick={triggerScan}>
            <RefreshCw className="w-4 h-4 mr-2" /> Run SERP Scan
          </Button>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6"><div className="h-20 bg-slate-200 rounded" /></CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {competitors.length === 0 ? (
                <Card className="md:col-span-3">
                  <CardContent className="p-12 text-center text-muted-foreground">
                    No competitor data yet. Run a SERP scan to discover competitors.
                  </CardContent>
                </Card>
              ) : (
                competitors.map((comp: any) => (
                  <Card key={comp.id || comp.competitor_key}>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Globe className="w-4 h-4 text-muted-foreground" />
                        {comp.name || comp.domain}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground mb-3">{comp.domain}</p>
                      {comp.messaging_themes_json && (
                        <div className="flex flex-wrap gap-1.5">
                          {(Array.isArray(comp.messaging_themes_json) ? comp.messaging_themes_json : []).slice(0, 5).map((t: string, i: number) => (
                            <Badge key={i} variant="secondary" className="text-xs">{t}</Badge>
                          ))}
                        </div>
                      )}
                      {comp.landing_pages_json && (
                        <div className="mt-3">
                          <span className="text-xs text-muted-foreground">
                            {(Array.isArray(comp.landing_pages_json) ? comp.landing_pages_json : []).length} landing pages tracked
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))
              )}
            </div>

            {auctionInsights.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-blue-500" /> Auction Insights
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="pb-2 font-medium">Competitor</th>
                          <th className="pb-2 font-medium text-right">Impression Share</th>
                          <th className="pb-2 font-medium text-right">Overlap Rate</th>
                          <th className="pb-2 font-medium text-right">Outranking Share</th>
                          <th className="pb-2 font-medium text-right">Top of Page</th>
                          <th className="pb-2 font-medium text-right">Abs Top</th>
                        </tr>
                      </thead>
                      <tbody>
                        {auctionInsights.slice(0, 10).map((ai: any, i: number) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2.5 font-medium">{ai.competitor_domain}</td>
                            <td className="py-2.5 text-right">{((ai.impression_share || 0) * 100).toFixed(1)}%</td>
                            <td className="py-2.5 text-right">{((ai.overlap_rate || 0) * 100).toFixed(1)}%</td>
                            <td className="py-2.5 text-right">{((ai.outranking_share || 0) * 100).toFixed(1)}%</td>
                            <td className="py-2.5 text-right">{((ai.top_of_page_rate || 0) * 100).toFixed(1)}%</td>
                            <td className="py-2.5 text-right">{((ai.abs_top_rate || 0) * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
