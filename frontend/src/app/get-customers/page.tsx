"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AppLayout } from "@/components/layout/sidebar";
import {
  Users, MapPin, DollarSign, Target, Rocket, Loader2, CheckCircle2,
  AlertCircle, ArrowRight, ArrowLeft, Sparkles, Phone, Globe,
  TrendingUp, Zap, Shield, ChevronRight,
} from "lucide-react";

type Step = 1 | 2 | 3 | 4 | 5;

interface BuildProgress {
  step: string;
  status: "running" | "done";
  detail: string;
  elapsed_ms?: number;
}

interface BuildResult {
  success: boolean;
  campaign_id: string;
  campaign_name: string;
  campaign_type: string;
  budget_daily: number;
  ad_groups: number;
  keywords: number;
  ads: number;
  compliance?: { score?: number; grade?: string };
  reasoning?: Record<string, string>;
}

const BUSINESS_TYPES = [
  { label: "Locksmith", value: "locksmith", icon: "🔑" },
  { label: "Roofer", value: "roofer", icon: "🏠" },
  { label: "Plumber", value: "plumber", icon: "🔧" },
  { label: "Electrician", value: "electrician", icon: "⚡" },
  { label: "HVAC", value: "hvac", icon: "❄️" },
  { label: "Pest Control", value: "pest_control", icon: "🐛" },
  { label: "Garage Door", value: "garage_door", icon: "🚪" },
  { label: "Landscaping", value: "landscaping", icon: "🌿" },
  { label: "Auto Repair", value: "auto_repair", icon: "🚗" },
  { label: "Cleaning Service", value: "cleaning", icon: "✨" },
  { label: "Moving Company", value: "moving", icon: "📦" },
  { label: "Other", value: "other", icon: "💼" },
];

const BUDGET_OPTIONS = [
  { label: "$500/mo", value: 500, desc: "Starter — test the waters" },
  { label: "$1,000/mo", value: 1000, desc: "Growth — steady lead flow" },
  { label: "$1,500/mo", value: 1500, desc: "Recommended — best value" },
  { label: "$2,500/mo", value: 2500, desc: "Aggressive — dominate locally" },
  { label: "$5,000/mo", value: 5000, desc: "Scale — maximize coverage" },
  { label: "Custom", value: 0, desc: "Set your own budget" },
];

const GOAL_OPTIONS = [
  { label: "Phone Calls", value: "calls", icon: Phone, desc: "Get calls from ready-to-buy customers" },
  { label: "Website Leads", value: "leads", icon: Globe, desc: "Drive form fills and bookings" },
  { label: "Both", value: "calls_and_leads", icon: TrendingUp, desc: "Maximize all lead types" },
];

