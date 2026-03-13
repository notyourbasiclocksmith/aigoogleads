"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Pause, Play, Trophy, AlertTriangle, Loader2, ExternalLink, Eye, ArrowUp, ArrowDown, ArrowUpDown, Brain, Target, Shield, Smartphone, FileText, CheckCircle2, Lightbulb, Zap, X } from "lucide-react";
import { HelpTip, PageInfo } from "@/components/ui/help-tip";

type SortKey = "impressions" | "clicks" | "cost" | "conversions" | "ctr" | "cpc";
type SortDir = "asc" | "desc";

export default function AdPerformancePage() {
  const [ads, setAds] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("cost");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [audits, setAudits] = useState<Record<string, any>>({});
  const [auditing, setAuditing] = useState<Record<string, boolean>>({});
  const [auditExpanded, setAuditExpanded] = useState<string | null>(null);

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

  async function runAiAudit(ad: any) {
    const adId = ad.ad_id;
    if (auditing[adId]) return;
    const url = ad.final_urls?.[0];
    if (!url) return;
    setAuditing((prev) => ({ ...prev, [adId]: true }));
    try {
      const result = await api.post("/api/ads/landing-pages/audit", {
        url,
        ad_headlines: ad.headlines || [],
        ad_descriptions: ad.descriptions || [],
        ad_id: adId,
      });
      setAudits((prev) => ({ ...prev, [adId]: result }));
      setAuditExpanded(adId);
    } catch (e: any) {
      setAudits((prev) => ({ ...prev, [adId]: { status: "error", error: e?.message || "Audit failed" } }));
      setAuditExpanded(adId);
    } finally {
      setAuditing((prev) => ({ ...prev, [adId]: false }));
    }
  }

  function auditScoreColor(score: number | null | undefined): string {
    if (score == null) return "text-slate-400";
    if (score >= 80) return "text-green-600";
    if (score >= 50) return "text-orange-500";
    return "text-red-600";
  }

  function auditScoreBg(score: number | null | undefined): string {
    if (score == null) return "bg-slate-100 border-slate-200";
    if (score >= 80) return "bg-green-50 border-green-200";
    if (score >= 50) return "bg-orange-50 border-orange-200";
    return "bg-red-50 border-red-200";
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

        <PageInfo term="page_ads" />

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
                        {ad.final_urls && ad.final_urls.length > 0 && (
                          auditing[ad.ad_id] ? (
                            <span className="inline-flex items-center gap-1 text-xs font-medium text-purple-600">
                              <Loader2 className="w-3 h-3 animate-spin" /> Scanning Landing Page...
                            </span>
                          ) : audits[ad.ad_id]?.ai_audit ? (
                            <button
                              onClick={() => setAuditExpanded(auditExpanded === ad.ad_id ? null : ad.ad_id)}
                              className={`inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded border cursor-pointer ${auditScoreBg(audits[ad.ad_id].ai_audit.overall_score)} ${auditScoreColor(audits[ad.ad_id].ai_audit.overall_score)}`}
                            >
                              <Brain className="w-3 h-3" /> Audit: {audits[ad.ad_id].ai_audit.overall_score}/100
                            </button>
                          ) : (
                            <button
                              onClick={() => runAiAudit(ad)}
                              className="inline-flex items-center gap-1 text-xs font-medium text-purple-600 hover:text-purple-800 hover:underline"
                            >
                              <Brain className="w-3 h-3" /> AI Audit Landing Page
                            </button>
                          )
                        )}
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

                      {/* AI Audit Report */}
                      {auditExpanded === ad.ad_id && audits[ad.ad_id] && (() => {
                        const audit = audits[ad.ad_id];
                        const ai = audit.ai_audit;
                        const pd = audit.page_data;
                        if (audit.status === "error") {
                          return (
                            <div className="mt-3 p-3 bg-red-50 rounded-lg border border-red-200">
                              <div className="flex items-center gap-2 text-red-700">
                                <AlertTriangle className="w-4 h-4" />
                                <span className="text-sm font-medium">Audit failed: {audit.error}</span>
                              </div>
                            </div>
                          );
                        }
                        return (
                          <div className="mt-4 space-y-4 border-t pt-4">
                            {/* Header */}
                            <div className="flex items-start justify-between">
                              <div className="flex items-center gap-3">
                                <div className={`w-14 h-14 rounded-xl border-2 flex flex-col items-center justify-center ${auditScoreBg(ai?.overall_score)}`}>
                                  <span className={`text-xl font-bold ${auditScoreColor(ai?.overall_score)}`}>{ai?.overall_score ?? "?"}</span>
                                  <span className="text-[8px] text-slate-500 -mt-0.5">/ 100</span>
                                </div>
                                <div>
                                  <h4 className="text-sm font-bold text-slate-900">AI Landing Page Audit</h4>
                                  <p className="text-xs text-slate-500 mt-0.5 max-w-lg">{ai?.summary}</p>
                                </div>
                              </div>
                              <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setAuditExpanded(null)}>
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            </div>

                            {/* Score Cards */}
                            {ai?.scores && (
                              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                                {[
                                  { key: "message_match", label: "Message Match", icon: Target },
                                  { key: "keyword_relevance", label: "Keywords", icon: FileText },
                                  { key: "conversion_optimization", label: "Conversion", icon: CheckCircle2 },
                                  { key: "trust_credibility", label: "Trust", icon: Shield },
                                  { key: "page_structure", label: "Structure", icon: FileText },
                                  { key: "mobile_readiness", label: "Mobile", icon: Smartphone },
                                ].map(({ key, label, icon: Icon }) => {
                                  const s = ai.scores[key];
                                  if (!s) return null;
                                  return (
                                    <div key={key} className={`rounded-lg border p-2.5 ${auditScoreBg(s.score)}`}>
                                      <div className="flex items-center gap-1 mb-0.5">
                                        <Icon className="w-3 h-3 text-slate-500" />
                                        <span className="text-[10px] font-medium text-slate-600">{label}</span>
                                      </div>
                                      <div className={`text-lg font-bold ${auditScoreColor(s.score)}`}>{s.score}</div>
                                      <p className="text-[9px] text-slate-500 mt-0.5 line-clamp-2">{s.explanation}</p>
                                    </div>
                                  );
                                })}
                              </div>
                            )}

                            {/* Page Scan Summary */}
                            {pd && (
                              <div className="bg-slate-50 rounded-lg border p-3">
                                <h5 className="text-xs font-semibold text-slate-700 mb-1.5">Page Scan</h5>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
                                  <div><span className="text-slate-500">Title:</span> <span className="font-medium">{pd.title || "(none)"}</span></div>
                                  <div><span className="text-slate-500">Words:</span> <span className="font-medium">{pd.word_count?.toLocaleString()}</span></div>
                                  <div><span className="text-slate-500">Forms:</span> <span className="font-medium">{pd.form_count}</span></div>
                                  <div><span className="text-slate-500">Images:</span> <span className="font-medium">{pd.image_count} ({pd.images_with_alt} with alt)</span></div>
                                  <div><span className="text-slate-500">CTAs:</span> <span className="font-medium">{pd.ctas?.join(", ") || "None"}</span></div>
                                  <div><span className="text-slate-500">Phone:</span> <span className="font-medium">{pd.phone_numbers?.length > 0 ? pd.phone_numbers.join(", ") : "Not visible"}</span></div>
                                  <div><span className="text-slate-500">Trust:</span> <span className="font-medium">{pd.trust_signals?.join(", ") || "None"}</span></div>
                                  <div><span className="text-slate-500">H1:</span> <span className="font-medium">{pd.h1_headings?.join(", ") || "(none)"}</span></div>
                                </div>
                              </div>
                            )}

                            {/* Critical Issues */}
                            {ai?.critical_issues && ai.critical_issues.length > 0 && (
                              <div className="bg-white rounded-lg border border-red-200 p-3">
                                <h5 className="text-xs font-semibold text-red-700 mb-1.5 flex items-center gap-1">
                                  <AlertTriangle className="w-3.5 h-3.5" /> Critical Issues ({ai.critical_issues.length})
                                </h5>
                                <div className="space-y-1.5">
                                  {ai.critical_issues.map((issue: any, idx: number) => (
                                    <div key={idx} className="flex items-start gap-2 text-[11px]">
                                      <Badge className={`text-[9px] shrink-0 ${issue.impact === "high" ? "bg-red-100 text-red-700" : issue.impact === "medium" ? "bg-orange-100 text-orange-700" : "bg-yellow-100 text-yellow-700"}`}>
                                        {issue.impact}
                                      </Badge>
                                      <div>
                                        <span className="font-medium text-slate-800">{issue.issue}</span>
                                        <p className="text-slate-500">{issue.fix}</p>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Ad ↔ Landing Page Gaps */}
                            {ai?.ad_landing_page_gaps && ai.ad_landing_page_gaps.length > 0 && (
                              <div className="bg-white rounded-lg border border-orange-200 p-3">
                                <h5 className="text-xs font-semibold text-orange-700 mb-1.5 flex items-center gap-1">
                                  <Target className="w-3.5 h-3.5" /> Ad vs Landing Page Gaps
                                </h5>
                                <ul className="space-y-0.5">
                                  {ai.ad_landing_page_gaps.map((gap: string, idx: number) => (
                                    <li key={idx} className="text-[11px] text-slate-700 flex items-start gap-1">
                                      <span className="text-orange-400 mt-0.5">•</span> {gap}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Quick Wins */}
                            {ai?.quick_wins && ai.quick_wins.length > 0 && (
                              <div className="bg-white rounded-lg border border-green-200 p-3">
                                <h5 className="text-xs font-semibold text-green-700 mb-1.5 flex items-center gap-1">
                                  <Zap className="w-3.5 h-3.5" /> Quick Wins
                                </h5>
                                <ul className="space-y-0.5">
                                  {ai.quick_wins.map((win: string, idx: number) => (
                                    <li key={idx} className="text-[11px] text-slate-700 flex items-start gap-1">
                                      <CheckCircle2 className="w-3 h-3 text-green-500 mt-0.5 shrink-0" /> {win}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {/* Full Recommendations */}
                            {ai?.recommendations && ai.recommendations.length > 0 && (
                              <div className="bg-white rounded-lg border p-3">
                                <h5 className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1">
                                  <Lightbulb className="w-3.5 h-3.5 text-amber-500" /> Recommendations ({ai.recommendations.length})
                                </h5>
                                <div className="space-y-2">
                                  {ai.recommendations.map((rec: any, idx: number) => (
                                    <div key={idx} className="border-l-2 pl-2.5 py-0.5" style={{ borderColor: rec.priority === "high" ? "#ef4444" : rec.priority === "medium" ? "#f59e0b" : "#3b82f6" }}>
                                      <div className="flex items-center gap-1.5 mb-0.5">
                                        <Badge className={`text-[9px] ${rec.priority === "high" ? "bg-red-100 text-red-700" : rec.priority === "medium" ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"}`}>
                                          {rec.priority}
                                        </Badge>
                                        <Badge className="text-[9px] bg-slate-100 text-slate-600">{rec.category}</Badge>
                                        <span className="text-[11px] font-semibold text-slate-800">{rec.title}</span>
                                      </div>
                                      <p className="text-[10px] text-slate-600">{rec.description}</p>
                                      {rec.expected_impact && <p className="text-[9px] text-green-600 mt-0.5 font-medium">Impact: {rec.expected_impact}</p>}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Missing Elements */}
                            {ai?.missing_elements && ai.missing_elements.length > 0 && (
                              <div className="bg-white rounded-lg border p-3">
                                <h5 className="text-xs font-semibold text-slate-700 mb-1.5">Missing Elements</h5>
                                <div className="flex flex-wrap gap-1">
                                  {ai.missing_elements.map((el: string, idx: number) => (
                                    <Badge key={idx} className="text-[9px] bg-slate-100 text-slate-700 border border-slate-200">{el}</Badge>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })()}
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
