"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Target, Megaphone, Wand2, Palette,
  Search, Zap, FlaskConical, FileText, Settings, LogOut,
  Shield, BarChart3, Building2, GitBranch, Plug, Scale,
  CreditCard, Bell, Trophy, Crosshair,
} from "lucide-react";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Accounts", href: "/settings", icon: Target },
  { label: "Audit", href: "/audit", icon: Shield },
  { label: "Command Console", href: "/ads/prompt", icon: Wand2 },
  { label: "Campaigns", href: "/ads/campaigns", icon: Megaphone },
  { label: "Creative Studio", href: "/creative", icon: Palette },
  { label: "Competitors", href: "/intel/competitors", icon: Search },
  { label: "Optimizations", href: "/optimizations", icon: Zap },
  { label: "Experiments", href: "/experiments", icon: FlaskConical },
  { label: "Reports", href: "/reports", icon: FileText },
  { label: "Settings", href: "/settings", icon: Settings },
];

const v2NavItems = [
  { label: "MCC / Agency", href: "/v2/mcc", icon: Building2 },
  { label: "Conversions", href: "/v2/conversions", icon: Crosshair },
  { label: "Change Mgmt", href: "/v2/changes", icon: GitBranch },
  { label: "Connectors", href: "/v2/connectors", icon: Plug },
  { label: "Policy", href: "/v2/policy", icon: Scale },
  { label: "Billing", href: "/v2/billing", icon: CreditCard },
  { label: "Notifications", href: "/v2/notifications", icon: Bell },
  { label: "AI Quality", href: "/v2/evaluation", icon: Trophy },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 text-white flex flex-col">
      <div className="p-6 border-b border-slate-700">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center font-bold text-sm">
            IA
          </div>
          <div>
            <div className="font-bold text-lg leading-tight">IgniteAds.ai</div>
            <div className="text-xs text-slate-400">AI CMO Platform</div>
          </div>
        </Link>
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
            localStorage.removeItem("token");
            window.location.href = "/login";
          }}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-400 hover:bg-slate-800 hover:text-white w-full transition-colors"
        >
          <LogOut className="w-5 h-5" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <Sidebar />
      <main className="pl-64">
        <div className="p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
