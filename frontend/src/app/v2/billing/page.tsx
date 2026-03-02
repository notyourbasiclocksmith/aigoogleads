"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CreditCard, Zap, ArrowUpRight, BarChart3, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";

export default function BillingPage() {
  const [billingStatus, setBillingStatus] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [status, usg, p] = await Promise.all([
        api.get(`/api/v2/billing/status?tenant_id=${tenantId}`),
        api.get(`/api/v2/billing/usage?tenant_id=${tenantId}`),
        api.get("/api/v2/billing/plans"),
      ]);
      setBillingStatus(status);
      setUsage(usg);
      setPlans(p.plans || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function openCheckout(plan: string) {
    try {
      const result = await api.post("/api/v2/billing/checkout", {
        tenant_id: tenantId, plan,
        success_url: window.location.origin + "/v2/billing?success=true",
        cancel_url: window.location.origin + "/v2/billing?canceled=true",
      });
      if (result.checkout_url) window.location.href = result.checkout_url;
    } catch (e) { console.error(e); }
  }

  async function openPortal() {
    try {
      const result = await api.post("/api/v2/billing/portal", {
        tenant_id: tenantId,
        return_url: window.location.origin + "/v2/billing",
      });
      if (result.portal_url) window.location.href = result.portal_url;
    } catch (e) { console.error(e); }
  }

  const usageMetrics = [
    { key: "prompts", label: "AI Prompts", icon: Zap },
    { key: "serp_scans", label: "SERP Scans", icon: BarChart3 },
    { key: "seopix_credits", label: "Seopix Credits", icon: CreditCard },
    { key: "accounts_connected", label: "Accounts", icon: CheckCircle },
    { key: "autopilot_actions", label: "Autopilot Actions", icon: ArrowUpRight },
  ];

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Billing & Usage</h1>
            <p className="text-slate-500 mt-1">Manage your subscription, view usage, and upgrade your plan</p>
          </div>
          {billingStatus?.stripe_customer_id && (
            <Button variant="outline" onClick={openPortal}>
              <CreditCard className="w-4 h-4 mr-2" /> Manage Subscription
            </Button>
          )}
        </div>

        {/* Current Plan */}
        <Card>
          <CardHeader>
            <CardTitle>Current Plan</CardTitle>
          </CardHeader>
          <CardContent>
            {billingStatus ? (
              <div className="flex items-center gap-4">
                <div className="bg-indigo-50 px-4 py-2 rounded-lg">
                  <span className="text-2xl font-bold text-indigo-700 capitalize">{billingStatus.plan}</span>
                </div>
                <Badge variant={billingStatus.status === "active" ? "default" : "destructive"}>
                  {billingStatus.status}
                </Badge>
                {billingStatus.current_period_end && (
                  <span className="text-sm text-slate-500">
                    Renews: {new Date(billingStatus.current_period_end).toLocaleDateString()}
                  </span>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Loading...</p>
            )}
          </CardContent>
        </Card>

        {/* Usage Dashboard */}
        <Card>
          <CardHeader>
            <CardTitle>Usage This Period</CardTitle>
            <CardDescription>Current billing period consumption vs plan limits</CardDescription>
          </CardHeader>
          <CardContent>
            {usage ? (
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                {usageMetrics.map((m) => {
                  const used = usage.usage?.[m.key] || 0;
                  const limit = usage.limits?.[m.key] || 0;
                  const pct = usage.usage_pct?.[m.key] || 0;
                  const isUnlimited = limit === -1;
                  const Icon = m.icon;
                  return (
                    <div key={m.key} className="p-4 border rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <Icon className="w-4 h-4 text-slate-500" />
                        <span className="text-xs font-medium text-slate-500">{m.label}</span>
                      </div>
                      <div className="text-xl font-bold text-slate-900">
                        {used}{!isUnlimited && <span className="text-sm font-normal text-slate-400">/{limit}</span>}
                        {isUnlimited && <span className="text-xs font-normal text-slate-400 ml-1">unlimited</span>}
                      </div>
                      {!isUnlimited && (
                        <div className="mt-2 w-full bg-slate-100 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full ${pct > 90 ? "bg-red-500" : pct > 70 ? "bg-yellow-500" : "bg-blue-500"}`}
                            style={{ width: `${Math.min(pct, 100)}%` }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-500">Loading usage data...</p>
            )}
          </CardContent>
        </Card>

        {/* Plans */}
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-4">Available Plans</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {plans.map((plan: any) => {
              const isCurrent = billingStatus?.plan === plan.name;
              return (
                <Card key={plan.name} className={isCurrent ? "ring-2 ring-indigo-500" : ""}>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span className="capitalize">{plan.label}</span>
                      {isCurrent && <Badge>Current</Badge>}
                    </CardTitle>
                    <CardDescription className="text-xl font-bold text-slate-900">{plan.price}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2 text-sm text-slate-600 mb-4">
                      {Object.entries(plan.limits).map(([key, value]: [string, any]) => (
                        <li key={key} className="flex items-center gap-2">
                          <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                          <span>{key.replace(/_/g, " ")}: <strong>{value === -1 ? "Unlimited" : value}</strong></span>
                        </li>
                      ))}
                    </ul>
                    {!isCurrent && (
                      <Button className="w-full" onClick={() => openCheckout(plan.name)}>
                        Upgrade to {plan.label}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
