"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
  CheckCircle2, ArrowRight, ArrowLeft, Building2, Globe, Link2,
  Target, Settings2, Sparkles, Phone, MapPin, FileText, Facebook,
  Instagram, Music2, Map, DollarSign, PhoneCall, ClipboardList,
  CalendarCheck, ShoppingCart, Shield, Zap, Brain, Loader2, Rocket,
  ExternalLink,
} from "lucide-react";

const steps = [
  { label: "Business Info", subtitle: "Tell us about your business", icon: Building2, color: "from-blue-500 to-indigo-600" },
  { label: "Online Presence", subtitle: "Connect your digital footprint", icon: Globe, color: "from-emerald-500 to-teal-600" },
  { label: "Google Ads", subtitle: "Link your ad account", icon: Link2, color: "from-orange-500 to-amber-600" },
  { label: "Goals & Budget", subtitle: "Define your targets", icon: Target, color: "from-purple-500 to-violet-600" },
  { label: "AI Preferences", subtitle: "Set your automation level", icon: Settings2, color: "from-pink-500 to-rose-600" },
];

const industries = [
  { value: "locksmith", label: "Locksmith", emoji: "🔑" },
  { value: "roofing", label: "Roofing", emoji: "🏠" },
  { value: "hvac", label: "HVAC", emoji: "❄️" },
  { value: "plumbing", label: "Plumbing", emoji: "🔧" },
  { value: "auto_repair", label: "Auto Repair", emoji: "🚗" },
  { value: "electrical", label: "Electrical", emoji: "⚡" },
  { value: "pest_control", label: "Pest Control", emoji: "🐛" },
  { value: "landscaping", label: "Landscaping", emoji: "🌿" },
  { value: "cleaning", label: "Cleaning", emoji: "✨" },
  { value: "dental", label: "Dental", emoji: "🦷" },
  { value: "legal", label: "Legal Services", emoji: "⚖️" },
  { value: "real_estate", label: "Real Estate", emoji: "🏡" },
  { value: "other", label: "Other", emoji: "📦" },
];

const conversionGoals = [
  { value: "calls", label: "Phone Calls", desc: "Drive inbound calls from potential customers", icon: PhoneCall },
  { value: "forms", label: "Form Submissions", desc: "Generate leads through contact forms", icon: ClipboardList },
  { value: "bookings", label: "Online Bookings", desc: "Get appointments booked directly", icon: CalendarCheck },
  { value: "purchases", label: "Purchases", desc: "Drive direct product or service sales", icon: ShoppingCart },
];

const autonomyModes = [
  {
    mode: "suggest", title: "Co-Pilot", icon: Shield,
    desc: "AI analyzes and recommends changes. You review and approve every optimization before it goes live.",
    features: ["Full visibility into every change", "One-click approval workflow", "Learn as AI explains its reasoning"],
    gradient: "from-blue-500/10 to-indigo-500/10",
    border: "border-slate-700 hover:border-blue-500/50",
    activeBorder: "border-blue-500 bg-gradient-to-br from-blue-500/10 to-indigo-500/10",
    badge: "Conservative",
  },
  {
    mode: "semi_auto", title: "Autopilot Lite", icon: Zap,
    desc: "AI handles routine optimizations automatically. You approve strategic and high-impact changes.",
    features: ["Auto-applies bid adjustments & negatives", "Alerts for budget & strategy changes", "Perfect balance of speed & control"],
    gradient: "from-purple-500/10 to-violet-500/10",
    border: "border-slate-700 hover:border-purple-500/50",
    activeBorder: "border-purple-500 bg-gradient-to-br from-purple-500/10 to-violet-500/10",
    badge: "Recommended",
  },
  {
    mode: "full_auto", title: "Full Autopilot", icon: Brain,
    desc: "AI manages your campaigns end-to-end. Maximum performance with minimal oversight required.",
    features: ["Fully autonomous campaign management", "Real-time optimization 24/7", "Weekly performance summaries"],
    gradient: "from-rose-500/10 to-pink-500/10",
    border: "border-slate-700 hover:border-rose-500/50",
    activeBorder: "border-rose-500 bg-gradient-to-br from-rose-500/10 to-pink-500/10",
    badge: "Aggressive",
  },
];

function OnboardingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [googleAdsConnected, setGoogleAdsConnected] = useState(false);
  const [onboardingComplete, setOnboardingComplete] = useState(false);

  const [tenantName, setTenantName] = useState("");
  const [industry, setIndustry] = useState("");
  const [phone, setPhone] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [description, setDescription] = useState("");
  const [facebookUrl, setFacebookUrl] = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [tiktokUrl, setTiktokUrl] = useState("");
  const [gbpLink, setGbpLink] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("1000");
  const [conversionGoal, setConversionGoal] = useState("calls");
  const [autonomyMode, setAutonomyMode] = useState("semi_auto");
  const [serviceArea, setServiceArea] = useState("");

  // Google Ads account picker state
  const [accessibleCustomers, setAccessibleCustomers] = useState<any[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const [accountSelected, setAccountSelected] = useState(false);
  const [selectingAccount, setSelectingAccount] = useState(false);
  const [manualCustomerId, setManualCustomerId] = useState("");

  useEffect(() => {
    if (searchParams.get("oauth_success") === "true") {
      setStep(2);
      setGoogleAdsConnected(true);
      // Fetch accessible customers so user can pick one
      loadAccessibleCustomers();
    } else if (searchParams.get("oauth_error")) {
      setStep(2);
      setError(`Google Ads connection failed: ${searchParams.get("oauth_error")}`);
    }
  }, [searchParams]);

  async function loadAccessibleCustomers() {
    setLoadingCustomers(true);
    try {
      const customers = await api.get("/api/ads/accounts/accessible-customers");
      setAccessibleCustomers(Array.isArray(customers) ? customers : []);
    } catch (e: any) {
      console.error("Failed to load accessible customers", e);
      setAccessibleCustomers([]);
    }
    setLoadingCustomers(false);
  }

  async function handleSelectAccount() {
    if (!selectedCustomerId) return;
    setSelectingAccount(true);
    setError("");
    try {
      // Get the pending account ID
      const accounts = await api.get("/api/ads/accounts");
      const pending = accounts.find((a: any) => a.customer_id === "pending");
      if (!pending) {
        setError("No pending account found. Please reconnect Google Ads.");
        setSelectingAccount(false);
        return;
      }
      const selected = accessibleCustomers.find((c: any) => c.customer_id === selectedCustomerId);
      await api.post(`/api/ads/accounts/${pending.id}/select-customer`, {
        customer_id: selectedCustomerId,
        account_name: selected?.name || `Account ${selectedCustomerId}`,
      });
      setAccountSelected(true);
    } catch (e: any) {
      setError(e.message || "Failed to select account");
    }
    setSelectingAccount(false);
  }

  // Check if onboarding is already complete — redirect to dashboard
  // Also pre-populate fields from saved data if still in progress
  useEffect(() => {
    api.get("/api/onboarding/status").then((status: any) => {
      if (status?.complete) {
        router.push("/dashboard");
        return;
      }
      // Not complete — fetch saved data to pre-populate fields
      api.get("/api/onboarding/data").then((data: any) => {
        if (!data) return;
        if (data.business_name) setTenantName(data.business_name);
        if (data.industry) setIndustry(data.industry);
        if (data.phone) setPhone(data.phone);
        if (data.website_url) setWebsiteUrl(data.website_url);
        if (data.description) setDescription(data.description);
        if (data.facebook_url) setFacebookUrl(data.facebook_url);
        if (data.instagram_url) setInstagramUrl(data.instagram_url);
        if (data.tiktok_url) setTiktokUrl(data.tiktok_url);
        if (data.gbp_link) setGbpLink(data.gbp_link);
        if (data.monthly_budget) setMonthlyBudget(String(data.monthly_budget));
        if (data.conversion_goal) setConversionGoal(data.conversion_goal);
        if (data.autonomy_mode) setAutonomyMode(data.autonomy_mode);
        if (data.google_ads_connected) setGoogleAdsConnected(true);
        if (data.service_area) setServiceArea(data.service_area);
      }).catch(() => {});
    }).catch(() => {});
  }, [router]);

  async function handleNext() {
    setError("");
    setLoading(true);
    try {
      if (step === 0) {
        if (!tenantName.trim()) { setError("Please enter your business name"); setLoading(false); return; }
        if (!industry) { setError("Please select an industry"); setLoading(false); return; }
        const res = await api.post("/api/onboarding/step1", {
          tenant_name: tenantName,
          industry,
          phone,
          service_area: serviceArea ? { primary: serviceArea } : undefined,
        });
        if (res.access_token) api.setToken(res.access_token);
      } else if (step === 1) {
        await api.post("/api/onboarding/step2", {
          website_url: websiteUrl, description,
          social_links: { facebook: facebookUrl, instagram: instagramUrl, tiktok: tiktokUrl },
          gbp_link: gbpLink,
        });
      } else if (step === 2) {
        // Google Ads connection is optional — skip or already connected
      } else if (step === 3) {
        await api.post("/api/onboarding/step4", {
          monthly_budget: parseInt(monthlyBudget) || 1000,
          conversion_goal: conversionGoal,
        });
      } else if (step === 4) {
        await api.post("/api/onboarding/step5", { autonomy_mode: autonomyMode });
        setOnboardingComplete(true);
        setTimeout(() => router.push("/dashboard"), 2500);
        return;
      }
      setStep(step + 1);
    } catch (err: any) {
      setError(err.message || "Failed to save step");
    } finally {
      setLoading(false);
    }
  }

  const progress = ((step + 1) / steps.length) * 100;

  if (onboardingComplete) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center space-y-6 animate-in fade-in duration-500">
          <div className="w-24 h-24 mx-auto rounded-3xl bg-gradient-to-br from-emerald-500/20 to-teal-500/20 border border-emerald-500/30 flex items-center justify-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-3xl font-bold text-white mb-2">You&apos;re All Set!</h2>
            <p className="text-slate-400 max-w-md mx-auto">
              Your AI marketing assistant is ready. Redirecting to your dashboard...
            </p>
          </div>
          <div className="flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
            <span className="text-sm text-slate-500">Setting up your workspace</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex">
      {/* Left Sidebar */}
      <div className="hidden lg:flex lg:w-[380px] xl:w-[420px] flex-col bg-gradient-to-b from-slate-900 to-slate-950 border-r border-slate-800/50 p-8 relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute top-0 left-0 w-full h-full">
          <div className="absolute top-20 -left-20 w-72 h-72 bg-blue-500/10 rounded-full blur-3xl" />
          <div className="absolute bottom-20 -right-20 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl" />
        </div>

        <div className="relative z-10 flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">IgniteAds.ai</h1>
              <p className="text-xs text-slate-400">Intelligent Ad Management</p>
            </div>
          </div>

          {/* Steps */}
          <div className="space-y-1 flex-1">
            {steps.map((s, i) => {
              const Icon = s.icon;
              const isActive = i === step;
              const isComplete = i < step;
              return (
                <div key={i} className="flex items-start gap-4 relative">
                  {/* Connector line */}
                  {i < steps.length - 1 && (
                    <div className={`absolute left-[19px] top-[44px] w-[2px] h-[40px] transition-colors duration-500 ${
                      isComplete ? "bg-emerald-500" : "bg-slate-700"
                    }`} />
                  )}
                  <div className={`relative z-10 w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-all duration-500 ${
                    isComplete
                      ? "bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30"
                      : isActive
                      ? `bg-gradient-to-br ${s.color} text-white shadow-lg shadow-blue-500/20`
                      : "bg-slate-800/50 text-slate-500 ring-1 ring-slate-700/50"
                  }`}>
                    {isComplete ? <CheckCircle2 className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                  </div>
                  <div className={`pt-1.5 pb-6 transition-opacity duration-300 ${isActive ? "opacity-100" : "opacity-60"}`}>
                    <p className={`text-sm font-semibold ${isActive ? "text-white" : isComplete ? "text-emerald-400" : "text-slate-400"}`}>
                      {s.label}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">{s.subtitle}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Progress */}
          <div className="mt-auto pt-8 border-t border-slate-800/50">
            <div className="flex justify-between text-xs text-slate-400 mb-2">
              <span>Progress</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-h-screen">
        {/* Mobile top bar */}
        <div className="lg:hidden flex items-center justify-between p-4 border-b border-slate-800/50">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-bold text-white">IgniteAds.ai</span>
          </div>
          <span className="text-xs text-slate-400">Step {step + 1}/{steps.length}</span>
        </div>

        {/* Mobile progress bar */}
        <div className="lg:hidden h-1 bg-slate-800">
          <div className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-700" style={{ width: `${progress}%` }} />
        </div>

        {/* Content area */}
        <div className="flex-1 flex items-center justify-center p-4 sm:p-6 lg:p-12">
          <div className="w-full max-w-2xl">
            {/* Step header */}
            <div className="mb-8">
              <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gradient-to-r ${steps[step].color} bg-opacity-10 mb-4`}>
                <span className="text-xs font-medium text-white/90">Step {step + 1} of {steps.length}</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-bold text-white mb-2">{steps[step].label}</h2>
              <p className="text-slate-400">{steps[step].subtitle}</p>
            </div>

            {/* Step content */}
            <div className="space-y-5">
              {/* ═══════ STEP 1: Business Info ═══════ */}
              {step === 0 && (
                <div className="space-y-5">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-blue-400" /> Business Name
                    </label>
                    <Input
                      value={tenantName} onChange={(e) => setTenantName(e.target.value)}
                      placeholder="e.g. Ace Locksmith Dallas"
                      className="h-12 bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20 rounded-xl"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-blue-400" /> Industry
                    </label>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {industries.map((ind) => (
                        <button
                          key={ind.value}
                          onClick={() => setIndustry(ind.value)}
                          className={`flex items-center gap-2 p-3 rounded-xl border text-sm font-medium transition-all duration-200 ${
                            industry === ind.value
                              ? "border-blue-500 bg-blue-500/10 text-blue-300 ring-1 ring-blue-500/30"
                              : "border-slate-700/50 bg-slate-800/30 text-slate-400 hover:border-slate-600 hover:bg-slate-800/50"
                          }`}
                        >
                          <span className="text-lg">{ind.emoji}</span>
                          <span className="truncate">{ind.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <Phone className="w-4 h-4 text-blue-400" /> Phone Number
                    </label>
                    <Input
                      value={phone} onChange={(e) => setPhone(e.target.value)}
                      placeholder="(214) 555-0123"
                      className="h-12 bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20 rounded-xl"
                    />
                    <p className="text-xs text-slate-500">Used for call tracking and ad extensions</p>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-blue-400" /> Service Area
                    </label>
                    <Input
                      value={serviceArea} onChange={(e) => setServiceArea(e.target.value)}
                      placeholder="e.g. Dallas, TX or Dallas-Fort Worth metro"
                      className="h-12 bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20 rounded-xl"
                    />
                    <p className="text-xs text-slate-500">Where your business operates — used for geo-targeting your ads</p>
                  </div>
                </div>
              )}

              {/* ═══════ STEP 2: Online Presence ═══════ */}
              {step === 1 && (
                <div className="space-y-5">
                  <div className="p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                    <p className="text-sm text-emerald-300 flex items-center gap-2">
                      <Sparkles className="w-4 h-4" />
                      Our AI will analyze your online presence to generate optimized ad campaigns.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <Globe className="w-4 h-4 text-emerald-400" /> Website URL
                    </label>
                    <Input
                      value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)}
                      placeholder="https://www.yourbusiness.com"
                      className="h-12 bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-emerald-500 focus:ring-emerald-500/20 rounded-xl"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-emerald-400" /> Business Description
                    </label>
                    <textarea
                      value={description} onChange={(e) => setDescription(e.target.value)}
                      placeholder="Tell us about your services, specialties, and what makes your business unique..."
                      rows={3}
                      className="flex w-full rounded-xl border border-slate-700 bg-slate-800/50 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 focus:outline-none resize-none"
                    />
                  </div>

                  <div className="space-y-3">
                    <label className="text-sm font-medium text-slate-300">Social Media Profiles</label>
                    <div className="space-y-3">
                      {[
                        { icon: Facebook, label: "Facebook", value: facebookUrl, setter: setFacebookUrl, placeholder: "https://facebook.com/yourbiz", color: "text-blue-400" },
                        { icon: Instagram, label: "Instagram", value: instagramUrl, setter: setInstagramUrl, placeholder: "https://instagram.com/yourbiz", color: "text-pink-400" },
                        { icon: Music2, label: "TikTok", value: tiktokUrl, setter: setTiktokUrl, placeholder: "https://tiktok.com/@yourbiz", color: "text-slate-300" },
                        { icon: Map, label: "Google Business Profile", value: gbpLink, setter: setGbpLink, placeholder: "https://g.page/yourbiz", color: "text-amber-400" },
                      ].map(({ icon: SIcon, label, value, setter, placeholder, color }) => (
                        <div key={label} className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-slate-800/80 border border-slate-700/50 flex items-center justify-center flex-shrink-0">
                            <SIcon className={`w-5 h-5 ${color}`} />
                          </div>
                          <Input
                            value={value} onChange={(e) => setter(e.target.value)}
                            placeholder={placeholder}
                            className="h-11 bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-emerald-500 focus:ring-emerald-500/20 rounded-xl flex-1"
                          />
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-slate-500">Add any profiles you have — we&apos;ll extract insights to supercharge your ads.</p>
                  </div>
                </div>
              )}

              {/* ═══════ STEP 3: Google Ads ═══════ */}
              {step === 2 && (
                <div className="space-y-6">
                  <div className="relative rounded-2xl border border-slate-700/50 bg-gradient-to-b from-slate-800/50 to-slate-900/50 p-8 text-center overflow-hidden">
                    {/* Background decoration */}
                    <div className="absolute inset-0 bg-gradient-to-br from-orange-500/5 to-amber-500/5" />
                    <div className="absolute top-0 right-0 w-32 h-32 bg-orange-500/10 rounded-full blur-3xl" />

                    <div className="relative z-10">
                      {googleAdsConnected && accountSelected ? (
                        /* ── Account fully linked ── */
                        <>
                          <div className="w-20 h-20 mx-auto rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mb-5">
                            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
                          </div>
                          <h3 className="text-xl font-bold text-white mb-2">Google Ads Connected</h3>
                          <p className="text-slate-400 max-w-sm mx-auto mb-4">
                            Your account is linked and syncing. We&apos;ll start analyzing your campaigns.
                          </p>
                          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-medium">
                            <CheckCircle2 className="w-4 h-4" /> Account verified &amp; syncing
                          </div>
                        </>
                      ) : googleAdsConnected ? (
                        /* ── OAuth done, need to pick account ── */
                        <>
                          <div className="w-20 h-20 mx-auto rounded-2xl bg-orange-500/10 border border-orange-500/30 flex items-center justify-center mb-5">
                            <svg className="w-10 h-10" viewBox="0 0 24 24" fill="none">
                              <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#FBBC05" />
                              <path d="M2 17l10 5 10-5" stroke="#4285F4" strokeWidth="2" />
                              <path d="M2 12l10 5 10-5" stroke="#34A853" strokeWidth="2" />
                            </svg>
                          </div>
                          <h3 className="text-xl font-bold text-white mb-2">Select Your Google Ads Account</h3>
                          <p className="text-slate-400 max-w-sm mx-auto mb-6">
                            Google connected successfully! Now choose which account to manage.
                          </p>

                          {loadingCustomers ? (
                            <div className="flex items-center justify-center gap-2 py-6">
                              <Loader2 className="w-5 h-5 text-orange-400 animate-spin" />
                              <span className="text-sm text-slate-400">Loading your accounts...</span>
                            </div>
                          ) : accessibleCustomers.length === 0 ? (
                            <div className="py-4 space-y-4">
                              <p className="text-sm text-slate-400">Could not auto-detect accounts. Enter your Google Ads Customer ID manually.</p>
                              <p className="text-xs text-slate-500">Find it at the top of your Google Ads dashboard (e.g. 123-456-7890)</p>
                              <div className="flex gap-2 max-w-md mx-auto">
                                <input
                                  type="text"
                                  placeholder="e.g. 894-688-3394"
                                  value={manualCustomerId}
                                  onChange={(e) => setManualCustomerId(e.target.value)}
                                  className="flex-1 px-4 py-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 text-white placeholder:text-slate-500 text-sm focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/30"
                                />
                                <Button
                                  disabled={!manualCustomerId.replace(/[-\s]/g, '').match(/^\d{7,10}$/) || selectingAccount}
                                  onClick={async () => {
                                    setSelectingAccount(true);
                                    setError("");
                                    try {
                                      const accounts = await api.get("/api/ads/accounts");
                                      const pending = accounts.find((a: any) => a.customer_id === "pending");
                                      if (!pending) { setError("No pending account found."); setSelectingAccount(false); return; }
                                      await api.post(`/api/ads/accounts/${pending.id}/select-customer`, {
                                        customer_id: manualCustomerId.replace(/[-\s]/g, ''),
                                        account_name: `Account ${manualCustomerId}`,
                                      });
                                      setAccountSelected(true);
                                    } catch (e: any) {
                                      setError(e.message || "Failed to connect account");
                                    }
                                    setSelectingAccount(false);
                                  }}
                                  className="bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 text-white font-semibold rounded-xl"
                                >
                                  {selectingAccount ? <Loader2 className="w-4 h-4 animate-spin" /> : "Connect"}
                                </Button>
                              </div>
                              <div className="pt-2">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={async () => {
                                    try {
                                      const res = await api.post("/api/onboarding/step3/google-ads-url");
                                      if (res.oauth_url) window.location.href = res.oauth_url;
                                    } catch {
                                      setError("Google Ads connection not available.");
                                    }
                                  }}
                                  className="text-slate-400 hover:text-white text-xs"
                                >
                                  Or reconnect Google Ads
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="text-left space-y-3 max-w-md mx-auto">
                              {accessibleCustomers.map((c: any) => (
                                <button
                                  key={c.customer_id}
                                  onClick={() => setSelectedCustomerId(c.customer_id)}
                                  className={`w-full flex items-center gap-3 p-4 rounded-xl border text-left transition-all duration-200 ${
                                    selectedCustomerId === c.customer_id
                                      ? "border-orange-500 bg-orange-500/10 ring-1 ring-orange-500/30"
                                      : "border-slate-700/50 bg-slate-800/30 hover:border-slate-600"
                                  }`}
                                >
                                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                                    selectedCustomerId === c.customer_id ? "bg-orange-500/20" : "bg-slate-800"
                                  }`}>
                                    <Target className={`w-5 h-5 ${
                                      selectedCustomerId === c.customer_id ? "text-orange-400" : "text-slate-400"
                                    }`} />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <p className={`text-sm font-semibold truncate ${
                                      selectedCustomerId === c.customer_id ? "text-orange-300" : "text-slate-300"
                                    }`}>{c.name}</p>
                                    <p className="text-xs text-slate-500 mt-0.5">
                                      ID: {c.customer_id.replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3")}
                                      {c.currency ? ` · ${c.currency}` : ""}
                                      {c.is_manager ? " · Manager Account" : ""}
                                    </p>
                                  </div>
                                  <div className={`w-5 h-5 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-colors ${
                                    selectedCustomerId === c.customer_id
                                      ? "border-orange-500 bg-orange-500"
                                      : "border-slate-600"
                                  }`}>
                                    {selectedCustomerId === c.customer_id && <div className="w-2 h-2 rounded-full bg-white" />}
                                  </div>
                                </button>
                              ))}
                              <Button
                                onClick={handleSelectAccount}
                                disabled={!selectedCustomerId || selectingAccount}
                                className="w-full h-11 mt-4 bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 text-white font-semibold rounded-xl shadow-lg shadow-orange-500/20 transition-all duration-200 disabled:opacity-50"
                              >
                                {selectingAccount ? (
                                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Connecting...</>
                                ) : (
                                  <>Link Selected Account <ArrowRight className="w-4 h-4 ml-2" /></>
                                )}
                              </Button>
                            </div>
                          )}
                        </>
                      ) : (
                        /* ── Not connected yet ── */
                        <>
                          <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-orange-500/20 to-amber-500/20 border border-orange-500/30 flex items-center justify-center mb-5">
                            <svg className="w-10 h-10" viewBox="0 0 24 24" fill="none">
                              <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#FBBC05" />
                              <path d="M2 17l10 5 10-5" stroke="#4285F4" strokeWidth="2" />
                              <path d="M2 12l10 5 10-5" stroke="#34A853" strokeWidth="2" />
                            </svg>
                          </div>
                          <h3 className="text-xl font-bold text-white mb-2">Connect Google Ads</h3>
                          <p className="text-slate-400 max-w-sm mx-auto mb-6">
                            Link your Google Ads account to unlock AI-powered campaign management, real-time optimization, and performance insights.
                          </p>
                          <div className="flex flex-col items-center gap-3">
                            <Button
                              size="lg"
                              onClick={async () => {
                                try {
                                  const res = await api.post("/api/onboarding/step3/google-ads-url");
                                  if (res.oauth_url) window.location.href = res.oauth_url;
                                } catch {
                                  setError("Google Ads connection not available. You can connect later from Settings.");
                                }
                              }}
                              className="h-12 px-8 bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 text-white font-semibold rounded-xl shadow-lg shadow-orange-500/20 transition-all duration-200"
                            >
                              <ExternalLink className="w-4 h-4 mr-2" />
                              Connect Google Ads Account
                            </Button>
                            <p className="text-xs text-slate-500">You can also connect later from Settings</p>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Benefits */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {[
                      { title: "Smart Bidding", desc: "AI-optimized bids in real-time", icon: Zap },
                      { title: "Auto-Optimization", desc: "Continuous campaign improvement", icon: Brain },
                      { title: "Performance Insights", desc: "Detailed analytics & reports", icon: Target },
                    ].map(({ title, desc, icon: BIcon }) => (
                      <div key={title} className="p-4 rounded-xl bg-slate-800/30 border border-slate-700/30">
                        <BIcon className="w-5 h-5 text-orange-400 mb-2" />
                        <p className="text-sm font-medium text-white">{title}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ═══════ STEP 4: Goals & Budget ═══════ */}
              {step === 3 && (
                <div className="space-y-6">
                  <div className="space-y-3">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <DollarSign className="w-4 h-4 text-purple-400" /> Monthly Ad Budget
                    </label>
                    <div className="relative">
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-lg font-semibold">$</span>
                      <Input
                        type="number" value={monthlyBudget}
                        onChange={(e) => setMonthlyBudget(e.target.value)}
                        placeholder="1000"
                        className="h-14 pl-10 text-xl font-semibold bg-slate-800/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-purple-500 focus:ring-purple-500/20 rounded-xl"
                      />
                    </div>
                    <div className="flex gap-2">
                      {["500", "1000", "2500", "5000"].map((amt) => (
                        <button
                          key={amt}
                          onClick={() => setMonthlyBudget(amt)}
                          className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                            monthlyBudget === amt
                              ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                              : "bg-slate-800/50 text-slate-400 border border-slate-700/50 hover:border-slate-600"
                          }`}
                        >
                          ${parseInt(amt).toLocaleString()}
                        </button>
                      ))}
                    </div>
                    <p className="text-xs text-slate-500">
                      That&apos;s approximately <span className="text-purple-400 font-medium">${Math.round((parseInt(monthlyBudget) || 0) / 30)}/day</span> across your campaigns
                    </p>
                  </div>

                  <div className="space-y-3">
                    <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                      <Target className="w-4 h-4 text-purple-400" /> Primary Conversion Goal
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {conversionGoals.map(({ value, label, desc, icon: GIcon }) => (
                        <button
                          key={value}
                          onClick={() => setConversionGoal(value)}
                          className={`flex items-start gap-3 p-4 rounded-xl border text-left transition-all duration-200 ${
                            conversionGoal === value
                              ? "border-purple-500 bg-purple-500/10 ring-1 ring-purple-500/30"
                              : "border-slate-700/50 bg-slate-800/30 hover:border-slate-600"
                          }`}
                        >
                          <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                            conversionGoal === value ? "bg-purple-500/20 text-purple-400" : "bg-slate-800 text-slate-400"
                          }`}>
                            <GIcon className="w-5 h-5" />
                          </div>
                          <div>
                            <p className={`text-sm font-semibold ${conversionGoal === value ? "text-purple-300" : "text-slate-300"}`}>{label}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* ═══════ STEP 5: AI Preferences ═══════ */}
              {step === 4 && (
                <div className="space-y-5">
                  <div className="p-4 rounded-xl bg-pink-500/5 border border-pink-500/20">
                    <p className="text-sm text-pink-300 flex items-center gap-2">
                      <Brain className="w-4 h-4" />
                      Choose how much control IgniteAds.ai has over your campaigns. You can change this anytime.
                    </p>
                  </div>

                  <div className="space-y-3">
                    {autonomyModes.map((opt) => {
                      const AIcon = opt.icon;
                      const isSelected = autonomyMode === opt.mode;
                      return (
                        <button
                          key={opt.mode}
                          onClick={() => setAutonomyMode(opt.mode)}
                          className={`w-full text-left p-5 rounded-2xl border-2 transition-all duration-300 ${
                            isSelected ? opt.activeBorder : opt.border + " bg-slate-800/20"
                          }`}
                        >
                          <div className="flex items-start gap-4">
                            <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors ${
                              isSelected ? `bg-gradient-to-br ${opt.gradient}` : "bg-slate-800"
                            }`}>
                              <AIcon className={`w-6 h-6 ${isSelected ? "text-white" : "text-slate-400"}`} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <p className={`text-base font-bold ${isSelected ? "text-white" : "text-slate-300"}`}>{opt.title}</p>
                                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                  opt.mode === "semi_auto"
                                    ? "bg-purple-500/20 text-purple-300"
                                    : opt.mode === "full_auto"
                                    ? "bg-rose-500/20 text-rose-300"
                                    : "bg-blue-500/20 text-blue-300"
                                }`}>{opt.badge}</span>
                              </div>
                              <p className="text-sm text-slate-400 mb-3">{opt.desc}</p>
                              <div className="flex flex-wrap gap-x-4 gap-y-1">
                                {opt.features.map((f) => (
                                  <span key={f} className="text-xs text-slate-500 flex items-center gap-1">
                                    <CheckCircle2 className={`w-3 h-3 ${isSelected ? "text-emerald-400" : "text-slate-600"}`} />
                                    {f}
                                  </span>
                                ))}
                              </div>
                            </div>
                            {/* Radio indicator */}
                            <div className={`w-5 h-5 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-colors ${
                              isSelected
                                ? opt.mode === "suggest" ? "border-blue-500 bg-blue-500"
                                : opt.mode === "semi_auto" ? "border-purple-500 bg-purple-500"
                                : "border-rose-500 bg-rose-500"
                              : "border-slate-600"
                            }`}>
                              {isSelected && <div className="w-2 h-2 rounded-full bg-white" />}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Error message */}
            {error && (
              <div className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Navigation */}
            <div className="flex items-center justify-between mt-8 pt-6 border-t border-slate-800/50">
              <Button
                variant="ghost"
                onClick={() => { setError(""); setStep(Math.max(0, step - 1)); }}
                disabled={step === 0}
                className="text-slate-400 hover:text-white hover:bg-slate-800/50 rounded-xl h-11 px-5"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
              <Button
                onClick={handleNext}
                disabled={loading}
                className={`h-11 px-8 rounded-xl font-semibold shadow-lg transition-all duration-200 ${
                  step === 4
                    ? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 shadow-emerald-500/20"
                    : "bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 shadow-blue-500/20"
                } text-white`}
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</>
                ) : step === 4 ? (
                  <><Rocket className="w-4 h-4 mr-2" /> Launch Dashboard</>
                ) : step === 2 && !googleAdsConnected ? (
                  <>Skip for Now <ArrowRight className="w-4 h-4 ml-2" /></>
                ) : (
                  <>Continue <ArrowRight className="w-4 h-4 ml-2" /></>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    }>
      <OnboardingContent />
    </Suspense>
  );
}
