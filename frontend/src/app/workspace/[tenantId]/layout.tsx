"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import {
  LayoutDashboard, Target, Megaphone, Wand2, Palette,
  Search, Zap, FlaskConical, FileText, Settings, LogOut,
  Shield, Building2, GitBranch, Plug, Scale,
  CreditCard, Bell, Trophy, Crosshair,
} from "lucide-react";

interface TenantInfo {
  id: string;
  name: string;
  role: string;
}

const makeNav = (tenantId: string) => [
  { label: "Dashboard", href: `/workspace/${tenantId}/dashboard`, icon: LayoutDashboard },
  { label: "Accounts", href: `/workspace/${tenantId}/ads/accounts`, icon: Target },
  { label: "Audit", href: `/workspace/${tenantId}/ads/audit`, icon: Shield },
  { label: "Command Console", href: `/workspace/${tenantId}/ads/prompt`, icon: Wand2 },
  { label: "Campaigns", href: `/workspace/${tenantId}/ads/campaigns`, icon: Megaphone },
  { label: "Creative Studio", href: `/workspace/${tenantId}/creative`, icon: Palette },
  { label: "Competitors", href: `/workspace/${tenantId}/intel/competitors`, icon: Search },
  { label: "Optimizations", href: `/workspace/${tenantId}/optimizations`, icon: Zap },
  { label: "Experiments", href: `/workspace/${tenantId}/experiments`, icon: FlaskConical },
  { label: "Reports", href: `/workspace/${tenantId}/reports`, icon: FileText },
  { label: "Settings", href: `/workspace/${tenantId}/settings`, icon: Settings },
];

const makeV2Nav = (tenantId: string) => [
  { label: "MCC / Agency", href: `/workspace/${tenantId}/v2/mcc`, icon: Building2 },
  { label: "Conversions", href: `/workspace/${tenantId}/v2/conversions`, icon: Crosshair },
  { label: "Change Mgmt", href: `/workspace/${tenantId}/v2/changes`, icon: GitBranch },
  { label: "Connectors", href: `/workspace/${tenantId}/v2/connectors`, icon: Plug },
  { label: "Policy", href: `/workspace/${tenantId}/v2/policy`, icon: Scale },
  { label: "Billing", href: `/workspace/${tenantId}/v2/billing`, icon: CreditCard },
  { label: "Notifications", href: `/workspace/${tenantId}/v2/notifications`, icon: Bell },
  { label: "AI Quality", href: `/workspace/${tenantId}/v2/evaluation`, icon: Trophy },
];

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const tenantId = params?.tenantId as string;

  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [tenant, setTenant] = useState<TenantInfo | null>(null);

  useEffect(() => {
    if (!tenantId) return;
    checkAccess();
  }, [tenantId]);

  async function checkAccess() {
    try {
      const data = await api.get("/api/me");
      const match = (data.tenants || []).find((t: TenantInfo) => t.id === tenantId);
      if (!match) {
        setAuthorized(false);
        return;
      }
      setTenant(match);
      setAuthorized(true);

      // Ensure active tenant is set
      if (data.active_tenant_id !== tenantId) {
        const result = await api.post("/api/me/active-tenant", { tenant_id: tenantId });
        if (result.access_token) {
          api.setToken(result.access_token);
          if (typeof window !== "undefined") {
            localStorage.setItem("tenant_id", tenantId);
            localStorage.setItem("tenant_role", result.role);
          }
        }
      }
    } catch (e) {
      setAuthorized(false);
    }
  }

  if (authorized === null) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-pulse text-slate-400">Verifying access...</div>
      </div>
    );
  }

  if (authorized === false) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-4">403</div>
          <h1 className="text-xl font-bold text-slate-900 mb-2">Access Denied</h1>
          <p className="text-slate-500 mb-4">You don&apos;t have access to this workspace.</p>
          <button
            onClick={() => router.push("/tenant/select")}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Go to Workspace Selector
          </button>
        </div>
      </div>
    );
  }

  const navItems = makeNav(tenantId);
  const v2NavItems = makeV2Nav(tenantId);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-white flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <WorkspaceSwitcher />
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors mb-1",
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                )}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {item.label}
              </Link>
            );
          })}

          <div className="mt-4 mb-2 px-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">V2 Modules</div>
          </div>

          {v2NavItems.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors mb-1",
                  isActive
                    ? "bg-indigo-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                )}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-3 border-t border-slate-700">
          <button
            onClick={() => {
              api.setToken(null);
              if (typeof window !== "undefined") {
                localStorage.removeItem("tenant_id");
                localStorage.removeItem("tenant_role");
              }
              router.push("/login");
            }}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-400 hover:bg-slate-800 hover:text-white w-full transition-colors"
          >
            <LogOut className="w-5 h-5" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="pl-64">
        <div className="p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
