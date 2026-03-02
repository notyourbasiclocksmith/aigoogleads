"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Crosshair, Activity, Upload, DollarSign, CheckCircle, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

export default function ConversionsPage() {
  const [ga4Status, setGa4Status] = useState<any>(null);
  const [healthReports, setHealthReports] = useState<any[]>([]);
  const [uploads, setUploads] = useState<any[]>([]);
  const [profitModel, setProfitModel] = useState<any>(null);
  const [propertyId, setPropertyId] = useState("");
  const [profitForm, setProfitForm] = useState({ avg_job_value: "", gross_margin_pct: "", close_rate_estimate: "", refund_rate_estimate: "", desired_profit_buffer_pct: "" });
  const [loading, setLoading] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [ga4, health, ups, profit] = await Promise.all([
        api.get(`/api/v2/conversions/ga4/status?tenant_id=${tenantId}`),
        api.get(`/api/v2/conversions/tracking/health?tenant_id=${tenantId}`),
        api.get(`/api/v2/conversions/offline-conversions/uploads?tenant_id=${tenantId}`),
        api.get(`/api/v2/conversions/profit-model?tenant_id=${tenantId}`),
      ]);
      setGa4Status(ga4);
      setHealthReports(health);
      setUploads(ups);
      setProfitModel(profit);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function connectGA4() {
    if (!propertyId) return;
    await api.post("/api/v2/conversions/ga4/connect", { tenant_id: tenantId, property_id: propertyId });
    await loadAll();
  }

  async function runHealthCheck() {
    await api.post(`/api/v2/conversions/tracking/health/run?tenant_id=${tenantId}`);
    await loadAll();
  }

  async function updateProfitModel() {
    const body: any = { tenant_id: tenantId };
    if (profitForm.avg_job_value) body.avg_job_value = parseFloat(profitForm.avg_job_value);
    if (profitForm.gross_margin_pct) body.gross_margin_pct = parseFloat(profitForm.gross_margin_pct);
    if (profitForm.close_rate_estimate) body.close_rate_estimate = parseFloat(profitForm.close_rate_estimate);
    if (profitForm.refund_rate_estimate) body.refund_rate_estimate = parseFloat(profitForm.refund_rate_estimate);
    if (profitForm.desired_profit_buffer_pct) body.desired_profit_buffer_pct = parseFloat(profitForm.desired_profit_buffer_pct);
    const result = await api.put("/api/v2/conversions/profit-model", body);
    setProfitModel(result);
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Conversion Truth Layer</h1>
          <p className="text-slate-500 mt-1">GA4 integration, tracking health, offline conversions, and profit optimization</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* GA4 Integration */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Activity className="w-5 h-5" /> GA4 Integration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {ga4Status?.connected ? (
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 text-green-500" />
                  <span className="text-sm">Connected — Property: {ga4Status.property_id}</span>
                  {ga4Status.last_sync_at && <span className="text-xs text-slate-400 ml-auto">Last sync: {new Date(ga4Status.last_sync_at).toLocaleDateString()}</span>}
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-slate-500">Connect your GA4 property to cross-reference conversion data.</p>
                  <div className="flex gap-2">
                    <Input placeholder="GA4 Property ID" value={propertyId} onChange={(e) => setPropertyId(e.target.value)} />
                    <Button onClick={connectGA4} disabled={!propertyId}>Connect</Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Tracking Health */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Crosshair className="w-5 h-5" /> Tracking Health</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button size="sm" onClick={runHealthCheck}>Run Health Check</Button>
              {healthReports.length > 0 && (
                <div className="space-y-2 mt-3">
                  {(healthReports[0]?.report?.checks || []).map((check: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <Badge variant={check.status === "pass" ? "default" : check.status === "warn" ? "outline" : "destructive"} className="text-xs">
                        {check.status}
                      </Badge>
                      <span>{check.name}</span>
                      <span className="text-xs text-slate-400 ml-auto">{check.detail}</span>
                    </div>
                  ))}
                  {healthReports[0]?.report?.overall_score && (
                    <div className="text-sm font-medium mt-2">Score: {healthReports[0].report.overall_score}/100</div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Profit Model */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><DollarSign className="w-5 h-5" /> Profit Optimization Model</CardTitle>
            <CardDescription>Configure your business economics so AI optimizes toward profit, not just CPA</CardDescription>
          </CardHeader>
          <CardContent>
            {profitModel && !profitModel.error && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-green-50 p-3 rounded-lg text-center">
                  <div className="text-xs text-slate-500">Expected Profit/Lead</div>
                  <div className="text-lg font-bold text-green-700">${profitModel.expected_profit_per_lead}</div>
                </div>
                <div className="bg-blue-50 p-3 rounded-lg text-center">
                  <div className="text-xs text-slate-500">Target CPA Max</div>
                  <div className="text-lg font-bold text-blue-700">${profitModel.target_cpa_max}</div>
                </div>
                <div className="bg-indigo-50 p-3 rounded-lg text-center">
                  <div className="text-xs text-slate-500">Target ROAS</div>
                  <div className="text-lg font-bold text-indigo-700">{profitModel.target_roas}x</div>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg text-center">
                  <div className="text-xs text-slate-500">Revenue/Lead</div>
                  <div className="text-lg font-bold text-slate-700">${profitModel.expected_revenue_per_lead}</div>
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Input placeholder="Avg Job Value ($)" value={profitForm.avg_job_value} onChange={(e) => setProfitForm({ ...profitForm, avg_job_value: e.target.value })} />
              <Input placeholder="Gross Margin (0-1)" value={profitForm.gross_margin_pct} onChange={(e) => setProfitForm({ ...profitForm, gross_margin_pct: e.target.value })} />
              <Input placeholder="Close Rate (0-1)" value={profitForm.close_rate_estimate} onChange={(e) => setProfitForm({ ...profitForm, close_rate_estimate: e.target.value })} />
              <Input placeholder="Refund Rate (0-1)" value={profitForm.refund_rate_estimate} onChange={(e) => setProfitForm({ ...profitForm, refund_rate_estimate: e.target.value })} />
              <Input placeholder="Profit Buffer (0-1)" value={profitForm.desired_profit_buffer_pct} onChange={(e) => setProfitForm({ ...profitForm, desired_profit_buffer_pct: e.target.value })} />
            </div>
            <Button className="mt-3" onClick={updateProfitModel}>Update Profit Model</Button>
          </CardContent>
        </Card>

        {/* Offline Conversion Uploads */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Upload className="w-5 h-5" /> Offline Conversion Uploads</CardTitle>
            <CardDescription>Upload offline conversions via CSV for deduplication and Google Ads API push</CardDescription>
          </CardHeader>
          <CardContent>
            {uploads.length === 0 ? (
              <p className="text-sm text-slate-500">No uploads yet. Use the API to upload offline conversions.</p>
            ) : (
              <div className="space-y-2">
                {uploads.map((u: any) => (
                  <div key={u.id} className="flex items-center justify-between p-3 border rounded-lg text-sm">
                    <div>
                      <span className="font-medium">{u.row_count} rows</span>
                      <span className="text-slate-400 ml-2">{new Date(u.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={u.status === "completed" ? "default" : "outline"}>{u.status}</Badge>
                      <span className="text-green-600">{u.success_count} ok</span>
                      {u.error_count > 0 && <span className="text-red-500">{u.error_count} errors</span>}
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
