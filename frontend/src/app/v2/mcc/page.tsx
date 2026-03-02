"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Building2, RefreshCw, Link2, Unlink, BarChart3 } from "lucide-react";
import { api } from "@/lib/api";

interface AccessibleAccount {
  id: string;
  customer_id: string;
  descriptive_name: string;
  currency: string;
  timezone: string;
  status: string;
}

interface Binding {
  id: string;
  google_customer_id: string;
  label: string;
  enabled: boolean;
}

export default function MCCPage() {
  const [accounts, setAccounts] = useState<AccessibleAccount[]>([]);
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [loading, setLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) {
      loadData();
    }
  }, [tenantId]);

  async function loadData() {
    setLoading(true);
    try {
      const [accs, binds] = await Promise.all([
        api.get(`/api/v2/mcc/accessible-accounts?tenant_id=${tenantId}`),
        api.get(`/api/v2/mcc/bindings?tenant_id=${tenantId}`),
      ]);
      setAccounts(accs);
      setBindings(binds);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }

  async function discoverAccounts() {
    setDiscovering(true);
    try {
      await api.post("/api/v2/mcc/discover-accounts", { tenant_id: tenantId });
      await loadData();
    } catch (e) {
      console.error(e);
    }
    setDiscovering(false);
  }

  async function bindAccount(customerId: string) {
    try {
      await api.post("/api/v2/mcc/bind-account", { tenant_id: tenantId, google_customer_id: customerId });
      await loadData();
    } catch (e) {
      console.error(e);
    }
  }

  async function unbindAccount(customerId: string) {
    try {
      await api.post("/api/v2/mcc/unbind-account", { tenant_id: tenantId, google_customer_id: customerId });
      await loadData();
    } catch (e) {
      console.error(e);
    }
  }

  const boundIds = new Set(bindings.map((b) => b.google_customer_id));

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">MCC / Agency Mode</h1>
            <p className="text-slate-500 mt-1">Manage Google Ads Manager accounts and child account bindings</p>
          </div>
          <Button onClick={discoverAccounts} disabled={discovering}>
            <RefreshCw className={`w-4 h-4 mr-2 ${discovering ? "animate-spin" : ""}`} />
            {discovering ? "Discovering..." : "Discover Accounts"}
          </Button>
        </div>

        {/* Bound Accounts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Link2 className="w-5 h-5" /> Bound Accounts ({bindings.length})
            </CardTitle>
            <CardDescription>Accounts actively managed by this tenant</CardDescription>
          </CardHeader>
          <CardContent>
            {bindings.length === 0 ? (
              <p className="text-sm text-slate-500">No accounts bound yet. Discover and bind accounts below.</p>
            ) : (
              <div className="space-y-3">
                {bindings.map((b) => (
                  <div key={b.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                    <div>
                      <div className="font-medium text-sm">{b.label || b.google_customer_id}</div>
                      <div className="text-xs text-slate-500">CID: {b.google_customer_id}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={b.enabled ? "default" : "secondary"}>
                        {b.enabled ? "Active" : "Disabled"}
                      </Badge>
                      <Button size="sm" variant="outline" onClick={() => unbindAccount(b.google_customer_id)}>
                        <Unlink className="w-3 h-3 mr-1" /> Unbind
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Discovered Accounts */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5" /> Accessible Accounts ({accounts.length})
            </CardTitle>
            <CardDescription>Child accounts discovered from your MCC</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-slate-500">Loading...</p>
            ) : accounts.length === 0 ? (
              <p className="text-sm text-slate-500">No accounts discovered. Click Discover Accounts to scan your MCC.</p>
            ) : (
              <div className="space-y-2">
                {accounts.map((acc) => (
                  <div key={acc.id} className="flex items-center justify-between p-3 border rounded-lg">
                    <div>
                      <div className="font-medium text-sm">{acc.descriptive_name}</div>
                      <div className="text-xs text-slate-500">
                        CID: {acc.customer_id} &bull; {acc.currency} &bull; {acc.timezone}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={acc.status === "ENABLED" ? "default" : "secondary"}>{acc.status}</Badge>
                      {boundIds.has(acc.customer_id) ? (
                        <Badge variant="outline">Bound</Badge>
                      ) : (
                        <Button size="sm" onClick={() => bindAccount(acc.customer_id)}>
                          <Link2 className="w-3 h-3 mr-1" /> Bind
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Rollup KPIs */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5" /> Rollup KPIs
            </CardTitle>
            <CardDescription>Aggregated metrics across all bound accounts</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {["Impressions", "Clicks", "Cost", "Conversions", "Conv. Value"].map((label) => (
                <div key={label} className="text-center p-3 bg-slate-50 rounded-lg">
                  <div className="text-xs text-slate-500">{label}</div>
                  <div className="text-lg font-bold text-slate-900 mt-1">--</div>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-3">Rollup data will populate once accounts are bound and synced.</p>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
