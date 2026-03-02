"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { FlaskConical, Play, Square, Trophy } from "lucide-react";

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/experiments").then(setExperiments).catch(() => setExperiments([])).finally(() => setLoading(false));
  }, []);

  async function handleStart(id: string) {
    try {
      await api.post(`/api/experiments/${id}/start`);
      const updated = await api.get("/api/experiments");
      setExperiments(updated);
    } catch (e) { console.error(e); }
  }

  async function handleStop(id: string) {
    try {
      await api.post(`/api/experiments/${id}/stop`);
      const updated = await api.get("/api/experiments");
      setExperiments(updated);
    } catch (e) { console.error(e); }
  }

  async function handlePromote(id: string, variantIndex: number) {
    try {
      await api.post(`/api/experiments/${id}/promote`, { variant_index: variantIndex });
      alert("Winner promoted!");
    } catch (e) { console.error(e); }
  }

  const statusColor: Record<string, string> = {
    draft: "secondary", running: "success", paused: "warning", completed: "default",
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Experiments</h1>
            <p className="text-muted-foreground">A/B tests and multi-armed bandit experiments</p>
          </div>
          <Button>
            <FlaskConical className="w-4 h-4 mr-2" /> New Experiment
          </Button>
        </div>

        {loading ? (
          <div className="space-y-4">
            {[1, 2].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6"><div className="h-16 bg-slate-200 rounded" /></CardContent>
              </Card>
            ))}
          </div>
        ) : experiments.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <FlaskConical className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No experiments yet. Create one to test ad variations.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {experiments.map((exp: any) => (
              <Card key={exp.id}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <h3 className="font-semibold text-lg">{exp.name}</h3>
                        <Badge variant={(statusColor[exp.status] || "secondary") as any}>{exp.status}</Badge>
                        <Badge variant="outline">{exp.experiment_type}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{exp.hypothesis}</p>
                      {exp.variants_json && (
                        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
                          {(Array.isArray(exp.variants_json) ? exp.variants_json : []).map((v: any, i: number) => (
                            <div key={i} className="border rounded-lg p-2.5 text-sm">
                              <div className="font-medium">{v.name || `Variant ${i}`}</div>
                              {v.conversions !== undefined && (
                                <div className="text-muted-foreground text-xs mt-1">
                                  {v.conversions} conv / {v.clicks || 0} clicks
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 ml-4">
                      {exp.status === "draft" && (
                        <Button size="sm" onClick={() => handleStart(exp.id)}>
                          <Play className="w-4 h-4 mr-1" /> Start
                        </Button>
                      )}
                      {exp.status === "running" && (
                        <Button size="sm" variant="outline" onClick={() => handleStop(exp.id)}>
                          <Square className="w-4 h-4 mr-1" /> Stop
                        </Button>
                      )}
                      {exp.status === "completed" && exp.winner_index == null && (
                        <Button size="sm" onClick={() => handlePromote(exp.id, 0)}>
                          <Trophy className="w-4 h-4 mr-1" /> Promote Winner
                        </Button>
                      )}
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
