"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Save, Shield, Bell, Users, Link2 } from "lucide-react";

export default function SettingsPage() {
  const [profile, setProfile] = useState<any>({});
  const [guardrails, setGuardrails] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get("/api/settings/profile").catch(() => ({})),
      api.get("/api/settings/guardrails").catch(() => ({})),
    ]).then(([p, g]) => {
      setProfile(p || {});
      setGuardrails(g || {});
    }).finally(() => setLoading(false));
  }, []);

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
          <CardContent>
            <div className="flex items-center justify-between p-4 rounded-lg border">
              <div>
                <p className="font-medium">Google Ads Account</p>
                <p className="text-sm text-muted-foreground">
                  {profile.google_ads_customer_id
                    ? `Connected: ${profile.google_ads_customer_id}`
                    : "Not connected"}
                </p>
              </div>
              <Badge variant={profile.google_ads_customer_id ? "success" : "secondary"}>
                {profile.google_ads_customer_id ? "Connected" : "Disconnected"}
              </Badge>
            </div>
            {!profile.google_ads_customer_id && (
              <Button variant="outline" className="mt-3" onClick={() => window.open("/api/onboarding/step3/oauth-url", "_blank")}>
                Connect Google Ads
              </Button>
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
