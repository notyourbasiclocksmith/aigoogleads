"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, Megaphone, Wand2, Palette,
  Search, Zap, FlaskConical, FileText, Settings, LogOut,
  Shield, Building2, GitBranch, Plug, Scale,
  CreditCard, Bell, Trophy, Crosshair, Brain,
  MessageSquare, Key, Image, Globe, Lightbulb, Compass, Phone,
  ChevronDown, Menu, X,
} from "lucide-react";

interface NavSection {
  title: string;
  items: { label: string; href: string; icon: any }[];
  collapsible?: boolean;
}

const navSections: NavSection[] = [
  {
    title: "",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    ],
  },
  {
    title: "AI Power",
    items: [
      { label: "Fix My Ads", href: "/operator", icon: Brain },
      { label: "Campaign Builder", href: "/ads/prompt", icon: Wand2 },
      { label: "Ad Copy Studio", href: "/creative", icon: Palette },
      { label: "Auto Optimizer", href: "/operator/live", icon: Zap },
    ],
  },
  {
    title: "Manage Ads",
    items: [
      { label: "Campaigns", href: "/ads/campaigns", icon: Megaphone },
      { label: "Ads", href: "/ads/ads", icon: Image },
      { label: "Keywords", href: "/ads/keywords", icon: Key },
      { label: "Search Terms", href: "/ads/search-terms", icon: MessageSquare },
      { label: "Landing Pages", href: "/ads/landing-pages", icon: Globe },
    ],
  },
  {
    title: "Growth AI",
    items: [
      { label: "Search Term Mining", href: "/growth/search-mining", icon: Search },
      { label: "Expand Services", href: "/growth/expand", icon: Zap },
      { label: "Bulk Campaigns", href: "/growth/bulk-generate", icon: Megaphone },
    ],
  },
  {
    title: "Intelligence",
    items: [
      { label: "Recommendations", href: "/ads/recommendations", icon: Lightbulb },
      { label: "Audit", href: "/audit", icon: Shield },
      { label: "Competitors", href: "/intel/competitors", icon: Search },
      { label: "Keyword Research", href: "/ads/keyword-research", icon: Compass },
      { label: "Reports", href: "/reports", icon: FileText },
    ],
  },
  {
    title: "Calls & Leads",
    items: [
      { label: "Calls Dashboard", href: "/calls", icon: Phone },
      { label: "LSA Leads", href: "/lsa", icon: Phone },
    ],
  },
  {
    title: "Settings",
    items: [
      { label: "Account & Sync", href: "/settings", icon: Settings },
      { label: "Billing", href: "/v2/billing", icon: CreditCard },
      { label: "Notifications", href: "/v2/notifications", icon: Bell },
    ],
  },
  {
    title: "Advanced",
    collapsible: true,
    items: [
      { label: "MCC / Agency", href: "/v2/mcc", icon: Building2 },
      { label: "Experiments", href: "/experiments", icon: FlaskConical },
      { label: "Conversions", href: "/v2/conversions", icon: Crosshair },
      { label: "Change History", href: "/v2/changes", icon: GitBranch },
      { label: "Connectors", href: "/v2/connectors", icon: Plug },
      { label: "Policy", href: "/v2/policy", icon: Scale },
      { label: "AI Quality", href: "/v2/evaluation", icon: Trophy },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const sidebarContent = (
    <>
      <div className="px-5 py-5 border-b border-white/[0.06] flex items-center justify-between">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center font-bold text-sm shadow-lg shadow-blue-500/20">
            IA
          </div>
          <div>
            <div className="font-semibold text-[15px] leading-tight tracking-tight">IgniteAds.ai</div>
            <div className="text-[11px] text-white/40 font-medium">AI CMO Platform</div>
          </div>
        </Link>
        <button onClick={() => setMobileOpen(false)} className="lg:hidden text-white/40 hover:text-white/70 p-1">
          <X className="w-5 h-5" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-3">
        {navSections.map((section) => {
          const isCollapsed = section.collapsible && !advancedOpen;
          return (
            <div key={section.title || "top"} className="mb-1">
              {section.title && (
                <div
                  className={cn(
                    "pt-4 pb-1.5 px-3 flex items-center justify-between",
                    section.collapsible && "cursor-pointer hover:opacity-80"
                  )}
                  onClick={section.collapsible ? () => setAdvancedOpen(!advancedOpen) : undefined}
                >
                  <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-white/25">
                    {section.title}
                  </div>
                  {section.collapsible && (
                    <ChevronDown className={cn(
                      "w-3 h-3 text-white/25 transition-transform duration-200",
                      advancedOpen && "rotate-180"
                    )} />
                  )}
                </div>
              )}
              {!isCollapsed && (
                <div className="space-y-0.5">
                  {section.items.map((item) => {
                    const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
                    const Icon = item.icon;
                    return (
                      <Link
                        key={item.href + item.label}
                        href={item.href}
                        onClick={() => setMobileOpen(false)}
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
                </div>
              )}
            </div>
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
    </>
  );

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(true)}
        className="lg:hidden fixed top-4 left-4 z-50 w-10 h-10 rounded-xl bg-[#0f1117] flex items-center justify-center text-white/70 hover:text-white shadow-lg"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-40 bg-black/50" onClick={() => setMobileOpen(false)} />
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 z-50 w-[260px] bg-[#0f1117] text-white flex-col">
        {sidebarContent}
      </aside>

      {/* Mobile sidebar */}
      <aside className={cn(
        "lg:hidden fixed inset-y-0 left-0 z-50 w-[280px] bg-[#0f1117] text-white flex flex-col transition-transform duration-300",
        mobileOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {sidebarContent}
      </aside>
    </>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <main className="lg:pl-[260px]">
        <div className="p-4 pt-16 lg:pt-0 lg:p-8 xl:p-10 max-w-[1440px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
