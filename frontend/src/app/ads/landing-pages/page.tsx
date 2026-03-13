"use client";

import { useEffect, useState, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { Globe, Gauge, Loader2, ExternalLink, Zap, ArrowUp, ArrowDown, ArrowUpDown, Brain, AlertTriangle, CheckCircle2, Lightbulb, Target, Shield, Smartphone, FileText, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { HelpTip, PageInfo } from "@/components/ui/help-tip";

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

type SortKey = "clicks" | "cost" | "conversions" | "conversion_rate" | "ctr" | "pagespeed";
type SortDir = "asc" | "desc";

export default function LandingPagesPage() {
  const [pages, setPages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [speeds, setSpeeds] = useState<Record<string, PageSpeedResult>>({});
  const [checking, setChecking] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("clicks");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [audits, setAudits] = useState<Record<string, any>>({});
  const [auditing, setAuditing] = useState<Record<string, boolean>>({});
  const [auditExpanded, setAuditExpanded] = useState<string | null>(null);

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

  async function runAiAudit(url: string) {
    if (auditing[url]) return;
    setAuditing((prev) => ({ ...prev, [url]: true }));
    try {
      const result = await api.post("/api/ads/landing-pages/audit", { url });
      setAudits((prev) => ({ ...prev, [url]: result }));
      setAuditExpanded(url);
      setExpanded(null);
    } catch (e: any) {
      setAudits((prev) => ({ ...prev, [url]: { status: "error", error: e?.message || "Audit failed" } }));
      setAuditExpanded(url);
    } finally {
      setAuditing((prev) => ({ ...prev, [url]: false }));
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

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ArrowUpDown className="w-3 h-3 text-slate-300" />;
    return sortDir === "desc"
      ? <ArrowDown className="w-3 h-3 text-blue-600" />
      : <ArrowUp className="w-3 h-3 text-blue-600" />;
  }

  const sortedPages = [...pages].sort((a, b) => {
    let av: number, bv: number;
    if (sortKey === "pagespeed") {
      av = speeds[a.landing_page_url]?.performance_score ?? -1;
      bv = speeds[b.landing_page_url]?.performance_score ?? -1;
    } else {
      av = a[sortKey] || 0;
      bv = b[sortKey] || 0;
    }
    return sortDir === "desc" ? bv - av : av - bv;
  });

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Landing Pages</h1>
          <p className="text-muted-foreground">Analyze landing page performance and conversion rates</p>
        </div>

        <PageInfo term="page_landing_pages" />

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
                      {[
                        { key: "clicks" as SortKey, label: "Clicks" },
                        { key: "cost" as SortKey, label: "Cost" },
                        { key: "conversions" as SortKey, label: "Conv." },
                        { key: "conversion_rate" as SortKey, label: "Conv. Rate" },
                        { key: "ctr" as SortKey, label: "CTR" },
                      ].map(({ key, label }) => (
                        <th key={key} className="text-right p-3 font-medium">
                          <button
                            onClick={() => toggleSort(key)}
                            className="inline-flex items-center gap-1 hover:text-blue-600 transition-colors"
                          >
                            {label} <SortIcon col={key} />
                          </button>
                        </th>
                      ))}
                      <th className="text-center p-3 font-medium">
                        <button
                          onClick={() => toggleSort("pagespeed")}
                          className="inline-flex items-center gap-1 hover:text-blue-600 transition-colors"
                        >
                          <Gauge className="w-3.5 h-3.5" /> PageSpeed <SortIcon col="pagespeed" />
                        </button>
                      </th>
                      <th className="text-center p-3 font-medium">
                        <span className="inline-flex items-center gap-1">
                          <Brain className="w-3.5 h-3.5" /> AI Audit
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedPages.map((p, i) => {
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
                                  onClick={() => { setExpanded(isExpanded ? null : p.landing_page_url); setAuditExpanded(null); }}
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
                            <td className="p-3 text-center">
                              {auditing[p.landing_page_url] ? (
                                <div className="flex flex-col items-center gap-1">
                                  <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
                                  <span className="text-[10px] text-purple-600">Scanning...</span>
                                </div>
                              ) : audits[p.landing_page_url]?.ai_audit ? (
                                <button
                                  onClick={() => { setAuditExpanded(auditExpanded === p.landing_page_url ? null : p.landing_page_url); setExpanded(null); }}
                                  className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-xs font-bold cursor-pointer ${auditScoreBg(audits[p.landing_page_url].ai_audit.overall_score)} ${auditScoreColor(audits[p.landing_page_url].ai_audit.overall_score)}`}
                                >
                                  <Brain className="w-3 h-3" />
                                  {audits[p.landing_page_url].ai_audit.overall_score}/100
                                </button>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-xs h-7 px-2 text-purple-600 hover:text-purple-700 hover:bg-purple-50"
                                  onClick={() => runAiAudit(p.landing_page_url)}
                                >
                                  <Brain className="w-3 h-3 mr-1" /> Audit
                                </Button>
                              )}
                            </td>
                          </tr>
                          {/* Expanded PageSpeed Details */}
                          {isExpanded && speed && (
                            <tr key={`${i}-details`} className="bg-slate-50/80">
                              <td colSpan={8} className="p-4">
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

                          {/* AI Audit Report */}
                          {auditExpanded === p.landing_page_url && audits[p.landing_page_url] && (() => {
                            const audit = audits[p.landing_page_url];
                            const ai = audit.ai_audit;
                            const pd = audit.page_data;
                            if (audit.status === "error") {
                              return (
                                <tr key={`${i}-audit`} className="bg-red-50/50">
                                  <td colSpan={8} className="p-4">
                                    <div className="flex items-center gap-2 text-red-700">
                                      <AlertTriangle className="w-4 h-4" />
                                      <span className="text-sm font-medium">Audit failed: {audit.error}</span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            }
                            return (
                              <tr key={`${i}-audit`} className="bg-purple-50/30">
                                <td colSpan={8} className="p-0">
                                  <div className="p-5 space-y-5">
                                    {/* Header */}
                                    <div className="flex items-start justify-between">
                                      <div className="flex items-center gap-3">
                                        <div className={`w-16 h-16 rounded-xl border-2 flex flex-col items-center justify-center ${auditScoreBg(ai?.overall_score)}`}>
                                          <span className={`text-2xl font-bold ${auditScoreColor(ai?.overall_score)}`}>{ai?.overall_score ?? "?"}</span>
                                          <span className="text-[9px] text-slate-500 -mt-0.5">/ 100</span>
                                        </div>
                                        <div>
                                          <h3 className="text-base font-bold text-slate-900">AI Landing Page Audit</h3>
                                          <p className="text-xs text-slate-500 mt-0.5 max-w-xl">{ai?.summary}</p>
                                        </div>
                                      </div>
                                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setAuditExpanded(null)}>
                                        <X className="w-4 h-4" />
                                      </Button>
                                    </div>

                                    {/* Score Cards */}
                                    {ai?.scores && (
                                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                                        {[
                                          { key: "message_match", label: "Message Match", icon: Target },
                                          { key: "keyword_relevance", label: "Keyword Relevance", icon: FileText },
                                          { key: "conversion_optimization", label: "Conversion", icon: CheckCircle2 },
                                          { key: "trust_credibility", label: "Trust", icon: Shield },
                                          { key: "page_structure", label: "Structure", icon: FileText },
                                          { key: "mobile_readiness", label: "Mobile", icon: Smartphone },
                                        ].map(({ key, label, icon: Icon }) => {
                                          const s = ai.scores[key];
                                          if (!s) return null;
                                          return (
                                            <div key={key} className={`rounded-lg border p-3 ${auditScoreBg(s.score)}`}>
                                              <div className="flex items-center gap-1.5 mb-1">
                                                <Icon className="w-3.5 h-3.5 text-slate-500" />
                                                <span className="text-[11px] font-medium text-slate-600">{label}</span>
                                              </div>
                                              <div className={`text-xl font-bold ${auditScoreColor(s.score)}`}>{s.score}</div>
                                              <p className="text-[10px] text-slate-500 mt-1 line-clamp-2">{s.explanation}</p>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    )}

                                    {/* Page Data Summary */}
                                    {pd && (
                                      <div className="bg-white rounded-lg border p-4">
                                        <h4 className="text-sm font-semibold text-slate-700 mb-2">Page Scan Results</h4>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                          <div><span className="text-slate-500">Title:</span> <span className="font-medium">{pd.title || "(none)"}</span></div>
                                          <div><span className="text-slate-500">Words:</span> <span className="font-medium">{pd.word_count?.toLocaleString()}</span></div>
                                          <div><span className="text-slate-500">Forms:</span> <span className="font-medium">{pd.form_count}</span></div>
                                          <div><span className="text-slate-500">Images:</span> <span className="font-medium">{pd.image_count} ({pd.images_with_alt} with alt)</span></div>
                                          <div><span className="text-slate-500">CTAs:</span> <span className="font-medium">{pd.ctas?.join(", ") || "None found"}</span></div>
                                          <div><span className="text-slate-500">Phone:</span> <span className="font-medium">{pd.phone_numbers?.length > 0 ? pd.phone_numbers.join(", ") : "Not visible"}</span></div>
                                          <div><span className="text-slate-500">Trust:</span> <span className="font-medium">{pd.trust_signals?.join(", ") || "None detected"}</span></div>
                                          <div><span className="text-slate-500">H1:</span> <span className="font-medium">{pd.h1_headings?.join(", ") || "(none)"}</span></div>
                                        </div>
                                      </div>
                                    )}

                                    {/* Critical Issues */}
                                    {ai?.critical_issues && ai.critical_issues.length > 0 && (
                                      <div className="bg-white rounded-lg border border-red-200 p-4">
                                        <h4 className="text-sm font-semibold text-red-700 mb-2 flex items-center gap-1.5">
                                          <AlertTriangle className="w-4 h-4" /> Critical Issues ({ai.critical_issues.length})
                                        </h4>
                                        <div className="space-y-2">
                                          {ai.critical_issues.map((issue: any, idx: number) => (
                                            <div key={idx} className="flex items-start gap-2 text-xs">
                                              <Badge className={`text-[10px] shrink-0 ${issue.impact === "high" ? "bg-red-100 text-red-700" : issue.impact === "medium" ? "bg-orange-100 text-orange-700" : "bg-yellow-100 text-yellow-700"}`}>
                                                {issue.impact}
                                              </Badge>
                                              <div>
                                                <span className="font-medium text-slate-800">{issue.issue}</span>
                                                <p className="text-slate-500 mt-0.5">{issue.fix}</p>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Ad ↔ Landing Page Gaps */}
                                    {ai?.ad_landing_page_gaps && ai.ad_landing_page_gaps.length > 0 && (
                                      <div className="bg-white rounded-lg border border-orange-200 p-4">
                                        <h4 className="text-sm font-semibold text-orange-700 mb-2 flex items-center gap-1.5">
                                          <Target className="w-4 h-4" /> Ad ↔ Landing Page Gaps
                                        </h4>
                                        <ul className="space-y-1">
                                          {ai.ad_landing_page_gaps.map((gap: string, idx: number) => (
                                            <li key={idx} className="text-xs text-slate-700 flex items-start gap-1.5">
                                              <span className="text-orange-400 mt-0.5">•</span> {gap}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}

                                    {/* Quick Wins */}
                                    {ai?.quick_wins && ai.quick_wins.length > 0 && (
                                      <div className="bg-white rounded-lg border border-green-200 p-4">
                                        <h4 className="text-sm font-semibold text-green-700 mb-2 flex items-center gap-1.5">
                                          <Zap className="w-4 h-4" /> Quick Wins — Do These Today
                                        </h4>
                                        <ul className="space-y-1">
                                          {ai.quick_wins.map((win: string, idx: number) => (
                                            <li key={idx} className="text-xs text-slate-700 flex items-start gap-1.5">
                                              <CheckCircle2 className="w-3 h-3 text-green-500 mt-0.5 shrink-0" /> {win}
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}

                                    {/* Full Recommendations */}
                                    {ai?.recommendations && ai.recommendations.length > 0 && (
                                      <div className="bg-white rounded-lg border p-4">
                                        <h4 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
                                          <Lightbulb className="w-4 h-4 text-amber-500" /> All Recommendations ({ai.recommendations.length})
                                        </h4>
                                        <div className="space-y-3">
                                          {ai.recommendations.map((rec: any, idx: number) => (
                                            <div key={idx} className="border-l-2 pl-3 py-1" style={{ borderColor: rec.priority === "high" ? "#ef4444" : rec.priority === "medium" ? "#f59e0b" : "#3b82f6" }}>
                                              <div className="flex items-center gap-2 mb-0.5">
                                                <Badge className={`text-[10px] ${rec.priority === "high" ? "bg-red-100 text-red-700" : rec.priority === "medium" ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"}`}>
                                                  {rec.priority}
                                                </Badge>
                                                <Badge className="text-[10px] bg-slate-100 text-slate-600">{rec.category}</Badge>
                                                <span className="text-xs font-semibold text-slate-800">{rec.title}</span>
                                              </div>
                                              <p className="text-[11px] text-slate-600">{rec.description}</p>
                                              {rec.expected_impact && <p className="text-[10px] text-green-600 mt-0.5 font-medium">Expected impact: {rec.expected_impact}</p>}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Missing Elements */}
                                    {ai?.missing_elements && ai.missing_elements.length > 0 && (
                                      <div className="bg-white rounded-lg border p-4">
                                        <h4 className="text-sm font-semibold text-slate-700 mb-2">Missing Elements</h4>
                                        <div className="flex flex-wrap gap-1.5">
                                          {ai.missing_elements.map((el: string, idx: number) => (
                                            <Badge key={idx} className="text-[10px] bg-slate-100 text-slate-700 border border-slate-200">{el}</Badge>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                  </div>
                                </td>
                              </tr>
                            );
                          })()}
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
