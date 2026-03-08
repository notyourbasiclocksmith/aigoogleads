"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Save, Shield, Bell, Users, Link2, RefreshCw, CheckCircle2, XCircle, Loader2, BarChart3, Zap } from "lucide-react";

export default function SettingsPage() {
  const [profile, setProfile] = useState<any>({});
  const [guardrails, setGuardrails] = useState<any>({});
  const [accounts, setAccounts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    Promise.all([
      api.get("/api/settings/profile").catch(() => ({})),
      api.get("/api/settings/guardrails").catch(() => ({})),
      api.get("/api/ads/accounts").catch(() => []),
    ]).then(([p, g, a]) => {
      setProfile(p || {});
      setGuardrails(g || {});
      const accts = Array.isArray(a) ? a : [];
      setAccounts(accts);
      // If an account is already syncing, start polling
      const active = accts.find((acc: any) => acc.sync_status === "syncing");
      if (active) {
        setSyncStatus({ sync_status: active.sync_status, sync_message: active.sync_message, sync_progress: active.sync_progress });
        startPolling(active.id);
      }
    }).finally(() => setLoading(false));
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const startPolling = useCallback((accountId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.get(`/api/ads/accounts/${accountId}/sync-status`);
        setSyncStatus(status);
        if (status.sync_status === "completed" || status.sync_status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          // Refresh accounts list
          const a = await api.get("/api/ads/accounts").catch(() => []);
          setAccounts(Array.isArray(a) ? a : []);
        }
      } catch (e) { console.error("Poll error:", e); }
    }, 2000);
  }, []);

  async function triggerSync() {
    const active = accounts.find((a: any) => a.is_active);
    if (!active) return;
    setSyncStatus({ sync_status: "syncing", sync_message: "Starting sync...", sync_progress: 0 });
    try {
      await api.post(`/api/ads/accounts/${active.id}/sync`);
      startPolling(active.id);
    } catch (e) { console.error(e); setSyncStatus(null); }
  }

  async function saveProfile() {
    setSaving(true);
    try {
      await api.put("/api/settings/profile", profile);
      alert("Profile saved!");
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  async function saveGuardrails() {
    setSaving(true);
    try {
      await api.put("/api/settings/guardrails", guardrails);
      alert("Guardrails saved!");
    } catch (e) { console.error(e); }
    finally { setSaving(false); }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-6"><div className="h-24 bg-slate-200 rounded" /></CardContent>
            </Card>
          ))}
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
          <p className="text-muted-foreground">Manage your account, integrations, and AI guardrails</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Users className="w-5 h-5" /> Business Profile
            </CardTitle>
            <CardDescription>Update your business details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Business Name</label>
                <Input
                  value={profile.business_name || ""}
                  onChange={(e) => setProfile({ ...profile, business_name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Industry</label>
                <Input
                  value={profile.industry || ""}
                  onChange={(e) => setProfile({ ...profile, industry: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Phone</label>
                <Input
                  value={profile.phone || ""}
                  onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Website</label>
                <Input
                  value={profile.website_url || ""}
                  onChange={(e) => setProfile({ ...profile, website_url: e.target.value })}
                />
              </div>
            </div>
            <Button onClick={saveProfile} disabled={saving}>
              <Save className="w-4 h-4 mr-2" /> {saving ? "Saving..." : "Save Profile"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Link2 className="w-5 h-5" /> Google Ads Connection
            </CardTitle>
            <CardDescription>Manage your Google Ads account integration</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {accounts.map((acct: any) => (
              <div key={acct.id} className="p-4 rounded-lg border space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{acct.account_name || "Google Ads Account"}</p>
                    <p className="text-sm text-muted-foreground">
                      Customer ID: {acct.customer_id}
                    </p>
                  </div>
                  <Badge variant={acct.is_active ? "default" : "secondary"}>
                    {acct.is_active ? "Connected" : "Disconnected"}
                  </Badge>
                </div>

                {/* Sync Progress */}
                {syncStatus && syncStatus.sync_status === "syncing" && (
                  <div className="space-y-2 p-3 rounded-lg bg-blue-50 border border-blue-200">
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                      <span className="text-sm font-medium text-blue-800">
                        {syncStatus.sync_message || "Syncing..."}
                      </span>
                    </div>
                    <div className="w-full bg-blue-100 rounded-full h-2.5">
                      <div
                        className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
                        style={{ width: `${syncStatus.sync_progress || 0}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-xs text-blue-600">
                      <span>{syncStatus.sync_progress || 0}% complete</span>
                      <span>
                        {syncStatus.campaigns_synced > 0 && `${syncStatus.campaigns_synced} campaigns`}
                        {syncStatus.conversions_synced > 0 && ` · ${syncStatus.conversions_synced} conversions`}
                      </span>
                    </div>
                  </div>
                )}

                {syncStatus && syncStatus.sync_status === "completed" && (
                  <div className="p-3 rounded-lg bg-green-50 border border-green-200 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-green-600" />
                    <span className="text-sm text-green-800">{syncStatus.sync_message}</span>
                  </div>
                )}

                {syncStatus && syncStatus.sync_status === "failed" && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2">
                    <XCircle className="w-4 h-4 text-red-600 mt-0.5" />
                    <div>
                      <span className="text-sm font-medium text-red-800">Sync Failed</span>
                      <p className="text-xs text-red-600 mt-0.5">{syncStatus.sync_message}</p>
                    </div>
                  </div>
                )}

                {/* Sync stats */}
                {(acct.campaigns_synced > 0 || acct.conversions_synced > 0) && (!syncStatus || syncStatus.sync_status !== "syncing") && (
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1"><BarChart3 className="w-3 h-3" /> {acct.campaigns_synced} campaigns</span>
                    <span className="flex items-center gap-1"><Zap className="w-3 h-3" /> {acct.conversions_synced} conversions</span>
                  </div>
                )}

                {/* Sync button + last synced */}
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={triggerSync}
                    disabled={syncStatus?.sync_status === "syncing"}
                  >
                    <RefreshCw className={`w-4 h-4 mr-2 ${syncStatus?.sync_status === "syncing" ? "animate-spin" : ""}`} />
                    {syncStatus?.sync_status === "syncing" ? "Syncing..." : "Sync Now"}
                  </Button>
                  {acct.last_sync_at && (
                    <span className="text-xs text-muted-foreground">
                      Last synced: {new Date(acct.last_sync_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            ))}

            {accounts.length === 0 && (
              <div className="text-center py-6">
                <p className="text-sm text-muted-foreground mb-3">No Google Ads accounts connected</p>
                <Button variant="outline" onClick={() => window.location.href = "/onboarding"}>
                  Connect Google Ads
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Shield className="w-5 h-5" /> AI Guardrails
            </CardTitle>
            <CardDescription>Control what the AI can do automatically</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Autonomy Mode</label>
              <select
                value={guardrails.autonomy_mode || "suggest"}
                onChange={(e) => setGuardrails({ ...guardrails, autonomy_mode: e.target.value })}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                <option value="suggest">Suggest Only</option>
                <option value="semi_auto">Semi-Autopilot</option>
                <option value="full_auto">Full Autopilot</option>
              </select>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Max Daily Budget ($)</label>
                <Input
                  type="number"
                  value={guardrails.max_daily_budget || ""}
                  onChange={(e) => setGuardrails({ ...guardrails, max_daily_budget: parseInt(e.target.value) })}
                  placeholder="500"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Max CPC ($)</label>
                <Input
                  type="number"
                  step="0.01"
                  value={guardrails.max_cpc || ""}
                  onChange={(e) => setGuardrails({ ...guardrails, max_cpc: parseFloat(e.target.value) })}
                  placeholder="15.00"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Max Budget Increase (%)</label>
                <Input
                  type="number"
                  value={guardrails.max_budget_increase_pct || ""}
                  onChange={(e) => setGuardrails({ ...guardrails, max_budget_increase_pct: parseInt(e.target.value) })}
                  placeholder="30"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Min ROAS Threshold</label>
                <Input
                  type="number"
                  step="0.1"
                  value={guardrails.min_roas || ""}
                  onChange={(e) => setGuardrails({ ...guardrails, min_roas: parseFloat(e.target.value) })}
                  placeholder="2.0"
                />
              </div>
            </div>
            <Button onClick={saveGuardrails} disabled={saving}>
              <Save className="w-4 h-4 mr-2" /> {saving ? "Saving..." : "Save Guardrails"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="w-5 h-5" /> Notifications
            </CardTitle>
            <CardDescription>Choose how you receive alerts and reports</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { key: "email_alerts", label: "Email alerts for critical events" },
              { key: "weekly_report", label: "Weekly performance digest" },
              { key: "recommendation_alerts", label: "New recommendation notifications" },
              { key: "budget_alerts", label: "Budget threshold alerts" },
            ].map((n) => (
              <label key={n.key} className="flex items-center justify-between p-3 rounded-lg border cursor-pointer hover:bg-slate-50">
                <span className="text-sm font-medium">{n.label}</span>
                <input
                  type="checkbox"
                  checked={profile[n.key] ?? true}
                  onChange={(e) => setProfile({ ...profile, [n.key]: e.target.checked })}
                  className="h-4 w-4 rounded border-gray-300"
                />
              </label>
            ))}
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
