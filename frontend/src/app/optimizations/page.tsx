"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Check, X, Undo2, Zap } from "lucide-react";

export default function OptimizationsPage() {
  const [recs, setRecs] = useState<any[]>([]);
  const [changeLogs, setChangeLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"pending" | "history">("pending");

  useEffect(() => {
    Promise.all([
      api.get("/api/optimizations/recommendations").catch(() => []),
      api.get("/api/optimizations/change-log").catch(() => []),
    ]).then(([r, c]) => {
      setRecs(Array.isArray(r) ? r : []);
      setChangeLogs(Array.isArray(c) ? c : []);
    }).finally(() => setLoading(false));
  }, []);

  async function handleApprove(id: string) {
    try {
      await api.post(`/api/optimizations/recommendations/${id}/approve`);
      setRecs(recs.map((r) => (r.id === id ? { ...r, status: "approved" } : r)));
    } catch (e) { console.error(e); }
  }

  async function handleReject(id: string) {
    try {
      await api.post(`/api/optimizations/recommendations/${id}/reject`);
      setRecs(recs.map((r) => (r.id === id ? { ...r, status: "rejected" } : r)));
    } catch (e) { console.error(e); }
  }

  async function handleRollback(changeId: string) {
    try {
      await api.post(`/api/optimizations/change-log/${changeId}/rollback`);
      alert("Rollback initiated");
    } catch (e) { console.error(e); }
  }

  const pending = recs.filter((r) => r.status === "pending");
  const sevColor: Record<string, string> = { high: "destructive", medium: "warning", low: "secondary" };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Optimizations</h1>
          <p className="text-muted-foreground">AI-generated recommendations and change history</p>
        </div>

        <div className="flex gap-2">
          <Button variant={tab === "pending" ? "default" : "outline"} onClick={() => setTab("pending")}>
            <Zap className="w-4 h-4 mr-2" /> Recommendations ({pending.length})
          </Button>
          <Button variant={tab === "history" ? "default" : "outline"} onClick={() => setTab("history")}>
            Change History ({changeLogs.length})
          </Button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse"><CardContent className="p-6"><div className="h-6 bg-slate-200 rounded w-96" /></CardContent></Card>
            ))}
          </div>
        ) : tab === "pending" ? (
          pending.length === 0 ? (
            <Card><CardContent className="p-12 text-center text-muted-foreground">No pending recommendations. Your campaigns are running well!</CardContent></Card>
          ) : (
            <div className="space-y-3">
              {pending.map((rec: any) => (
                <Card key={rec.id}>
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant={(sevColor[rec.severity] || "secondary") as any}>{rec.severity}</Badge>
                          <Badge variant="outline">{rec.category?.replace("_", " ")}</Badge>
                          {rec.risk_level && <span className="text-xs text-muted-foreground">Risk: {rec.risk_level}</span>}
                        </div>
                        <h3 className="font-medium mt-1">{rec.title}</h3>
                        <p className="text-sm text-muted-foreground mt-1">{rec.rationale}</p>
                        {rec.expected_impact_json?.estimated_improvement && (
                          <p className="text-xs text-green-600 mt-1">Expected: {rec.expected_impact_json.estimated_improvement}</p>
                        )}
                      </div>
                      <div className="flex gap-2 ml-4">
                        <Button size="sm" onClick={() => handleApprove(rec.id)}>
                          <Check className="w-4 h-4 mr-1" /> Approve
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleReject(rec.id)}>
                          <X className="w-4 h-4 mr-1" /> Reject
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )
        ) : (
          changeLogs.length === 0 ? (
            <Card><CardContent className="p-12 text-center text-muted-foreground">No changes recorded yet.</CardContent></Card>
          ) : (
            <div className="space-y-3">
              {changeLogs.map((cl: any) => (
                <Card key={cl.id}>
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline">{cl.entity_type}</Badge>
                          <span className="text-xs text-muted-foreground">{cl.actor_type} - {new Date(cl.created_at).toLocaleString()}</span>
                        </div>
                        <p className="text-sm">{cl.reason}</p>
                      </div>
                      {cl.rollback_token && (
                        <Button size="sm" variant="ghost" onClick={() => handleRollback(cl.id)}>
                          <Undo2 className="w-4 h-4 mr-1" /> Rollback
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )
        )}
      </div>
    </AppLayout>
  );
}
