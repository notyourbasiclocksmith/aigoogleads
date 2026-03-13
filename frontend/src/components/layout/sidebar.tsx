"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Target, Megaphone, Wand2, Palette,
  Search, Zap, FlaskConical, FileText, Settings, LogOut,
  Shield, BarChart3, Building2, GitBranch, Plug, Scale,
  CreditCard, Bell, Trophy, Crosshair, Brain,
  MessageSquare, Key, Image, Globe, Lightbulb, Compass,
} from "lucide-react";

const navItems = [
  { label: "AI Operator", href: "/operator", icon: Brain },
  { label: "Auto Optimizer", href: "/operator/live", icon: Zap },
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Accounts", href: "/settings", icon: Target },
  { label: "Audit", href: "/audit", icon: Shield },
  { label: "Command Console", href: "/ads/prompt", icon: Wand2 },
  { label: "Campaigns", href: "/ads/campaigns", icon: Megaphone },
  { label: "Search Terms", href: "/ads/search-terms", icon: MessageSquare },
  { label: "Keywords", href: "/ads/keywords", icon: Key },
  { label: "Ads", href: "/ads/ads", icon: Image },
  { label: "Landing Pages", href: "/ads/landing-pages", icon: Globe },
  { label: "Recommendations", href: "/ads/recommendations", icon: Lightbulb },
  { label: "Keyword Research", href: "/ads/keyword-research", icon: Compass },
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
    <aside className="fixed inset-y-0 left-0 z-50 w-[260px] bg-[#0f1117] text-white flex flex-col">
      <div className="px-5 py-5 border-b border-white/[0.06]">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center font-bold text-sm shadow-lg shadow-blue-500/20">
            IA
          </div>
          <div>
            <div className="font-semibold text-[15px] leading-tight tracking-tight">IgniteAds.ai</div>
            <div className="text-[11px] text-white/40 font-medium">AI CMO Platform</div>
          </div>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-0.5">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-xl text-[13px] font-medium transition-all duration-150",
                isActive
                  ? "bg-white/[0.12] text-white shadow-sm"
                  : "text-white/50 hover:bg-white/[0.06] hover:text-white/80"
              )}
            >
              <Icon className="w-[18px] h-[18px] flex-shrink-0" />
              {item.label}
            </Link>
          );
        })}

        <div className="pt-4 pb-1 px-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-white/25">Advanced</div>
        </div>

        {v2NavItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-xl text-[13px] font-medium transition-all duration-150",
                isActive
                  ? "bg-white/[0.12] text-white shadow-sm"
                  : "text-white/50 hover:bg-white/[0.06] hover:text-white/80"
              )}
            >
              <Icon className="w-[18px] h-[18px] flex-shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-white/[0.06]">
        <button
          onClick={() => {
            localStorage.removeItem("token");
            window.location.href = "/login";
          }}
          className="flex items-center gap-3 px-3 py-2 rounded-xl text-[13px] text-white/35 hover:bg-white/[0.06] hover:text-white/70 w-full transition-all duration-150"
        >
          <LogOut className="w-[18px] h-[18px]" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <main className="pl-[260px]">
        <div className="p-8 lg:p-10 max-w-[1440px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
