"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { GitBranch, Calendar, Snowflake, ShieldAlert, Play, RotateCcw, Trash2, Plus } from "lucide-react";
import { api } from "@/lib/api";

export default function ChangeManagementPage() {
  const [changeSets, setChangeSets] = useState<any[]>([]);
  const [freezeWindows, setFreezeWindows] = useState<any[]>([]);
  const [freezeStatus, setFreezeStatus] = useState<any>(null);
  const [rollbackPolicy, setRollbackPolicy] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [freezeForm, setFreezeForm] = useState({ start_at: "", end_at: "", reason: "" });
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [sets, windows, status, policy] = await Promise.all([
        api.get(`/api/v2/changes/change-sets?tenant_id=${tenantId}`),
        api.get(`/api/v2/changes/freeze-windows?tenant_id=${tenantId}`),
        api.get(`/api/v2/changes/freeze-status?tenant_id=${tenantId}`),
        api.get(`/api/v2/changes/rollback-policies?tenant_id=${tenantId}`),
      ]);
      setChangeSets(sets);
      setFreezeWindows(windows);
      setFreezeStatus(status);
      setRollbackPolicy(policy);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function applyChangeSet(id: string) {
    await api.post("/api/v2/changes/change-sets/apply", { tenant_id: tenantId, change_set_id: id });
    await loadAll();
  }

  async function rollbackChangeSet(id: string) {
    await api.post("/api/v2/changes/change-sets/rollback", { tenant_id: tenantId, change_set_id: id });
    await loadAll();
  }

  async function createFreezeWindow() {
    if (!freezeForm.start_at || !freezeForm.end_at || !freezeForm.reason) return;
    await api.post("/api/v2/changes/freeze-windows", { tenant_id: tenantId, ...freezeForm });
    setFreezeForm({ start_at: "", end_at: "", reason: "" });
    await loadAll();
  }

  async function deleteFreezeWindow(id: string) {
    await api.delete(`/api/v2/changes/freeze-windows/${id}?tenant_id=${tenantId}`);
    await loadAll();
  }

  const statusColor: Record<string, string> = {
    draft: "outline", scheduled: "secondary", applying: "default",
    applied: "default", rolled_back: "destructive", failed: "destructive",
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Change Management</h1>
          <p className="text-slate-500 mt-1">Change sets, scheduled deploys, freeze windows, and rollback policies</p>
        </div>

        {/* Freeze Status Banner */}
        {freezeStatus?.frozen && (
          <div className="bg-blue-50 border border-blue-200 p-4 rounded-lg flex items-center gap-3">
            <Snowflake className="w-5 h-5 text-blue-600" />
            <div>
              <div className="font-medium text-blue-900">Freeze Window Active</div>
              <div className="text-sm text-blue-700">{freezeStatus.reason} — ends {new Date(freezeStatus.ends_at).toLocaleString()}</div>
            </div>
          </div>
        )}

        {/* Change Sets */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><GitBranch className="w-5 h-5" /> Change Sets</CardTitle>
            <CardDescription>Group and schedule atomic change deployments</CardDescription>
          </CardHeader>
          <CardContent>
            {changeSets.length === 0 ? (
              <p className="text-sm text-slate-500">No change sets created yet. Use the API or optimizations page to create change sets.</p>
            ) : (
              <div className="space-y-3">
                {changeSets.map((cs: any) => (
                  <div key={cs.id} className="flex items-center justify-between p-4 border rounded-lg">
                    <div>
                      <div className="font-medium">{cs.name}</div>
                      <div className="text-xs text-slate-500">
                        {cs.items_count} changes &bull; Created {new Date(cs.created_at).toLocaleDateString()}
                        {cs.scheduled_for && <> &bull; Scheduled: {new Date(cs.scheduled_for).toLocaleString()}</>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={(statusColor[cs.status] as any) || "outline"}>{cs.status}</Badge>
                      {(cs.status === "draft" || cs.status === "scheduled") && (
                        <Button size="sm" onClick={() => applyChangeSet(cs.id)}>
                          <Play className="w-3 h-3 mr-1" /> Apply
                        </Button>
                      )}
                      {cs.status === "applied" && (
                        <Button size="sm" variant="outline" onClick={() => rollbackChangeSet(cs.id)}>
                          <RotateCcw className="w-3 h-3 mr-1" /> Rollback
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Freeze Windows */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Snowflake className="w-5 h-5" /> Freeze Windows</CardTitle>
              <CardDescription>Block autopilot during critical periods</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-2">
                <Input type="datetime-local" placeholder="Start" value={freezeForm.start_at} onChange={(e) => setFreezeForm({ ...freezeForm, start_at: e.target.value })} />
                <Input type="datetime-local" placeholder="End" value={freezeForm.end_at} onChange={(e) => setFreezeForm({ ...freezeForm, end_at: e.target.value })} />
                <Input placeholder="Reason" value={freezeForm.reason} onChange={(e) => setFreezeForm({ ...freezeForm, reason: e.target.value })} />
                <Button size="sm" onClick={createFreezeWindow}><Plus className="w-3 h-3 mr-1" /> Add Freeze Window</Button>
              </div>
              {freezeWindows.length > 0 && (
                <div className="space-y-2 mt-3">
                  {freezeWindows.map((w: any) => (
                    <div key={w.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg text-sm">
                      <div>
                        <div className="font-medium">{w.reason}</div>
                        <div className="text-xs text-slate-400">{new Date(w.start_at).toLocaleString()} — {new Date(w.end_at).toLocaleString()}</div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => deleteFreezeWindow(w.id)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Rollback Policy */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><ShieldAlert className="w-5 h-5" /> Rollback Policy</CardTitle>
              <CardDescription>Auto-revert when metrics breach thresholds</CardDescription>
            </CardHeader>
            <CardContent>
              {rollbackPolicy ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Badge variant={rollbackPolicy.enabled ? "default" : "secondary"}>
                      {rollbackPolicy.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </div>
                  {(rollbackPolicy.rules || []).length === 0 ? (
                    <p className="text-sm text-slate-500">No rollback rules configured yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {rollbackPolicy.rules.map((rule: any, i: number) => (
                        <div key={i} className="p-2 bg-slate-50 rounded text-sm">
                          If <strong>{rule.metric}</strong> {rule.condition.replace("_", " ")} by &gt; <strong>{rule.threshold}%</strong> in {rule.window_days}d
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-slate-500">No rollback policy configured. Use the API to set trigger rules.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
