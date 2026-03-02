"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Scale, ShieldCheck, ShieldAlert, Search, History } from "lucide-react";
import { api } from "@/lib/api";

export default function PolicyPage() {
  const [rules, setRules] = useState<any[]>([]);
  const [scanHistory, setScanHistory] = useState<any[]>([]);
  const [scanTexts, setScanTexts] = useState("");
  const [scanResult, setScanResult] = useState<any>(null);
  const [strictMode, setStrictMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [r, h] = await Promise.all([
        api.get(`/api/v2/policy/rules?tenant_id=${tenantId}&strict_mode=${strictMode}`),
        api.get(`/api/v2/policy/scan-history?tenant_id=${tenantId}`),
      ]);
      setRules(r);
      setScanHistory(h);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function runScan() {
    if (!scanTexts.trim()) return;
    const texts = scanTexts.split("\n").filter((t: string) => t.trim());
    const result = await api.post("/api/v2/policy/scan", {
      tenant_id: tenantId, texts, strict_mode: strictMode,
      entity_type: "ad", entity_ref: "manual_scan",
    });
    setScanResult(result);
    await loadAll();
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Policy Compliance</h1>
            <p className="text-slate-500 mt-1">Scan ad copy for Google Ads policy violations before submission</p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={strictMode} onChange={(e) => { setStrictMode(e.target.checked); }} className="rounded" />
            <span className="font-medium">Strict Mode</span>
          </label>
        </div>

        {/* Live Scanner */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Search className="w-5 h-5" /> Ad Copy Scanner</CardTitle>
            <CardDescription>Paste headlines and descriptions (one per line) to check for violations</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <textarea
              className="w-full border rounded-lg p-3 text-sm min-h-[120px] focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder={"#1 Best Plumber in Town\nGuaranteed Results in 24 Hours\nFree Estimates — Call Now"}
              value={scanTexts}
              onChange={(e) => setScanTexts(e.target.value)}
            />
            <Button onClick={runScan} disabled={!scanTexts.trim()}>
              <Scale className="w-4 h-4 mr-2" /> Scan for Violations
            </Button>

            {scanResult && (
              <div className={`p-4 rounded-lg ${scanResult.passed ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"}`}>
                <div className="flex items-center gap-2 mb-2">
                  {scanResult.passed ? (
                    <><ShieldCheck className="w-5 h-5 text-green-600" /><span className="font-medium text-green-800">All Clear</span></>
                  ) : (
                    <><ShieldAlert className="w-5 h-5 text-red-600" /><span className="font-medium text-red-800">Violations Found</span></>
                  )}
                </div>
                {(scanResult.warnings || []).length > 0 && (
                  <div className="space-y-2 mt-3">
                    {scanResult.warnings.map((w: any, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm">
                        <Badge variant={w.severity === "error" ? "destructive" : "outline"} className="text-xs mt-0.5">{w.severity}</Badge>
                        <div>
                          <div className="font-medium">{w.description}</div>
                          <div className="text-xs text-slate-500">Category: {w.category} &bull; Matched: {(w.matched || []).join(", ")}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Active Rules */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Scale className="w-5 h-5" /> Active Rules ({rules.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {rules.map((r: any) => (
                  <div key={r.id} className="flex items-center gap-2 p-2 border-b text-sm">
                    <Badge variant={r.severity === "error" ? "destructive" : r.severity === "warning" ? "outline" : "secondary"} className="text-xs">
                      {r.severity}
                    </Badge>
                    <div className="flex-1">
                      <div className="font-medium">{r.description}</div>
                      <div className="text-xs text-slate-400">{r.category} &bull; Pattern: <code className="bg-slate-100 px-1 rounded">{r.pattern}</code></div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Scan History */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><History className="w-5 h-5" /> Scan History</CardTitle>
            </CardHeader>
            <CardContent>
              {scanHistory.length === 0 ? (
                <p className="text-sm text-slate-500">No scans yet.</p>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {scanHistory.map((s: any) => (
                    <div key={s.id} className="flex items-center justify-between p-2 border-b text-sm">
                      <div>
                        <div className="font-medium">{s.entity_ref}</div>
                        <div className="text-xs text-slate-400">{s.entity_type} &bull; {new Date(s.created_at).toLocaleString()}</div>
                      </div>
                      <Badge variant={s.passed ? "default" : "destructive"}>
                        {s.passed ? "Passed" : `${(s.warnings || []).length} issues`}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
