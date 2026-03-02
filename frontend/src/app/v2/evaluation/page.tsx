"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Trophy, TrendingUp, TrendingDown, AlertTriangle, BarChart3, Target } from "lucide-react";
import { api } from "@/lib/api";

export default function EvaluationPage() {
  const [scorecards7, setScorecards7] = useState<any>(null);
  const [scorecards30, setScorecards30] = useState<any>(null);
  const [regression, setRegression] = useState<any>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [s7, s30, reg, lb] = await Promise.all([
        api.get(`/api/v2/evaluation/scorecards?tenant_id=${tenantId}&window_days=7`),
        api.get(`/api/v2/evaluation/scorecards?tenant_id=${tenantId}&window_days=30`),
        api.get(`/api/v2/evaluation/regression-check?tenant_id=${tenantId}`),
        api.get("/api/v2/evaluation/leaderboard"),
      ]);
      setScorecards7(s7);
      setScorecards30(s30);
      setRegression(reg);
      setLeaderboard(lb);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  function ScoreCard({ title, data, period }: { title: string; data: any; period: string }) {
    if (!data || data.total === 0) {
      return (
        <Card>
          <CardHeader><CardTitle className="text-sm">{title} ({period})</CardTitle></CardHeader>
          <CardContent><p className="text-sm text-slate-500">No outcome data yet. Recommendations need time to mature.</p></CardContent>
        </Card>
      );
    }
    return (
      <Card>
        <CardHeader><CardTitle className="text-sm">{title} ({period})</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="text-center p-3 bg-slate-50 rounded-lg">
              <div className="text-xs text-slate-500">Total</div>
              <div className="text-2xl font-bold text-slate-900">{data.total}</div>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <div className="text-xs text-slate-500">Win Rate</div>
              <div className="text-2xl font-bold text-green-700">{data.win_rate}%</div>
              <div className="text-xs text-green-600">{data.wins} wins</div>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg">
              <div className="text-xs text-slate-500">Loss Rate</div>
              <div className="text-2xl font-bold text-red-700">{data.loss_rate}%</div>
              <div className="text-xs text-red-600">{data.losses} losses</div>
            </div>
            <div className="text-center p-3 bg-blue-50 rounded-lg">
              <div className="text-xs text-slate-500">Prediction Error</div>
              <div className="text-2xl font-bold text-blue-700">{data.avg_prediction_error_pct}%</div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">AI Quality & Evaluation</h1>
          <p className="text-slate-500 mt-1">Recommendation scorecards, prediction accuracy, playbook leaderboard, and regression alerts</p>
        </div>

        {/* Regression Banner */}
        {regression?.regression_detected && (
          <div className="bg-red-50 border border-red-200 p-4 rounded-lg flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
            <div>
              <div className="font-medium text-red-900">Regression Detected</div>
              {(regression.details || []).map((d: string, i: number) => (
                <div key={i} className="text-sm text-red-700">{d}</div>
              ))}
            </div>
          </div>
        )}

        {/* Scorecards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ScoreCard title="Recommendation Quality" data={scorecards7} period="7-day" />
          <ScoreCard title="Recommendation Quality" data={scorecards30} period="30-day" />
        </div>

        {/* Regression Detail */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Target className="w-5 h-5" /> Prediction Accuracy</CardTitle>
            <CardDescription>Comparison of AI predicted vs actual outcomes over time</CardDescription>
          </CardHeader>
          <CardContent>
            {regression ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 border rounded-lg text-center">
                  <div className="text-xs text-slate-500 mb-1">7-Day Avg Error</div>
                  <div className={`text-2xl font-bold ${(regression.scorecards_7d?.avg_prediction_error_pct || 0) > 30 ? "text-red-600" : "text-green-600"}`}>
                    {regression.scorecards_7d?.avg_prediction_error_pct || 0}%
                  </div>
                </div>
                <div className="p-4 border rounded-lg text-center">
                  <div className="text-xs text-slate-500 mb-1">30-Day Avg Error</div>
                  <div className={`text-2xl font-bold ${(regression.scorecards_30d?.avg_prediction_error_pct || 0) > 30 ? "text-red-600" : "text-green-600"}`}>
                    {regression.scorecards_30d?.avg_prediction_error_pct || 0}%
                  </div>
                </div>
                <div className="p-4 border rounded-lg text-center">
                  <div className="text-xs text-slate-500 mb-1">Status</div>
                  <Badge variant={regression.regression_detected ? "destructive" : "default"} className="text-sm">
                    {regression.regression_detected ? "Regression" : "Healthy"}
                  </Badge>
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Loading regression data...</p>
            )}
          </CardContent>
        </Card>

        {/* Playbook Leaderboard */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Trophy className="w-5 h-5" /> Playbook Leaderboard</CardTitle>
            <CardDescription>Best-performing strategies ranked by industry vertical</CardDescription>
          </CardHeader>
          <CardContent>
            {leaderboard.length === 0 ? (
              <p className="text-sm text-slate-500">No playbook data yet. As recommendations mature, strategies will be ranked here.</p>
            ) : (
              <div className="space-y-3">
                {leaderboard.map((item: any, i: number) => (
                  <div key={i} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-sm font-bold text-indigo-700">
                        {i + 1}
                      </div>
                      <div>
                        <div className="font-medium text-sm">{item.metric_key}</div>
                        <div className="text-xs text-slate-500">{item.industry}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-medium">
                        {item.stats?.win_rate ? `${item.stats.win_rate}% win rate` : "N/A"}
                      </div>
                      {item.updated_at && (
                        <div className="text-xs text-slate-400">Updated: {new Date(item.updated_at).toLocaleDateString()}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
