"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Globe, Smartphone, Gauge, Loader2 } from "lucide-react";

export default function LandingPagesPage() {
  const [pages, setPages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/ads/landing-pages?days=${days}&limit=50`)
      .then((data) => setPages(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Landing Pages</h1>
          <p className="text-muted-foreground">Analyze landing page performance and conversion rates</p>
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
          <Card><CardContent className="p-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" /><p className="text-muted-foreground">Loading landing pages...</p></CardContent></Card>
        ) : pages.length === 0 ? (
          <Card><CardContent className="p-12 text-center"><p className="text-muted-foreground">No landing page data. Sync your account first.</p></CardContent></Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-slate-50">
                      <th className="text-left p-3 font-medium">Landing Page URL</th>
                      <th className="text-right p-3 font-medium">Clicks</th>
                      <th className="text-right p-3 font-medium">Cost</th>
                      <th className="text-right p-3 font-medium">Conv.</th>
                      <th className="text-right p-3 font-medium">Conv. Rate</th>
                      <th className="text-right p-3 font-medium">CTR</th>
                      <th className="text-center p-3 font-medium">Mobile</th>
                      <th className="text-center p-3 font-medium">Speed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pages.map((p, i) => (
                      <tr key={i} className="border-b hover:bg-slate-50">
                        <td className="p-3 max-w-[400px]">
                          <div className="flex items-center gap-2">
                            <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                            <a
                              href={p.landing_page_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline truncate"
                            >
                              {p.landing_page_url}
                            </a>
                          </div>
                        </td>
                        <td className="p-3 text-right">{(p.clicks || 0).toLocaleString()}</td>
                        <td className="p-3 text-right font-medium">${(p.cost || 0).toFixed(2)}</td>
                        <td className="p-3 text-right">{(p.conversions || 0).toFixed(1)}</td>
                        <td className="p-3 text-right">
                          <span className={`font-medium ${(p.conversion_rate || 0) >= 5 ? "text-green-600" : (p.conversion_rate || 0) >= 2 ? "text-yellow-600" : "text-red-600"}`}>
                            {(p.conversion_rate || 0).toFixed(2)}%
                          </span>
                        </td>
                        <td className="p-3 text-right">{(p.ctr || 0).toFixed(2)}%</td>
                        <td className="p-3 text-center">
                          {p.mobile_friendly_click_rate != null ? (
                            <div className="flex items-center justify-center gap-1">
                              <Smartphone className={`w-3 h-3 ${p.mobile_friendly_click_rate >= 80 ? "text-green-500" : "text-red-500"}`} />
                              <span className="text-xs">{p.mobile_friendly_click_rate}%</span>
                            </div>
                          ) : "—"}
                        </td>
                        <td className="p-3 text-center">
                          {p.speed_score != null ? (
                            <div className="flex items-center justify-center gap-1">
                              <Gauge className={`w-3 h-3 ${p.speed_score >= 70 ? "text-green-500" : p.speed_score >= 40 ? "text-yellow-500" : "text-red-500"}`} />
                              <span className="text-xs">{p.speed_score}</span>
                            </div>
                          ) : "—"}
                        </td>
                      </tr>
                    ))}
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
