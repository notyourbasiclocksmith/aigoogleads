"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useOnboardingGuard } from "@/hooks/use-onboarding-guard";
import {
  LayoutDashboard, Megaphone, Wand2,
  Search, Zap, FlaskConical, FileText, Settings, LogOut,
  Shield, BarChart3, Building2, GitBranch, Plug, Scale,
  CreditCard, Bell, Trophy, Crosshair, Brain, Bot,
  MessageSquare, Key, Image, Globe, Phone,
  ChevronDown, Menu, X, Sparkles, Users, MapPin,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: any;
  highlight?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
  collapsible?: boolean;
  adminOnly?: boolean;
}

const coreNav: NavSection[] = [
  {
    title: "",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Get Customers", href: "/get-customers", icon: Users, highlight: true },
    ],
  },
  {
    title: "AI Intelligence",
    items: [
      { label: "AI Operator", href: "/strategist", icon: Sparkles },
      { label: "Claude Operator", href: "/ads/operator", icon: Bot },
      { label: "Fix My Ads", href: "/operator", icon: Brain },
    ],
  },
  {
    title: "Manage Ads",
    items: [
      { label: "Campaigns", href: "/ads/campaigns", icon: Megaphone },
      { label: "Creative Studio", href: "/creative", icon: Wand2 },
      { label: "Ads", href: "/ads/ads", icon: Image },
      { label: "Keywords", href: "/ads/keywords", icon: Key },
      { label: "Search Terms", href: "/ads/search-terms", icon: MessageSquare },
      { label: "Landing Pages", href: "/ads/landing-pages", icon: Globe },
    ],
  },
  {
    title: "Leads & Local",
    items: [
      { label: "Calls & Leads", href: "/calls", icon: Phone },
      { label: "GBP Manager", href: "/gbp", icon: MapPin },
    ],
  },
  {
    title: "",
    items: [
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

const advancedNav: NavSection = {
  title: "Advanced",
  collapsible: true,
  adminOnly: true,
  items: [
    { label: "Campaign Builder", href: "/ads/prompt", icon: Wand2 },
    { label: "Landing Page Studio", href: "/ads/landing-page-studio", icon: Globe },
    { label: "Search Mining", href: "/growth/search-mining", icon: Search },
    { label: "Expand Services", href: "/growth/expand", icon: Zap },
    { label: "Bulk Campaigns", href: "/growth/bulk-generate", icon: Megaphone },
    { label: "Recommendations", href: "/ads/recommendations", icon: Sparkles },
    { label: "Audit", href: "/audit", icon: Shield },
    { label: "Competitors", href: "/intel/competitors", icon: Search },
    { label: "Keyword Research", href: "/ads/keyword-research", icon: Search },
    { label: "Reports", href: "/reports", icon: FileText },
    { label: "LSA Leads", href: "/lsa", icon: Phone },
    { label: "Billing", href: "/v2/billing", icon: CreditCard },
    { label: "MCC / Agency", href: "/v2/mcc", icon: Building2 },
    { label: "Experiments", href: "/experiments", icon: FlaskConical },
    { label: "Conversions", href: "/v2/conversions", icon: Crosshair },
    { label: "Change History", href: "/v2/changes", icon: GitBranch },
    { label: "Connectors", href: "/v2/connectors", icon: Plug },
    { label: "Policy", href: "/v2/policy", icon: Scale },
    { label: "AI Quality", href: "/v2/evaluation", icon: Trophy },
  ],
};

export function Sidebar() {
  const pathname = usePathname();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    // Show advanced menu for admin/dev users
    try {
      const token = localStorage.getItem("token");
      if (token) {
        const payload = JSON.parse(atob(token.split(".")[1]));
        if (payload.role === "admin_dev" || payload.role === "owner") {
          setShowAdvanced(true);
        }
      }
    } catch {}
  }, []);

  const allSections = showAdvanced ? [...coreNav, advancedNav] : coreNav;

  function renderNavItem(item: NavItem) {
    const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
    const Icon = item.icon;

    if (item.highlight) {
      return (
        <Link
          key={item.href}
          href={item.href}
          onClick={() => setMobileOpen(false)}
          className={cn(
            "flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-semibold transition-all duration-150",
            isActive
              ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/25"
              : "bg-gradient-to-r from-blue-600/10 to-indigo-600/10 text-blue-400 hover:from-blue-600/20 hover:to-indigo-600/20 hover:text-blue-300 border border-blue-500/20"
          )}
        >
          <Icon className="w-[18px] h-[18px] flex-shrink-0" />
          {item.label}
        </Link>
      );
    }

    return (
      <Link
        key={item.href}
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
  }

  const sidebarContent = (
    <>
      <div className="px-5 py-5 border-b border-white/[0.06] flex items-center justify-between">
        <Link href="/dashboard" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center font-bold text-sm shadow-lg shadow-violet-500/20">
            IA
          </div>
          <div>
            <div className="font-semibold text-[15px] leading-tight tracking-tight">IntelliAds</div>
            <div className="text-[11px] text-white/40 font-medium">AI Marketing System</div>
          </div>
        </Link>
        <button onClick={() => setMobileOpen(false)} className="lg:hidden text-white/40 hover:text-white/70 p-1">
          <X className="w-5 h-5" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-3">
        {allSections.map((section, idx) => {
          const isCollapsed = section.collapsible && !advancedOpen;
          return (
            <div key={section.title || `section-${idx}`} className="mb-1">
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
                  {section.items.map(renderNavItem)}
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
            localStorage.removeItem("tenant_id");
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
  const { ready, loading } = useOnboardingGuard();

  if (loading || !ready) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      <Sidebar />
      <main className="lg:pl-[260px]">
        <div className="p-4 pt-16 lg:pt-0 lg:p-8 xl:p-10 max-w-[1440px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
