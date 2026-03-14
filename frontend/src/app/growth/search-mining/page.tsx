"use client";

import { useEffect, useState, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Search, Loader2, Plus, Ban, DollarSign, TrendingUp,
  CheckCircle, XCircle, Sparkles, ArrowRight, AlertTriangle,
} from "lucide-react";

interface MiningResult {
  status: string;
  analyzed_terms: number;
  summary: string;
  total_spend_analyzed: number;
  wasted_spend: number;
  add_as_keyword: any[];
  add_as_negative: any[];
  new_ad_group_themes: any[];
  recommendations: any[];
  ai_generated: boolean;
}

interface Recommendation {
  id: string;
  title: string;
  severity: string;
  rationale: string;
  expected_impact: string;
  risk_level: string;
  action_diff: string;
  status: string;
  created_at: string;
}

export default function SearchTermMiningPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MiningResult | null>(null);
  const [savedRecs, setSavedRecs] = useState<Recommendation[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(true);
  const [actioning, setActioning] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  const [customerId, setCustomerId] = useState("");
  const [tab, setTab] = useState<"live" | "saved">("live");

  useEffect(() => {
    loadSavedRecs();
  }, []);

  async function loadSavedRecs() {
    setLoadingRecs(true);
    try {
      const recs = await api.get("/api/v2/growth/search-term-mining/recommendations");
      setSavedRecs(Array.isArray(recs) ? recs : []);
    } catch {
      // no recs yet
    } finally {
      setLoadingRecs(false);
    }
  }

  async function runMining() {
    if (!customerId) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await api.post("/api/v2/growth/search-term-mining/run", {
        google_customer_id: customerId,
        days,
      });
      setResult(res);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function actionRec(recId: string, action: "apply" | "dismiss") {
    setActioning(recId);
    try {
      await api.post(`/api/v2/growth/search-term-mining/recommendations/${recId}/action`, { action });
      await loadSavedRecs();
    } catch (e) {
      console.error(e);
    } finally {
      setActioning(null);
    }
  }

  const pendingRecs = savedRecs.filter((r) => r.status === "pending");
  const appliedRecs = savedRecs.filter((r) => r.status === "applied");

  return (
    <AppLayout>
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-amber-500" />
              Search Term Mining AI
            </h1>
            <p className="text-slate-500 mt-1">
              AI analyzes your search terms to find hidden opportunities and eliminate waste
            </p>
          </div>
        </div>

        {/* Run Mining Controls */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Google Ads Customer ID
                </label>
                <input
                  type="text"
                  placeholder="123-456-7890"
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value.replace(/[^\d-]/g, ""))}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div className="w-32">
                <label className="block text-sm font-medium text-slate-700 mb-1">Days</label>
                <select
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                >
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                  <option value={30}>30 days</option>
                  <option value={60}>60 days</option>
                  <option value={90}>90 days</option>
                </select>
              </div>
              <Button
                onClick={runMining}
                disabled={loading || !customerId}
                className="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white px-6"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Mining...</>
                ) : (
                  <><Search className="w-4 h-4 mr-2" /> Run AI Mining</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <div className="flex gap-2 border-b border-slate-200">
          <button
            onClick={() => setTab("live")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              tab === "live"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            Live Analysis {result && `(${result.analyzed_terms} terms)`}
          </button>
          <button
            onClick={() => setTab("saved")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              tab === "saved"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700"
            }`}
          >
            Saved Recommendations {pendingRecs.length > 0 && (
              <Badge className="ml-1 bg-amber-100 text-amber-800">{pendingRecs.length}</Badge>
            )}
          </button>
        </div>

        {/* Live Analysis Tab */}
        {tab === "live" && result && (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="pt-4 text-center">
                  <p className="text-sm text-slate-500">Terms Analyzed</p>
                  <p className="text-2xl font-bold text-slate-900">{result.analyzed_terms}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 text-center">
                  <p className="text-sm text-slate-500">Total Spend</p>
                  <p className="text-2xl font-bold text-slate-900">
                    ${result.total_spend_analyzed?.toFixed(0)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 text-center">
                  <p className="text-sm text-slate-500">Wasted Spend</p>
                  <p className="text-2xl font-bold text-red-600">
                    ${result.wasted_spend?.toFixed(0)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 text-center">
                  <p className="text-sm text-slate-500">AI Powered</p>
                  <p className="text-2xl font-bold text-green-600">
                    {result.ai_generated ? "✓ Yes" : "Rule-based"}
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* AI Summary */}
            {result.summary && (
              <Card className="border-blue-200 bg-blue-50/50">
                <CardContent className="pt-4">
                  <p className="text-sm font-medium text-blue-900 mb-1">AI Summary</p>
                  <p className="text-slate-700">{result.summary}</p>
                </CardContent>
              </Card>
            )}

            {/* Add as Keyword */}
            {result.add_as_keyword?.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Plus className="w-5 h-5 text-green-600" />
                    Add as Keywords ({result.add_as_keyword.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {result.add_as_keyword.map((kw: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-100"
                      >
                        <div className="flex-1">
                          <span className="font-medium text-slate-900">{kw.search_term}</span>
                          <span className="ml-2 text-xs text-slate-500">
                            [{kw.recommended_match_type}]
                          </span>
                          <p className="text-sm text-slate-600 mt-0.5">{kw.reason}</p>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge
                            className={
                              kw.priority === "high"
                                ? "bg-red-100 text-red-800"
                                : kw.priority === "medium"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-slate-100 text-slate-800"
                            }
                          >
                            {kw.priority}
                          </Badge>
                          <span className="text-sm font-medium text-green-700">
                            {kw.conversions} conv
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Add as Negative */}
            {result.add_as_negative?.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Ban className="w-5 h-5 text-red-600" />
                    Add as Negatives ({result.add_as_negative.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {result.add_as_negative.map((neg: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-3 bg-red-50 rounded-lg border border-red-100"
                      >
                        <div className="flex-1">
                          <span className="font-medium text-slate-900">{neg.search_term}</span>
                          <p className="text-sm text-slate-600 mt-0.5">{neg.reason}</p>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge
                            className={
                              neg.priority === "high"
                                ? "bg-red-100 text-red-800"
                                : "bg-amber-100 text-amber-800"
                            }
                          >
                            {neg.priority}
                          </Badge>
                          <span className="text-sm font-medium text-red-700">
                            ${neg.cost_wasted?.toFixed(2)} wasted
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* New Ad Group Themes */}
            {result.new_ad_group_themes?.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <TrendingUp className="w-5 h-5 text-purple-600" />
                    Suggested New Ad Groups ({result.new_ad_group_themes.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {result.new_ad_group_themes.map((theme: any, i: number) => (
                      <div
                        key={i}
                        className="p-4 bg-purple-50 rounded-lg border border-purple-100"
                      >
                        <p className="font-medium text-slate-900">{theme.theme}</p>
                        <p className="text-sm text-slate-600 mt-1">{theme.reason}</p>
                        <div className="flex flex-wrap gap-1 mt-2">
                          {theme.keywords?.map((kw: string, j: number) => (
                            <Badge key={j} className="bg-purple-100 text-purple-800 text-xs">
                              {kw}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {tab === "live" && !result && !loading && (
          <Card className="border-dashed border-2 border-slate-200">
            <CardContent className="py-12 text-center">
              <Search className="w-12 h-12 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-600">No analysis yet</h3>
              <p className="text-slate-400 mt-1">
                Enter your Google Ads Customer ID and click Run AI Mining
              </p>
            </CardContent>
          </Card>
        )}

        {/* Saved Recommendations Tab */}
        {tab === "saved" && (
          <>
            {loadingRecs ? (
              <div className="flex justify-center py-12">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
              </div>
            ) : pendingRecs.length === 0 && appliedRecs.length === 0 ? (
              <Card className="border-dashed border-2 border-slate-200">
                <CardContent className="py-12 text-center">
                  <AlertTriangle className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-600">No saved recommendations</h3>
                  <p className="text-slate-400 mt-1">
                    Run a mining analysis first — recommendations will be saved here
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {pendingRecs.length > 0 && (
                  <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
                    Pending ({pendingRecs.length})
                  </h3>
                )}
                {pendingRecs.map((rec) => (
                  <Card key={rec.id}>
                    <CardContent className="py-4">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <Badge
                              className={
                                rec.severity === "opportunity"
                                  ? "bg-green-100 text-green-800"
                                  : "bg-red-100 text-red-800"
                              }
                            >
                              {rec.severity}
                            </Badge>
                            <span className="font-medium text-slate-900">{rec.title}</span>
                          </div>
                          <p className="text-sm text-slate-600 mt-1">{rec.rationale}</p>
                          <p className="text-xs text-slate-400 mt-1">
                            Impact: {rec.expected_impact}
                          </p>
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            size="sm"
                            onClick={() => actionRec(rec.id, "apply")}
                            disabled={actioning === rec.id}
                            className="bg-green-600 hover:bg-green-700 text-white"
                          >
                            {actioning === rec.id ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <><CheckCircle className="w-3 h-3 mr-1" /> Apply</>
                            )}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => actionRec(rec.id, "dismiss")}
                            disabled={actioning === rec.id}
                          >
                            <XCircle className="w-3 h-3 mr-1" /> Dismiss
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {appliedRecs.length > 0 && (
                  <>
                    <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mt-6">
                      Applied ({appliedRecs.length})
                    </h3>
                    {appliedRecs.slice(0, 10).map((rec) => (
                      <Card key={rec.id} className="opacity-60">
                        <CardContent className="py-3">
                          <div className="flex items-center gap-2">
                            <CheckCircle className="w-4 h-4 text-green-600" />
                            <span className="text-sm text-slate-700">{rec.title}</span>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
