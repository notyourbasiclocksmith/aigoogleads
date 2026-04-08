"use client";

import { useEffect, useState, useRef, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Save, Shield, Bell, Users, Link2, RefreshCw, CheckCircle2, XCircle, Loader2, BarChart3, Zap, AlertTriangle, Target, ExternalLink, Send, MapPin, Globe, Star, Clock, Building2, Share2 } from "lucide-react";

function SettingsContent() {
  const searchParams = useSearchParams();
  const [profile, setProfile] = useState<any>({});
  const [guardrails, setGuardrails] = useState<any>({});
  const [accounts, setAccounts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testEmailStatus, setTestEmailStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Account picker state for pending accounts
  const [accessibleCustomers, setAccessibleCustomers] = useState<any[]>([]);
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [selectingAccount, setSelectingAccount] = useState(false);
  const [pickerError, setPickerError] = useState("");
  const [manualCustomerId, setManualCustomerId] = useState("");
  const [showManualInput, setShowManualInput] = useState(false);
  const [metaStatus, setMetaStatus] = useState<any>({ connected: false });
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [metaAdAccounts, setMetaAdAccounts] = useState<any[]>([]);
  const [loadingMetaAccounts, setLoadingMetaAccounts] = useState(false);
  const [showMetaAccountPicker, setShowMetaAccountPicker] = useState(false);
  const [selectingMetaAccount, setSelectingMetaAccount] = useState(false);

  useEffect(() => {
    // Fetch Meta connection status
    api.get("/api/meta/oauth/status").then((s: any) => setMetaStatus(s || { connected: false })).catch(() => {});

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

  // Handle OAuth callback redirect from Google
  useEffect(() => {
    if (searchParams.get("oauth_success") === "true") {
      loadAccessibleCustomers();
    } else if (searchParams.get("oauth_error")) {
      setPickerError(`Google Ads connection failed: ${searchParams.get("oauth_error")}`);
    }
  }, [searchParams]);

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

  const hasPending = accounts.some((a: any) => a.customer_id === "pending" && a.is_active);

  async function loadAccessibleCustomers() {
    setLoadingCustomers(true);
    setPickerError("");
    try {
      const customers = await api.get("/api/ads/accounts/accessible-customers");
      setAccessibleCustomers(Array.isArray(customers) ? customers : []);
      if (Array.isArray(customers) && customers.length === 0) {
        setPickerError("No accessible Google Ads accounts found. Please reconnect.");
      }
    } catch (e: any) {
      setPickerError(e.message || "Failed to load accounts from Google Ads");
      setAccessibleCustomers([]);
    }
    setLoadingCustomers(false);
  }

  async function handleSelectCustomer() {
    if (!selectedCustomerId) return;
    setSelectingAccount(true);
    setPickerError("");
    try {
      const pending = accounts.find((a: any) => a.customer_id === "pending");
      if (!pending) {
        setPickerError("No pending account found.");
        setSelectingAccount(false);
        return;
      }
      const selected = accessibleCustomers.find((c: any) => c.customer_id === selectedCustomerId);
      await api.post(`/api/ads/accounts/${pending.id}/select-customer`, {
        customer_id: selectedCustomerId,
        account_name: selected?.name || `Account ${selectedCustomerId}`,
      });
      // Refresh accounts list
      const a = await api.get("/api/ads/accounts").catch(() => []);
      setAccounts(Array.isArray(a) ? a : []);
      setAccessibleCustomers([]);
      setSelectedCustomerId("");
    } catch (e: any) {
      setPickerError(e.message || "Failed to select account");
    }
    setSelectingAccount(false);
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

  async function sendTestEmail() {
    setTestEmailStatus("sending");
    try {
      await api.post("/api/settings/notifications/test");
      setTestEmailStatus("sent");
      setTimeout(() => setTestEmailStatus("idle"), 4000);
    } catch (e: any) {
      setTestEmailStatus("error");
      alert(e?.response?.data?.detail || "Failed to send test email");
      setTimeout(() => setTestEmailStatus("idle"), 3000);
    }
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
                  onChange={(e: any) => setProfile({ ...profile, business_name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Industry</label>
                <Input
                  value={profile.industry || ""}
                  onChange={(e: any) => setProfile({ ...profile, industry: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Phone</label>
                <Input
                  value={profile.phone || ""}
                  onChange={(e: any) => setProfile({ ...profile, phone: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Website</label>
                <Input
                  value={profile.website_url || ""}
                  onChange={(e: any) => setProfile({ ...profile, website_url: e.target.value })}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm font-medium">Business Description</label>
                <textarea
                  className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={profile.description || ""}
                  onChange={(e: any) => setProfile({ ...profile, description: e.target.value })}
                  placeholder="Describe your business..."
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Service Area</label>
                <Input
                  value={profile.service_area || ""}
                  onChange={(e: any) => setProfile({ ...profile, service_area: e.target.value })}
                  placeholder="e.g. Miami, FL"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Conversion Goal</label>
                <select
                  value={profile.conversion_goal || "calls"}
                  onChange={(e: any) => setProfile({ ...profile, conversion_goal: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="calls">Phone Calls</option>
                  <option value="form_submissions">Form Submissions</option>
                  <option value="bookings">Bookings</option>
                  <option value="store_visits">Store Visits</option>
                  <option value="purchases">Purchases</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Monthly Budget ($)</label>
                <Input
                  type="number"
                  value={profile.monthly_budget || ""}
                  onChange={(e: any) => setProfile({ ...profile, monthly_budget: parseInt(e.target.value) || 0 })}
                  placeholder="1000"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Service Radius (miles)</label>
                <Input
                  type="number"
                  value={profile.service_radius_miles || ""}
                  onChange={(e: any) => setProfile({ ...profile, service_radius_miles: parseInt(e.target.value) || 0 })}
                  placeholder="25"
                />
              </div>
            </div>
            <Button onClick={saveProfile} disabled={saving}>
              <Save className="w-4 h-4 mr-2" /> {saving ? "Saving..." : "Save Profile"}
            </Button>
          </CardContent>
        </Card>

        {/* Location & Address */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <MapPin className="w-5 h-5" /> Location & Address
            </CardTitle>
            <CardDescription>
              {profile.gbp_connected
                ? "Auto-populated from Google Business Profile"
                : "Your business address for geo-targeting"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {profile.gbp_connected ? (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 border border-green-200 text-sm text-green-800 mb-2">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                <span>Synced from GBP{profile.gbp_location_name ? `: ${profile.gbp_location_name}` : ""}</span>
                {profile.google_rating && (
                  <Badge className="ml-auto bg-amber-100 text-amber-800 border-amber-200">
                    <Star className="w-3 h-3 mr-1" /> {profile.google_rating} ({profile.review_count || 0} reviews)
                  </Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto text-red-600 border-red-200 hover:bg-red-50"
                  disabled={disconnecting === "gbp"}
                  onClick={async () => {
                    if (!confirm("Disconnect Google Business Profile? You can reconnect anytime.")) return;
                    setDisconnecting("gbp");
                    try {
                      await api.delete("/api/gbp/oauth/disconnect");
                      setProfile({ ...profile, gbp_connected: false, gbp_location_name: null });
                    } catch (e) {
                      alert("Failed to disconnect GBP");
                    } finally {
                      setDisconnecting(null);
                    }
                  }}
                >
                  {disconnecting === "gbp" ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <XCircle className="w-3.5 h-3.5 mr-1" />} Disconnect
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-slate-50 border border-slate-200 text-sm text-slate-600 mb-2">
                <Globe className="w-4 h-4 flex-shrink-0" />
                <span>Google Business Profile not connected</span>
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto text-blue-600 border-blue-200 hover:bg-blue-50"
                  onClick={async () => {
                    try {
                      const res = await api.get("/api/gbp/oauth/authorize?origin=settings");
                      if (res.authorization_url) {
                        window.location.href = res.authorization_url;
                      }
                    } catch (e) {
                      alert("Failed to start GBP connection");
                    }
                  }}
                >
                  <Link2 className="w-3.5 h-3.5 mr-1" /> Connect GBP
                </Button>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm font-medium">Street Address</label>
                <Input
                  value={profile.address || ""}
                  onChange={(e: any) => setProfile({ ...profile, address: e.target.value })}
                  placeholder="123 Main St"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">City</label>
                <Input
                  value={profile.city || ""}
                  onChange={(e: any) => setProfile({ ...profile, city: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">State</label>
                <Input
                  value={profile.state || ""}
                  onChange={(e: any) => setProfile({ ...profile, state: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">ZIP Code</label>
                <Input
                  value={profile.zip_code || ""}
                  onChange={(e: any) => setProfile({ ...profile, zip_code: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Primary Category</label>
                <Input
                  value={profile.primary_category || ""}
                  disabled
                  className="bg-slate-50"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Years of Experience</label>
                <Input
                  type="number"
                  value={profile.years_experience || ""}
                  onChange={(e: any) => setProfile({ ...profile, years_experience: parseInt(e.target.value) || 0 })}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">License Info</label>
                <Input
                  value={profile.license_info || ""}
                  onChange={(e: any) => setProfile({ ...profile, license_info: e.target.value })}
                  placeholder="e.g. Licensed & Insured, #12345"
                />
              </div>
            </div>
            <Button onClick={saveProfile} disabled={saving}>
              <Save className="w-4 h-4 mr-2" /> {saving ? "Saving..." : "Save Address"}
            </Button>
          </CardContent>
        </Card>

        {/* Social & Online Presence */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Share2 className="w-5 h-5" /> Social & Online Presence
            </CardTitle>
            <CardDescription>Your social media profiles and GBP listing</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Facebook URL</label>
                <Input
                  value={profile.facebook_url || ""}
                  onChange={(e: any) => setProfile({ ...profile, facebook_url: e.target.value })}
                  placeholder="https://facebook.com/yourbusiness"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Instagram URL</label>
                <Input
                  value={profile.instagram_url || ""}
                  onChange={(e: any) => setProfile({ ...profile, instagram_url: e.target.value })}
                  placeholder="https://instagram.com/yourbusiness"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">TikTok URL</label>
                <Input
                  value={profile.tiktok_url || ""}
                  onChange={(e: any) => setProfile({ ...profile, tiktok_url: e.target.value })}
                  placeholder="https://tiktok.com/@yourbusiness"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">GBP Listing URL</label>
                <Input
                  value={profile.gbp_link || ""}
                  onChange={(e: any) => setProfile({ ...profile, gbp_link: e.target.value })}
                  placeholder="https://g.page/yourbusiness"
                />
              </div>
            </div>
            <Button onClick={saveProfile} disabled={saving}>
              <Save className="w-4 h-4 mr-2" /> {saving ? "Saving..." : "Save Social Links"}
            </Button>
          </CardContent>
        </Card>

        {/* GBP Connection */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="w-5 h-5" /> Google Business Profile
            </CardTitle>
            <CardDescription>Connect your GBP to auto-sync reviews, hours, and enable post scheduling</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {profile.gbp_connected ? (
              <div className="p-4 rounded-lg border space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{profile.gbp_location_name || "Google Business Profile"}</p>
                    <p className="text-sm text-muted-foreground">
                      {profile.google_rating && <span className="mr-3"><Star className="w-3 h-3 inline mr-1" />{profile.google_rating} ({profile.review_count} reviews)</span>}
                      {profile.primary_category && <span>{profile.primary_category}</span>}
                    </p>
                  </div>
                  <Badge variant="default">Connected</Badge>
                </div>
                {profile.gbp_last_sync && (
                  <p className="text-xs text-muted-foreground">
                    <Clock className="w-3 h-3 inline mr-1" /> Last synced: {new Date(profile.gbp_last_sync).toLocaleString()}
                  </p>
                )}
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      try {
                        await api.post("/api/gbp/sync");
                        const p = await api.get("/api/settings/profile").catch(() => ({}));
                        setProfile(p || {});
                      } catch (e: any) { alert(e.message || "Sync failed"); }
                    }}
                  >
                    <RefreshCw className="w-4 h-4 mr-2" /> Sync Now
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                    disabled={disconnecting === "gbp2"}
                    onClick={async () => {
                      if (!confirm("Disconnect Google Business Profile?")) return;
                      setDisconnecting("gbp2");
                      try {
                        await api.delete("/api/gbp/oauth/disconnect");
                        const p = await api.get("/api/settings/profile").catch(() => ({}));
                        setProfile(p || {});
                      } catch (e: any) { alert(e.message || "Failed to disconnect"); }
                      finally { setDisconnecting(null); }
                    }}
                  >
                    {disconnecting === "gbp2" ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <XCircle className="w-4 h-4 mr-2" />} Disconnect
                  </Button>
                </div>
              </div>
            ) : (
              <div className="text-center py-6">
                <Building2 className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground mb-3">Connect your Google Business Profile to auto-populate address, hours, rating, and enable post scheduling &amp; review management.</p>
                <Button
                  onClick={async () => {
                    try {
                      const res = await api.get("/api/gbp/oauth/authorize?origin=settings");
                      if (res.auth_url) window.location.href = res.auth_url;
                    } catch (e: any) {
                      alert(e.message || "Failed to start GBP connection");
                    }
                  }}
                >
                  <Building2 className="w-4 h-4 mr-2" /> Connect Google Business Profile
                </Button>
              </div>
            )}
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
            {/* Pending account picker */}
            {hasPending && (
              <div className="p-4 rounded-lg border border-amber-200 bg-amber-50 space-y-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="font-medium text-amber-800">Account setup incomplete</p>
                    <p className="text-sm text-amber-700 mt-1">
                      Google Ads is connected but you haven&apos;t selected which account to manage.
                      Click below to choose your Google Ads account.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200 flex-shrink-0"
                    disabled={disconnecting === "ads-pending"}
                    onClick={async () => {
                      if (!confirm("Disconnect Google Ads? You can reconnect with a different account.")) return;
                      setDisconnecting("ads-pending");
                      try {
                        const pending = accounts.find((a: any) => a.customer_id === "pending");
                        if (pending) await api.delete(`/api/ads/accounts/${pending.id}`);
                        const a = await api.get("/api/ads/accounts").catch(() => []);
                        setAccounts(Array.isArray(a) ? a : []);
                        setAccessibleCustomers([]);
                      } catch (e: any) {
                        alert(e.message || "Failed to disconnect");
                      } finally {
                        setDisconnecting(null);
                      }
                    }}
                  >
                    {disconnecting === "ads-pending" ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <XCircle className="w-3.5 h-3.5 mr-1" />} Disconnect
                  </Button>
                </div>

                {accessibleCustomers.length === 0 && !loadingCustomers && (
                  <Button
                    onClick={loadAccessibleCustomers}
                    disabled={loadingCustomers}
                    className="bg-amber-600 hover:bg-amber-700 text-white"
                  >
                    <Target className="w-4 h-4 mr-2" /> Load My Google Ads Accounts
                  </Button>
                )}

                {loadingCustomers && (
                  <div className="flex items-center gap-2 py-2">
                    <Loader2 className="w-4 h-4 text-amber-600 animate-spin" />
                    <span className="text-sm text-amber-700">Loading accounts from Google Ads...</span>
                  </div>
                )}

                {pickerError && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 space-y-3">
                    <p className="text-sm text-red-700">{pickerError}</p>
                    <div className="flex flex-wrap gap-2">
                      {pickerError.toLowerCase().includes("decrypt") || pickerError.toLowerCase().includes("reconnect") ? (
                        <Button
                          onClick={async () => {
                            try {
                              const res = await api.post("/api/ads/accounts/reconnect-oauth");
                              if (res.oauth_url) window.location.href = res.oauth_url;
                            } catch (e: any) {
                              setPickerError(e.message || "Failed to start reconnection");
                            }
                          }}
                          className="bg-red-600 hover:bg-red-700 text-white"
                          size="sm"
                        >
                          <ExternalLink className="w-4 h-4 mr-2" /> Reconnect Google Ads
                        </Button>
                      ) : null}
                      {!showManualInput && (
                        <Button
                          onClick={() => setShowManualInput(true)}
                          variant="outline"
                          size="sm"
                        >
                          Enter Customer ID Manually
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {showManualInput && accessibleCustomers.length === 0 && (
                  <div className="p-4 rounded-lg border border-blue-200 bg-blue-50 space-y-3">
                    <p className="text-sm text-blue-800 font-medium">Enter your Google Ads Customer ID</p>
                    <p className="text-xs text-blue-700">Find it at the top of your Google Ads dashboard (e.g. 123-456-7890)</p>
                    <div className="flex gap-2">
                      <Input
                        placeholder="e.g. 894-688-3394"
                        value={manualCustomerId}
                        onChange={(e: any) => setManualCustomerId(e.target.value)}
                        className="flex-1 bg-white"
                      />
                      <Button
                        disabled={!manualCustomerId.replace(/[-\s]/g, '').match(/^\d{7,10}$/) || selectingAccount}
                        onClick={async () => {
                          setSelectingAccount(true);
                          setPickerError("");
                          try {
                            const pending = accounts.find((a: any) => a.customer_id === "pending");
                            if (!pending) { setPickerError("No pending account found."); setSelectingAccount(false); return; }
                            await api.post(`/api/ads/accounts/${pending.id}/select-customer`, {
                              customer_id: manualCustomerId.replace(/[-\s]/g, ''),
                              account_name: `Account ${manualCustomerId}`,
                            });
                            const a = await api.get("/api/ads/accounts").catch(() => []);
                            setAccounts(Array.isArray(a) ? a : []);
                            setManualCustomerId("");
                            setShowManualInput(false);
                          } catch (e: any) {
                            setPickerError(e.message || "Failed to connect account");
                          }
                          setSelectingAccount(false);
                        }}
                      >
                        {selectingAccount ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1" />}
                        Connect
                      </Button>
                    </div>
                  </div>
                )}

                {accessibleCustomers.length > 0 && (
                  <div className="space-y-2">
                    {accessibleCustomers.map((c: any) => (
                      <button
                        key={c.customer_id}
                        onClick={() => setSelectedCustomerId(c.customer_id)}
                        className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                          selectedCustomerId === c.customer_id
                            ? "border-blue-500 bg-blue-50 ring-1 ring-blue-500/30"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <Target className={`w-5 h-5 flex-shrink-0 ${
                          selectedCustomerId === c.customer_id ? "text-blue-600" : "text-slate-400"
                        }`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-900 truncate">{c.name}</p>
                          <p className="text-xs text-slate-500">
                            ID: {c.customer_id.replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3")}
                            {c.currency ? ` · ${c.currency}` : ""}
                            {c.is_manager ? " · Manager" : ""}
                          </p>
                        </div>
                        <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                          selectedCustomerId === c.customer_id ? "border-blue-500 bg-blue-500" : "border-slate-300"
                        }`}>
                          {selectedCustomerId === c.customer_id && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                        </div>
                      </button>
                    ))}
                    <Button
                      onClick={handleSelectCustomer}
                      disabled={!selectedCustomerId || selectingAccount}
                      className="w-full mt-2"
                    >
                      {selectingAccount ? (
                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Connecting...</>
                      ) : (
                        <><CheckCircle2 className="w-4 h-4 mr-2" /> Connect Selected Account</>
                      )}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* Connected (non-pending) accounts */}
            {accounts.filter((a: any) => a.customer_id !== "pending").map((acct: any) => (
              <div key={acct.id} className="p-4 rounded-lg border space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{acct.account_name || "Google Ads Account"}</p>
                    <p className="text-sm text-muted-foreground">
                      Customer ID: {acct.customer_id.replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3")}
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

                {/* Action buttons */}
                <div className="flex items-center gap-3 flex-wrap">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={triggerSync}
                    disabled={syncStatus?.sync_status === "syncing"}
                  >
                    <RefreshCw className={`w-4 h-4 mr-2 ${syncStatus?.sync_status === "syncing" ? "animate-spin" : ""}`} />
                    {syncStatus?.sync_status === "syncing" ? "Syncing..." : "Sync Now"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      try {
                        const res = await api.post("/api/ads/accounts/reconnect-oauth");
                        if (res.oauth_url) window.location.href = res.oauth_url;
                      } catch (e: any) {
                        alert(e.message || "Failed to start reconnection");
                      }
                    }}
                  >
                    <ExternalLink className="w-4 h-4 mr-2" /> Reconnect
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                    disabled={disconnecting === `ads-${acct.id}`}
                    onClick={async () => {
                      if (!confirm("Disconnect this Google Ads account? You can reconnect later.")) return;
                      setDisconnecting(`ads-${acct.id}`);
                      try {
                        await api.delete(`/api/ads/accounts/${acct.id}`);
                        const a = await api.get("/api/ads/accounts").catch(() => []);
                        setAccounts(Array.isArray(a) ? a : []);
                        setSyncStatus(null);
                      } catch (e: any) {
                        alert(e.message || "Failed to disconnect account");
                      } finally {
                        setDisconnecting(null);
                      }
                    }}
                  >
                    {disconnecting === `ads-${acct.id}` ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <XCircle className="w-4 h-4 mr-2" />} Disconnect
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
                <Button
                  variant="outline"
                  onClick={async () => {
                    try {
                      const res = await api.post("/api/ads/accounts/reconnect-oauth");
                      if (res.oauth_url) window.location.href = res.oauth_url;
                    } catch {
                      window.location.href = "/onboarding";
                    }
                  }}
                >
                  <Link2 className="w-4 h-4 mr-2" /> Connect Google Ads
                </Button>
              </div>
            )}

            {/* Show message if only pending accounts and no real ones */}
            {accounts.length > 0 && !hasPending && accounts.filter((a: any) => a.customer_id !== "pending").length === 0 && (
              <div className="text-center py-6">
                <p className="text-sm text-muted-foreground mb-3">No Google Ads accounts connected</p>
                <Button
                  variant="outline"
                  onClick={async () => {
                    try {
                      const res = await api.post("/api/ads/accounts/reconnect-oauth");
                      if (res.oauth_url) window.location.href = res.oauth_url;
                    } catch {
                      window.location.href = "/onboarding";
                    }
                  }}
                >
                  <Link2 className="w-4 h-4 mr-2" /> Connect Google Ads
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Meta Ads (Facebook/Instagram) Connection */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Target className="w-5 h-5" /> Meta Ads (Facebook / Instagram)
            </CardTitle>
            <CardDescription>Connect your Meta ad account to manage Facebook &amp; Instagram campaigns</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {metaStatus.connected ? (
              <div className="p-4 rounded-lg border space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{metaStatus.account_name || "Meta Ad Account"}</p>
                    <p className="text-sm text-muted-foreground">
                      {metaStatus.ad_account_id && <span className="mr-3">Account: {metaStatus.ad_account_id}</span>}
                      {metaStatus.page_name && <span>Page: {metaStatus.page_name}</span>}
                    </p>
                  </div>
                  <Badge variant="default">Connected</Badge>
                </div>
                {metaStatus.sync_error && (
                  <p className="text-xs text-red-600">
                    <AlertTriangle className="w-3 h-3 inline mr-1" /> {metaStatus.sync_error}
                  </p>
                )}
                <div className="flex items-center gap-3 flex-wrap">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={loadingMetaAccounts}
                    onClick={async () => {
                      if (showMetaAccountPicker) {
                        setShowMetaAccountPicker(false);
                        return;
                      }
                      setLoadingMetaAccounts(true);
                      try {
                        const accts = await api.get("/api/meta/ad-accounts");
                        setMetaAdAccounts(Array.isArray(accts) ? accts : []);
                        setShowMetaAccountPicker(true);
                      } catch (e: any) {
                        alert(e.message || "Failed to load Meta ad accounts");
                      }
                      setLoadingMetaAccounts(false);
                    }}
                  >
                    {loadingMetaAccounts ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                    Change Account
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                    disabled={disconnecting === "meta"}
                    onClick={async () => {
                      if (!confirm("Disconnect Meta Ads?")) return;
                      setDisconnecting("meta");
                      try {
                        await api.delete("/api/meta/oauth/disconnect");
                        setMetaStatus({ connected: false });
                        setShowMetaAccountPicker(false);
                      } catch (e: any) { alert(e.message || "Failed to disconnect"); }
                      finally { setDisconnecting(null); }
                    }}
                  >
                    {disconnecting === "meta" ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <XCircle className="w-4 h-4 mr-2" />} Disconnect
                  </Button>
                </div>

                {showMetaAccountPicker && metaAdAccounts.length > 0 && (
                  <div className="space-y-2 mt-3 p-4 rounded-lg border border-blue-200 bg-blue-50">
                    <p className="text-sm font-medium text-blue-800">Select a different ad account:</p>
                    {metaAdAccounts.map((acct: any) => (
                      <button
                        key={acct.account_id || acct.id}
                        disabled={selectingMetaAccount}
                        onClick={async () => {
                          const accountId = acct.account_id || acct.id;
                          if (accountId === metaStatus.ad_account_id) return;
                          setSelectingMetaAccount(true);
                          try {
                            await api.post("/api/meta/ad-accounts/select", { account_id: accountId });
                            const s = await api.get("/api/meta/oauth/status");
                            setMetaStatus(s || { connected: false });
                            setShowMetaAccountPicker(false);
                          } catch (e: any) {
                            alert(e.message || "Failed to switch account");
                          }
                          setSelectingMetaAccount(false);
                        }}
                        className={`w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                          (acct.account_id || acct.id) === metaStatus.ad_account_id
                            ? "border-blue-500 bg-blue-100 ring-1 ring-blue-500/30"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <Target className={`w-5 h-5 flex-shrink-0 ${
                          (acct.account_id || acct.id) === metaStatus.ad_account_id ? "text-blue-600" : "text-slate-400"
                        }`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-900 truncate">{acct.name || "Ad Account"}</p>
                          <p className="text-xs text-slate-500">
                            ID: {acct.account_id || acct.id}
                            {acct.currency ? ` · ${acct.currency}` : ""}
                          </p>
                        </div>
                        {(acct.account_id || acct.id) === metaStatus.ad_account_id && (
                          <Badge variant="default" className="text-xs">Current</Badge>
                        )}
                      </button>
                    ))}
                    {selectingMetaAccount && (
                      <div className="flex items-center gap-2 py-2">
                        <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                        <span className="text-sm text-blue-700">Switching account...</span>
                      </div>
                    )}
                  </div>
                )}

                {showMetaAccountPicker && metaAdAccounts.length === 0 && !loadingMetaAccounts && (
                  <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 mt-3">
                    <p className="text-sm text-amber-700">No other ad accounts found. You may need to reconnect with a different Meta account.</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-6">
                <Target className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground mb-3">Connect your Meta Ads account to create and manage Facebook &amp; Instagram ad campaigns through IntelliDrive Operator.</p>
                <Button
                  onClick={async () => {
                    try {
                      const res = await api.get("/api/meta/oauth/authorize?origin=settings");
                      if (res.auth_url) window.location.href = res.auth_url;
                    } catch (e: any) {
                      alert(e.message || "Failed to start Meta connection");
                    }
                  }}
                >
                  <Target className="w-4 h-4 mr-2" /> Connect Meta Ads
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
          <CardContent className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Notification Email</label>
              <p className="text-xs text-muted-foreground mb-2">Where should we send email alerts and reports?</p>
              <Input
                type="email"
                placeholder="you@example.com"
                value={profile.notification_email || ""}
                onChange={(e) => setProfile({ ...profile, notification_email: e.target.value })}
              />
              {!profile.notification_email && (
                <p className="text-xs text-amber-600 mt-1 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> No email set — notifications won&apos;t be delivered
                </p>
              )}
            </div>
            <div className="border-t pt-3 space-y-2">
              <p className="text-sm font-medium text-slate-700">Alert Types</p>
              {[
                { key: "email_alerts", label: "Email alerts for critical events", desc: "Budget overruns, campaign errors, account issues" },
                { key: "weekly_report", label: "Weekly performance digest", desc: "Summary of all campaign performance every Monday" },
                { key: "recommendation_alerts", label: "New recommendation notifications", desc: "When Google or AI suggests optimizations" },
                { key: "budget_alerts", label: "Budget threshold alerts", desc: "When spend approaches or exceeds daily limits" },
              ].map((n) => (
                <label key={n.key} className="flex items-center justify-between p-3 rounded-lg border cursor-pointer hover:bg-slate-50">
                  <div>
                    <span className="text-sm font-medium">{n.label}</span>
                    <p className="text-xs text-muted-foreground">{n.desc}</p>
                  </div>
                  <input
                    type="checkbox"
                    checked={profile[n.key] ?? true}
                    onChange={(e) => setProfile({ ...profile, [n.key]: e.target.checked })}
                    className="h-4 w-4 rounded border-gray-300 shrink-0 ml-3"
                  />
                </label>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <Button onClick={saveProfile} disabled={saving}>
                <Save className="w-4 h-4 mr-2" /> {saving ? "Saving..." : "Save Notifications"}
              </Button>
              <Button
                variant="outline"
                onClick={sendTestEmail}
                disabled={testEmailStatus === "sending" || !profile.notification_email}
              >
                {testEmailStatus === "sending" ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Sending...</>
                ) : testEmailStatus === "sent" ? (
                  <><CheckCircle2 className="w-4 h-4 mr-2 text-green-500" /> Sent!</>
                ) : testEmailStatus === "error" ? (
                  <><XCircle className="w-4 h-4 mr-2 text-red-500" /> Failed</>
                ) : (
                  <><Send className="w-4 h-4 mr-2" /> Send Test Email</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>}>
      <SettingsContent />
    </Suspense>
  );
}
