"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Lightbulb, Check, X, Loader2, TrendingUp, DollarSign, Target } from "lucide-react";
import { HelpTip, PageInfo } from "@/components/ui/help-tip";

const TYPE_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  KEYWORD: { label: "Keyword", color: "bg-blue-100 text-blue-800", icon: "🔑" },
  CAMPAIGN_BUDGET: { label: "Budget", color: "bg-green-100 text-green-800", icon: "💰" },
  RESPONSIVE_SEARCH_AD: { label: "RSA", color: "bg-purple-100 text-purple-800", icon: "📝" },
  TEXT_AD: { label: "Text Ad", color: "bg-indigo-100 text-indigo-800", icon: "📝" },
  SITELINK_EXTENSION: { label: "Sitelink", color: "bg-orange-100 text-orange-800", icon: "🔗" },
  CALL_EXTENSION: { label: "Call Ext.", color: "bg-yellow-100 text-yellow-800", icon: "📞" },
  TARGET_CPA_OPT_IN: { label: "Target CPA", color: "bg-teal-100 text-teal-800", icon: "🎯" },
  MAXIMIZE_CONVERSIONS_OPT_IN: { label: "Max Conv.", color: "bg-emerald-100 text-emerald-800", icon: "📈" },
};

export default function GoogleRecommendationsPage() {
  const [recs, setRecs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("pending");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [filter]);

  async function loadData() {
    setLoading(true);
    try {
      const params = filter !== "all" ? `?status=${filter}` : "";
      const data = await api.get(`/api/ads/google-recommendations${params}`);
      setRecs(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function applyRec(recId: string) {
    setActionLoading(recId);
    try {
      await api.post(`/api/ads/recommendations/${recId}/apply`);
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  }

  async function dismissRec(recId: string) {
    setActionLoading(recId);
    try {
      await api.post(`/api/ads/recommendations/${recId}/dismiss`);
      await loadData();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  }

  const pendingCount = recs.filter((r) => r.status === "pending").length;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Google Recommendations</h1>
            <p className="text-muted-foreground">
              Recommendations from Google to improve your account performance
            </p>
          </div>
          {pendingCount > 0 && (
            <Badge className="bg-blue-100 text-blue-800 text-sm px-3 py-1">
              {pendingCount} pending
            </Badge>
          )}
        </div>

        <PageInfo term="page_recommendations" />

        {/* Filters */}
        <div className="flex gap-2">
          {["pending", "applied", "dismissed", "all"].map((f) => (
            <Button
              key={f}
              variant={filter === f ? "default" : "outline"}
              size="sm"
              onClick={() => setFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </Button>
          ))}
        </div>

        {loading ? (
          <Card>
            <CardContent className="p-8 text-center">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">Loading recommendations...</p>
            </CardContent>
          </Card>
        ) : recs.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <Lightbulb className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground">
                {filter === "pending"
                  ? "No pending recommendations. Your account is well-optimized!"
                  : "No recommendations found for this filter."}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {recs.map((rec: any) => {
              const typeInfo = TYPE_LABELS[rec.type] || {
                label: rec.type,
                color: "bg-gray-100 text-gray-800",
                icon: "💡",
              };

              return (
                <Card key={rec.id} className="hover:shadow-md transition-shadow">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-lg">{typeInfo.icon}</span>
                          <Badge className={typeInfo.color}>{typeInfo.label}</Badge>
                          <Badge
                            variant={
                              rec.status === "applied"
                                ? "default"
                                : rec.status === "dismissed"
                                ? "secondary"
                                : "outline"
                            }
                          >
                            {rec.status}
                          </Badge>
                          {rec.campaign_name && (
                            <span className="text-xs text-muted-foreground">
                              Campaign: {rec.campaign_name}
                            </span>
                          )}
                        </div>

                        {/* Details */}
                        {rec.details && Object.keys(rec.details).length > 0 && (
                          <div className="mb-3 p-3 bg-slate-50 rounded-lg text-sm">
                            {rec.details.keyword && (
                              <p>
                                <strong>Keyword:</strong> {rec.details.keyword}{" "}
                                ({rec.details.match_type})
                              </p>
                            )}
                            {rec.details.recommended_budget_micros && (
                              <p>
                                <strong>Recommended Budget:</strong> $
                                {(rec.details.recommended_budget_micros / 1_000_000).toFixed(2)}/day
                                {rec.details.current_budget_micros && (
                                  <span className="text-muted-foreground ml-2">
                                    (currently ${(rec.details.current_budget_micros / 1_000_000).toFixed(2)}/day)
                                  </span>
                                )}
                              </p>
                            )}
                          </div>
                        )}

                        {/* Impact */}
                        {rec.impact_potential &&
                          Object.keys(rec.impact_potential).length > 0 && (
                            <div className="flex gap-4 text-xs">
                              {rec.impact_potential.impressions != null && (
                                <div className="flex items-center gap-1 text-blue-600">
                                  <TrendingUp className="w-3 h-3" />+
                                  {rec.impact_potential.impressions?.toLocaleString()} impr.
                                </div>
                              )}
                              {rec.impact_potential.clicks != null && (
                                <div className="flex items-center gap-1 text-green-600">
                                  <Target className="w-3 h-3" />+
                                  {rec.impact_potential.clicks?.toLocaleString()} clicks
                                </div>
                              )}
                              {rec.impact_potential.conversions != null && (
                                <div className="flex items-center gap-1 text-purple-600">
                                  <DollarSign className="w-3 h-3" />+
                                  {rec.impact_potential.conversions?.toFixed(1)} conv.
                                </div>
                              )}
                            </div>
                          )}
                      </div>

                      {/* Actions */}
                      {rec.status === "pending" && (
                        <div className="flex gap-2 ml-4">
                          <Button
                            size="sm"
                            onClick={() => applyRec(rec.id)}
                            disabled={actionLoading === rec.id}
                            className="bg-green-600 hover:bg-green-700"
                          >
                            {actionLoading === rec.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <>
                                <Check className="w-4 h-4 mr-1" /> Apply
                              </>
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => dismissRec(rec.id)}
                            disabled={actionLoading === rec.id}
                          >
                            <X className="w-4 h-4 mr-1" /> Dismiss
                          </Button>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