export default function GetCustomersPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);

  // Form state
  const [businessType, setBusinessType] = useState("");
  const [customType, setCustomType] = useState("");
  const [location, setLocation] = useState("");
  const [budgetMonthly, setBudgetMonthly] = useState(1500);
  const [customBudget, setCustomBudget] = useState("");
  const [goal, setGoal] = useState("calls_and_leads");

  // Build state
  const [building, setBuilding] = useState(false);
  const [progress, setProgress] = useState<BuildProgress[]>([]);
  const [result, setResult] = useState<BuildResult | null>(null);
  const [error, setError] = useState("");

  const progressRef = useRef<HTMLDivElement>(null);

  const effectiveType = businessType === "other" ? customType : businessType;
  const effectiveBudget = budgetMonthly === 0 ? parseInt(customBudget) || 0 : budgetMonthly;

  function canProceed(): boolean {
    switch (step) {
      case 1: return !!effectiveType;
      case 2: return location.trim().length >= 3;
      case 3: return effectiveBudget >= 100;
      case 4: return !!goal;
      default: return true;
    }
  }

  function nextStep() {
    if (step < 5 && canProceed()) setStep((step + 1) as Step);
  }

  function prevStep() {
    if (step > 1) setStep((step - 1) as Step);
  }

  async function handleBuild() {
    setBuilding(true);
    setProgress([]);
    setError("");
    setResult(null);
    setStep(5);

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`/api/v2/strategist/auto-build/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          business_type: effectiveType,
          location: location.trim(),
          budget_monthly: effectiveBudget,
          goal,
          urgency: "high",
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(errData?.detail || `Build failed (${response.status})`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error("No response stream");

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "step") {
              setProgress((prev) => {
                const existing = prev.findIndex((p) => p.step === event.step);
                if (existing >= 0) {
                  const updated = [...prev];
                  updated[existing] = { ...updated[existing], ...event };
                  return updated;
                }
                return [...prev, event];
              });
            } else if (event.type === "complete") {
              setResult(event.data);
            } else if (event.type === "error") {
              setError(event.message);
            }
          } catch {}
        }
      }
    } catch (e: any) {
      setError(e.message || "Campaign build failed");
    }
    setBuilding(false);
  }

  // Auto-scroll progress
  useEffect(() => {
    if (progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight;
    }
  }, [progress]);

  return (
    <AppLayout>
      <div className="max-w-2xl mx-auto py-4">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-semibold mb-4">
            <Sparkles className="w-3 h-3" /> AI-Powered Campaign Builder
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">Get Customers</h1>
          <p className="text-white/50">
            Tell us about your business and we'll build a full Google Ads campaign in under 60 seconds.
          </p>
        </div>

        {/* Progress bar */}
        {step < 5 && (
          <div className="flex items-center gap-2 mb-8">
            {[1, 2, 3, 4].map((s) => (
              <div key={s} className="flex-1 flex items-center gap-2">
                <div
                  className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
                    s <= step ? "bg-gradient-to-r from-blue-500 to-indigo-500" : "bg-white/[0.08]"
                  }`}
                />
              </div>
            ))}
          </div>
        )}

        {/* Step 1: Business Type */}
        {step === 1 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white mb-1">What type of business do you run?</h2>
              <p className="text-sm text-white/40">We'll customize your campaign for your industry.</p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {BUSINESS_TYPES.map((bt) => (
                <button
                  key={bt.value}
                  onClick={() => setBusinessType(bt.value)}
                  className={`p-4 rounded-2xl text-left transition-all duration-150 border ${
                    businessType === bt.value
                      ? "bg-blue-500/10 border-blue-500/40 text-white"
                      : "bg-white/[0.03] border-white/[0.06] text-white/60 hover:border-white/[0.12] hover:text-white/80"
                  }`}
                >
                  <div className="text-2xl mb-2">{bt.icon}</div>
                  <div className="text-sm font-medium">{bt.label}</div>
                </button>
              ))}
            </div>
            {businessType === "other" && (
              <input
                type="text"
                value={customType}
                onChange={(e) => setCustomType(e.target.value)}
                placeholder="e.g. Pool cleaning, Tree trimming..."
                className="w-full px-4 py-3 rounded-xl bg-white/[0.06] border border-white/[0.08] text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50 text-sm"
                autoFocus
              />
            )}
          </div>
        )}

        {/* Step 2: Location */}
        {step === 2 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white mb-1">Where do you serve customers?</h2>
              <p className="text-sm text-white/40">We'll target your ads to this area.</p>
            </div>
            <div className="relative">
              <MapPin className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/30" />
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Dallas, TX or Houston metro area"
                className="w-full pl-12 pr-4 py-4 rounded-2xl bg-white/[0.06] border border-white/[0.08] text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50 text-base"
                autoFocus
              />
            </div>
            <div className="flex items-center gap-2 p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
              <Shield className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <p className="text-xs text-white/40">
                Your ads will only show to people searching in this area. No wasted spend.
              </p>
            </div>
          </div>
        )}

        {/* Step 3: Budget */}
        {step === 3 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white mb-1">How aggressively do you want to grow?</h2>
              <p className="text-sm text-white/40">Choose a monthly ad spend that fits your goals.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {BUDGET_OPTIONS.map((bo) => (
                <button
                  key={bo.value}
                  onClick={() => {
                    setBudgetMonthly(bo.value);
                    if (bo.value !== 0) setCustomBudget("");
                  }}
                  className={`p-4 rounded-2xl text-left transition-all duration-150 border ${
                    budgetMonthly === bo.value
                      ? "bg-blue-500/10 border-blue-500/40 text-white"
                      : "bg-white/[0.03] border-white/[0.06] text-white/60 hover:border-white/[0.12] hover:text-white/80"
                  }`}
                >
                  <div className="text-base font-semibold mb-0.5">{bo.label}</div>
                  <div className="text-xs text-white/40">{bo.desc}</div>
                </button>
              ))}
            </div>
            {budgetMonthly === 0 && (
              <div className="relative">
                <DollarSign className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/30" />
                <input
                  type="number"
                  value={customBudget}
                  onChange={(e) => setCustomBudget(e.target.value)}
                  placeholder="Monthly budget in USD"
                  className="w-full pl-12 pr-4 py-3 rounded-xl bg-white/[0.06] border border-white/[0.08] text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50 text-sm"
                  min={100}
                  autoFocus
                />
              </div>
            )}
            {effectiveBudget > 0 && (
              <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06]">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-white/40">Estimated daily spend</span>
                  <span className="text-white font-semibold">${Math.round(effectiveBudget / 30)}/day</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 4: Goal */}
        {step === 4 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white mb-1">What's your primary goal?</h2>
              <p className="text-sm text-white/40">We'll optimize your campaign for maximum results.</p>
            </div>
            <div className="space-y-3">
              {GOAL_OPTIONS.map((go) => {
                const Icon = go.icon;
                return (
                  <button
                    key={go.value}
                    onClick={() => setGoal(go.value)}
                    className={`w-full flex items-center gap-4 p-5 rounded-2xl text-left transition-all duration-150 border ${
                      goal === go.value
                        ? "bg-blue-500/10 border-blue-500/40"
                        : "bg-white/[0.03] border-white/[0.06] hover:border-white/[0.12]"
                    }`}
                  >
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                      goal === go.value ? "bg-blue-500/20" : "bg-white/[0.06]"
                    }`}>
                      <Icon className={`w-6 h-6 ${goal === go.value ? "text-blue-400" : "text-white/40"}`} />
                    </div>
                    <div>
                      <div className={`font-semibold ${goal === go.value ? "text-white" : "text-white/70"}`}>
                        {go.label}
                      </div>
                      <div className="text-xs text-white/40 mt-0.5">{go.desc}</div>
                    </div>
                    {goal === go.value && (
                      <CheckCircle2 className="w-5 h-5 text-blue-400 ml-auto" />
                    )}
                  </button>
                );
              })}
            </div>

            {/* Review summary */}
            <div className="p-5 rounded-2xl bg-white/[0.04] border border-white/[0.06] space-y-3">
              <div className="text-xs font-semibold uppercase text-white/30 mb-2">Campaign Summary</div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-white/40">Business</span>
                <span className="text-white font-medium capitalize">{effectiveType.replace("_", " ")}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-white/40">Location</span>
                <span className="text-white font-medium">{location}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-white/40">Monthly Budget</span>
                <span className="text-white font-medium">${effectiveBudget.toLocaleString()}/mo</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-white/40">Goal</span>
                <span className="text-white font-medium capitalize">{goal.replace("_", " & ")}</span>
              </div>
            </div>
          </div>
        )}

        {/* Step 5: Building / Results */}
        {step === 5 && (
          <div className="space-y-6">
            {(building || (!result && !error)) && (
              <>
                <div className="text-center mb-6">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-indigo-500/20 border border-blue-500/30 flex items-center justify-center mx-auto mb-4">
                    <Sparkles className="w-8 h-8 text-blue-400 animate-pulse" />
                  </div>
                  <h2 className="text-lg font-semibold text-white mb-1">Building Your Campaign</h2>
                  <p className="text-sm text-white/40">AI is creating your personalized Google Ads campaign...</p>
                </div>

                <div ref={progressRef} className="space-y-2 max-h-[50vh] overflow-y-auto">
                  {progress.map((p, i) => (
                    <div
                      key={`${p.step}-${i}`}
                      className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]"
                    >
                      {p.status === "running" ? (
                        <Loader2 className="w-4 h-4 text-blue-400 animate-spin mt-0.5 flex-shrink-0" />
                      ) : (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-white">{p.step}</div>
                        <div className="text-xs text-white/40 mt-0.5">{p.detail}</div>
                      </div>
                      {p.elapsed_ms && p.status === "done" && (
                        <span className="text-[10px] text-white/20 font-mono">{p.elapsed_ms}ms</span>
                      )}
                    </div>
                  ))}
                  {building && progress.length === 0 && (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Error */}
            {error && !building && (
              <div className="text-center py-8">
                <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
                <h2 className="text-lg font-semibold text-white mb-2">Build Failed</h2>
                <p className="text-sm text-white/50 mb-6 max-w-sm mx-auto">{error}</p>
                <button
                  onClick={handleBuild}
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-medium"
                >
                  Try Again
                </button>
              </div>
            )}

            {/* Success */}
            {result && !building && (
              <div className="space-y-6">
                <div className="text-center">
                  <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500/20 to-green-500/20 border border-emerald-500/30 flex items-center justify-center mx-auto mb-4">
                    <CheckCircle2 className="w-8 h-8 text-emerald-400" />
                  </div>
                  <h2 className="text-xl font-bold text-white mb-1">Campaign Ready!</h2>
                  <p className="text-sm text-white/50">Your AI-built campaign is ready to launch.</p>
                </div>

                {/* Results grid */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 rounded-2xl bg-white/[0.04] border border-white/[0.06] text-center">
                    <div className="text-2xl font-bold text-white">{result.ad_groups}</div>
                    <div className="text-xs text-white/40 mt-1">Ad Groups</div>
                  </div>
                  <div className="p-4 rounded-2xl bg-white/[0.04] border border-white/[0.06] text-center">
                    <div className="text-2xl font-bold text-white">{result.keywords}</div>
                    <div className="text-xs text-white/40 mt-1">Keywords</div>
                  </div>
                  <div className="p-4 rounded-2xl bg-white/[0.04] border border-white/[0.06] text-center">
                    <div className="text-2xl font-bold text-white">{result.ads}</div>
                    <div className="text-xs text-white/40 mt-1">Ads Created</div>
                  </div>
                  <div className="p-4 rounded-2xl bg-white/[0.04] border border-white/[0.06] text-center">
                    <div className="text-2xl font-bold text-white">${result.budget_daily}</div>
                    <div className="text-xs text-white/40 mt-1">Daily Budget</div>
                  </div>
                </div>

                {/* Compliance score */}
                {result.compliance?.score && (
                  <div className="p-4 rounded-2xl bg-white/[0.04] border border-white/[0.06] flex items-center gap-4">
                    <div className={`w-14 h-14 rounded-xl flex items-center justify-center text-lg font-bold ${
                      (result.compliance.score || 0) >= 80
                        ? "bg-emerald-500/15 text-emerald-400"
                        : (result.compliance.score || 0) >= 60
                        ? "bg-amber-500/15 text-amber-400"
                        : "bg-red-500/15 text-red-400"
                    }`}>
                      {result.compliance.score}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-white">Google Ad Strength: {result.compliance.grade}</div>
                      <div className="text-xs text-white/40">AI quality score for your campaign</div>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-col gap-3">
                  <button
                    onClick={() => router.push(`/ads/campaigns`)}
                    className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 transition-all"
                  >
                    <Rocket className="w-5 h-5" /> View & Launch Campaign
                  </button>
                  <button
                    onClick={() => { setStep(1); setResult(null); setProgress([]); }}
                    className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-white/[0.06] text-white/60 hover:text-white hover:bg-white/[0.1] transition-all text-sm"
                  >
                    Build Another Campaign
                  </button>
                </div>

                {/* Builder log */}
                {progress.length > 0 && (
                  <details className="group">
                    <summary className="text-xs text-white/30 cursor-pointer hover:text-white/50 flex items-center gap-1">
                      <ChevronRight className="w-3 h-3 transition-transform group-open:rotate-90" />
                      AI Builder Log ({progress.length} steps)
                    </summary>
                    <div className="mt-3 space-y-1.5">
                      {progress.map((p, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-white/30">
                          <CheckCircle2 className="w-3 h-3 text-emerald-500/50" />
                          <span className="font-medium text-white/50">{p.step}</span>
                          <span className="flex-1 truncate">{p.detail}</span>
                          {p.elapsed_ms && (
                            <span className="font-mono text-white/20">{p.elapsed_ms}ms</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        )}

        {/* Navigation */}
        {step < 5 && (
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-white/[0.06]">
            <button
              onClick={prevStep}
              disabled={step === 1}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm text-white/40 hover:text-white hover:bg-white/[0.06] disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>

            {step < 4 ? (
              <button
                onClick={nextStep}
                disabled={!canProceed()}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 transition-all"
              >
                Continue <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleBuild}
                disabled={!canProceed()}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-green-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 transition-all"
              >
                <Rocket className="w-4 h-4" /> Build My Campaign
              </button>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
