"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Building2, Plus, Shield, ChevronRight } from "lucide-react";

interface TenantInfo {
  id: string;
  name: string;
  role: string;
  industry?: string;
  tier: string;
  slug?: string;
}

export default function TenantSelectPage() {
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    loadTenants();
  }, []);

  async function loadTenants() {
    try {
      const data = await api.get("/api/me");
      const list = data.tenants || [];
      setTenants(list);

      // Auto-select if exactly one tenant
      if (list.length === 1) {
        await switchToTenant(list[0].id);
        return;
      }
      // If zero tenants, redirect to create
      if (list.length === 0) {
        router.push("/tenant/create");
        return;
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }

  async function switchToTenant(tenantId: string) {
    setSwitching(tenantId);
    try {
      const result = await api.post("/api/me/active-tenant", { tenant_id: tenantId });
      if (result.access_token) {
        api.setToken(result.access_token);
        if (typeof window !== "undefined") {
          localStorage.setItem("tenant_id", tenantId);
          localStorage.setItem("tenant_role", result.role);
        }
      }
      router.push(`/workspace/${tenantId}/dashboard`);
    } catch (e) {
      console.error(e);
      setSwitching(null);
    }
  }

  const roleBadgeColor: Record<string, string> = {
    owner: "bg-purple-100 text-purple-700",
    admin: "bg-blue-100 text-blue-700",
    analyst: "bg-green-100 text-green-700",
    viewer: "bg-slate-100 text-slate-600",
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-pulse text-slate-400">Loading workspaces...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center font-bold text-white text-lg mx-auto mb-4">
            IA
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Select Workspace</h1>
          <p className="text-slate-500 mt-1">Choose a business to manage</p>
        </div>

        <div className="space-y-3">
          {tenants.map((t) => (
            <button
              key={t.id}
              onClick={() => switchToTenant(t.id)}
              disabled={switching !== null}
              className="w-full flex items-center justify-between p-4 bg-white border border-slate-200 rounded-xl hover:border-blue-300 hover:shadow-md transition-all group disabled:opacity-60"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                  <Building2 className="w-5 h-5 text-slate-500" />
                </div>
                <div className="text-left">
                  <div className="font-semibold text-slate-900">{t.name}</div>
                  <div className="text-xs text-slate-400">
                    {t.industry || "Business"} &bull; {t.tier}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${roleBadgeColor[t.role] || "bg-slate-100 text-slate-600"}`}>
                  {t.role}
                </span>
                {switching === t.id ? (
                  <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-blue-500 transition-colors" />
                )}
              </div>
            </button>
          ))}
        </div>

        <button
          onClick={() => router.push("/tenant/create")}
          className="w-full mt-4 flex items-center justify-center gap-2 p-3 border-2 border-dashed border-slate-300 rounded-xl text-slate-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span className="font-medium">Create New Business</span>
        </button>
      </div>
    </div>
  );
}
