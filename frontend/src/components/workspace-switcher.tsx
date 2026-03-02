"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Building2, ChevronDown, Plus, Users, Search, Check } from "lucide-react";

interface TenantInfo {
  id: string;
  name: string;
  role: string;
  industry?: string;
  tier: string;
}

export function WorkspaceSwitcher() {
  const [tenants, setTenants] = useState<TenantInfo[]>([]);
  const [activeTenantId, setActiveTenantId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [switching, setSwitching] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const params = useParams();

  const currentTenantId = (params?.tenantId as string) || activeTenantId;

  useEffect(() => {
    loadTenants();
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function loadTenants() {
    try {
      const data = await api.get("/api/me");
      setTenants(data.tenants || []);
      setActiveTenantId(data.active_tenant_id);
    } catch (e) {
      console.error(e);
    }
  }

  async function switchTenant(tenantId: string) {
    if (tenantId === currentTenantId) { setOpen(false); return; }
    setSwitching(true);
    try {
      const result = await api.post("/api/me/active-tenant", { tenant_id: tenantId });
      if (result.access_token) {
        api.setToken(result.access_token);
        if (typeof window !== "undefined") {
          localStorage.setItem("tenant_id", tenantId);
          localStorage.setItem("tenant_role", result.role);
        }
      }
      setActiveTenantId(tenantId);
      setOpen(false);
      router.push(`/workspace/${tenantId}/dashboard`);
    } catch (e) {
      console.error(e);
    }
    setSwitching(false);
  }

  const currentTenant = tenants.find((t) => t.id === currentTenantId);
  const filtered = search
    ? tenants.filter((t) => t.name.toLowerCase().includes(search.toLowerCase()))
    : tenants;

  const roleBadge: Record<string, string> = {
    owner: "bg-purple-100 text-purple-700",
    admin: "bg-blue-100 text-blue-700",
    analyst: "bg-green-100 text-green-700",
    viewer: "bg-slate-100 text-slate-600",
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors max-w-[240px]"
      >
        <div className="w-7 h-7 rounded-md bg-blue-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
          {currentTenant?.name?.charAt(0)?.toUpperCase() || "?"}
        </div>
        <div className="text-left min-w-0">
          <div className="text-sm font-semibold text-slate-900 truncate">
            {currentTenant?.name || "Select Workspace"}
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
          {/* Search */}
          {tenants.length > 3 && (
            <div className="p-2 border-b border-slate-100">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search workspaces..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  autoFocus
                />
              </div>
            </div>
          )}

          {/* Tenant list */}
          <div className="max-h-64 overflow-y-auto py-1">
            {filtered.map((t) => (
              <button
                key={t.id}
                onClick={() => switchTenant(t.id)}
                disabled={switching}
                className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-slate-50 transition-colors text-left"
              >
                <div className="w-8 h-8 rounded-md bg-slate-100 flex items-center justify-center text-sm font-bold text-slate-600 flex-shrink-0">
                  {t.name.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-slate-900 truncate">{t.name}</div>
                  <div className="text-xs text-slate-400">{t.industry || "Business"}</div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${roleBadge[t.role] || ""}`}>
                    {t.role}
                  </span>
                  {t.id === currentTenantId && <Check className="w-4 h-4 text-blue-500" />}
                </div>
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-4 text-center text-sm text-slate-400">No workspaces found</div>
            )}
          </div>

          {/* Actions */}
          <div className="border-t border-slate-100 py-1">
            <button
              onClick={() => { setOpen(false); router.push("/tenant/create"); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              <Plus className="w-4 h-4" /> Create new business
            </button>
            {currentTenantId && (
              <button
                onClick={() => { setOpen(false); router.push(`/workspace/${currentTenantId}/settings/team`); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                <Users className="w-4 h-4" /> Manage team
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
