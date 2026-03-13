"use client";

import { useEffect, useState, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { Globe, Gauge, Loader2, ExternalLink, Zap } from "lucide-react";

interface PageSpeedResult {
  performance_score: number | null;
  fcp_ms: number | null;
  lcp_ms: number | null;
  cls: number | null;
  tbt_ms: number | null;
  speed_index_ms: number | null;
  overall_category: string;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-slate-400";
  if (score >= 90) return "text-green-600";
  if (score >= 50) return "text-orange-500";
  return "text-red-600";
}

function scoreBg(score: number | null): string {
  if (score === null) return "bg-slate-100";
  if (score >= 90) return "bg-green-50 border-green-200";
  if (score >= 50) return "bg-orange-50 border-orange-200";
  return "bg-red-50 border-red-200";
}

function formatMs(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function LandingPagesPage() {
  const [pages, setPages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [speeds, setSpeeds] = useState<Record<string, PageSpeedResult>>({});
  const [checking, setChecking] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/ads/landing-pages?days=${days}&limit=50`)
      .then((data) => setPages(Array.isArray(data) ? data : []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [days]);

  const checkPageSpeed = useCallback(async (url: string) => {
    if (speeds[url] || checking[url]) return;
    setChecking((prev) => ({ ...prev, [url]: true }));
    try {
      const data = await api.get(`/api/ads/landing-pages/pagespeed?url=${encodeURIComponent(url)}&strategy=mobile`);
      setSpeeds((prev) => ({ ...prev, [url]: data }));
    } catch (e) {
      console.error("PageSpeed check failed for", url, e);
      setSpeeds((prev) => ({ ...prev, [url]: { performance_score: null, fcp_ms: null, lcp_ms: null, cls: null, tbt_ms: null, speed_index_ms: null, overall_category: "ERROR" } }));
    } finally {
      setChecking((prev) => ({ ...prev, [url]: false }));
    }
  }, [speeds, checking]);

  // Auto-check top 5 URLs with clicks
  useEffect(() => {
    if (pages.length === 0) return;
    const topUrls = pages.filter((p) => (p.clicks || 0) > 0).slice(0, 5);
    let delay = 0;
    for (const p of topUrls) {
      if (!speeds[p.landing_page_url] && !checking[p.landing_page_url]) {
        setTimeout(() => checkPageSpeed(p.landing_page_url), delay);
        delay += 2000; // stagger to avoid rate limits
      }
    }
  }, [pages]); // eslint-disable-line react-hooks/exhaustive-deps

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
                      <th className="text-center p-3 font-medium">
                        <div className="flex items-center justify-center gap-1">
                          <Gauge className="w-3.5 h-3.5" /> PageSpeed
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pages.map((p, i) => {
                      const speed = speeds[p.landing_page_url];
                      const isChecking = checking[p.landing_page_url];
                      const isExpanded = expanded === p.landing_page_url;
                      return (
                        <>
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
                                <a
                                  href={p.landing_page_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex-shrink-0"
                                >
                                  <ExternalLink className="w-3 h-3 text-slate-400 hover:text-slate-600" />
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
                              {isChecking ? (
                                <Loader2 className="w-4 h-4 animate-spin mx-auto text-blue-500" />
                              ) : speed ? (
                                <button
                                  onClick={() => setExpanded(isExpanded ? null : p.landing_page_url)}
                                  className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-xs font-bold cursor-pointer ${scoreBg(speed.performance_score)} ${scoreColor(speed.performance_score)}`}
                                >
                                  <Gauge className="w-3 h-3" />
                                  {speed.performance_score !== null ? speed.performance_score : "?"}
                                </button>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-xs h-7 px-2"
                                  onClick={() => checkPageSpeed(p.landing_page_url)}
                                >
                                  <Zap className="w-3 h-3 mr-1" /> Check
                                </Button>
                              )}
                            </td>
                          </tr>
                          {/* Expanded PageSpeed Details */}
                          {isExpanded && speed && (
                            <tr key={`${i}-details`} className="bg-slate-50/80">
                              <td colSpan={7} className="p-4">
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-center">
                                  <div>
                                    <div className="text-xs text-muted-foreground mb-1">Performance</div>
                                    <div className={`text-2xl font-bold ${scoreColor(speed.performance_score)}`}>
                                      {speed.performance_score ?? "—"}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-xs text-muted-foreground mb-1">First Contentful Paint</div>
                                    <div className="text-lg font-semibold text-slate-700">{formatMs(speed.fcp_ms)}</div>
                                  </div>
                                  <div>
                                    <div className="text-xs text-muted-foreground mb-1">Largest Contentful Paint</div>
                                    <div className={`text-lg font-semibold ${(speed.lcp_ms || 0) <= 2500 ? "text-green-600" : (speed.lcp_ms || 0) <= 4000 ? "text-orange-500" : "text-red-600"}`}>
                                      {formatMs(speed.lcp_ms)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-xs text-muted-foreground mb-1">Total Blocking Time</div>
                                    <div className={`text-lg font-semibold ${(speed.tbt_ms || 0) <= 200 ? "text-green-600" : (speed.tbt_ms || 0) <= 600 ? "text-orange-500" : "text-red-600"}`}>
                                      {formatMs(speed.tbt_ms)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-xs text-muted-foreground mb-1">Cumulative Layout Shift</div>
                                    <div className={`text-lg font-semibold ${(speed.cls || 0) <= 0.1 ? "text-green-600" : (speed.cls || 0) <= 0.25 ? "text-orange-500" : "text-red-600"}`}>
                                      {speed.cls !== null ? speed.cls.toFixed(3) : "—"}
                                    </div>
                                  </div>
                                </div>
                                <div className="mt-3 text-center">
                                  <a
                                    href={`https://pagespeed.web.dev/analysis?url=${encodeURIComponent(p.landing_page_url)}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1"
                                  >
                                    <ExternalLink className="w-3 h-3" /> View full report on PageSpeed Insights
                                  </a>
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      );
                    })}
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
