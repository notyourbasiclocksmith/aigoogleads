"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Zap, CheckCircle2, ArrowRight, Shield, Eye, EyeOff,
  Rocket, Brain, Star,
} from "lucide-react";

import { api } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const planDetails: Record<string, { name: string; price: number; icon: any; color: string }> = {
  starter: { name: "Starter", price: 97, icon: Rocket, color: "from-blue-500 to-blue-600" },
  pro: { name: "Pro", price: 197, icon: Brain, color: "from-indigo-500 to-indigo-600" },
  elite: { name: "Elite", price: 397, icon: Star, color: "from-purple-500 to-purple-600" },
};

function RegisterContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const planParam = searchParams.get("plan") || "pro";
  const plan = planDetails[planParam] ? planParam : "pro";
  const currentPlan = planDetails[plan];
  const PlanIcon = currentPlan.icon;

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<"register" | "checkout">("register");

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      // 1. Register account
      const registerRes = await fetch(`${API_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: fullName }),
      });
      if (!registerRes.ok) {
        const errData = await registerRes.json().catch(() => ({}));
        throw new Error(errData.detail || "Registration failed");
      }

      // 2. Login to get token
      const loginRes = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const loginData = await loginRes.json();
      if (!loginRes.ok) throw new Error(loginData.detail || "Login failed");

      const token = loginData.access_token;
      localStorage.setItem("token", token);

      // Store tenant ID if available
      if (loginData.tenants && loginData.tenants.length > 0) {
        localStorage.setItem("tenant_id", loginData.tenants[0].tenant_id);
      }

      const tenantId = loginData.tenants?.[0]?.tenant_id;
      if (!tenantId) {
        // Create tenant if none exists
        const createData = await api.post("/api/workspace/tenants", { name: companyName || fullName });
        if (createData.tenant?.id) {
          localStorage.setItem("tenant_id", createData.tenant.id);
        } else if (createData.tenant_id) {
          localStorage.setItem("tenant_id", createData.tenant_id);
        }
      }

      const finalTenantId = localStorage.getItem("tenant_id");

      // 3. Create Stripe customer
      await api.post("/api/v2/billing/create-customer", {
        tenant_id: finalTenantId,
        email: email,
        name: companyName || fullName,
      });

      // 4. Create checkout session
      const checkoutData = await api.post("/api/v2/billing/checkout", {
        tenant_id: finalTenantId,
        plan: plan,
        success_url: `${window.location.origin}/onboarding?plan=${plan}&checkout=success`,
        cancel_url: `${window.location.origin}/pricing?canceled=true`,
      });

      if (checkoutData.checkout_url) {
        setStep("checkout");
        window.location.href = checkoutData.checkout_url;
      } else {
        // Fallback: go to onboarding
        router.push(`/onboarding?plan=${plan}`);
      }
    } catch (err: any) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex">
      {/* Left: Plan summary */}
      <div className="hidden lg:flex lg:w-[480px] flex-col justify-between p-10 border-r border-white/10">
        <div>
          <a href="/marketing" className="flex items-center gap-2 mb-12">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-white">IgniteAds.ai</span>
          </a>

          <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r ${currentPlan.color} mb-6`}>
            <PlanIcon className="w-5 h-5 text-white" />
            <span className="text-sm font-bold text-white">{currentPlan.name} Plan</span>
          </div>

          <h2 className="text-3xl font-extrabold text-white leading-tight mb-3">
            Start your 14-day<br />free trial
          </h2>
          <p className="text-gray-400 leading-relaxed">
            Get full access to the {currentPlan.name} plan. No credit card required during trial.
            Then ${currentPlan.price}/mo after trial ends.
          </p>

          <div className="mt-8 space-y-3">
            {[
              "AI campaign builder from simple prompts",
              "Competitor intelligence & SERP scanning",
              "Daily diagnostic engine with auto-alerts",
              "Built-in guardrails protect your budget",
              "Cancel anytime, no contracts",
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-2.5 text-sm text-gray-300">
                <CheckCircle2 className="w-4 h-4 text-blue-400 flex-shrink-0" />
                {item}
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-white/5 border border-white/10 mt-8">
          <Shield className="w-6 h-6 text-green-400 flex-shrink-0" />
          <p className="text-xs text-gray-400">
            Your data is encrypted and secure. Payments processed by Stripe.
            30-day money-back guarantee.
          </p>
        </div>

        <div className="mt-6 flex items-center gap-6 text-sm text-gray-500">
          <a href="/pricing" className="hover:text-white transition-colors">← Back to pricing</a>
          <a href="/login" className="hover:text-white transition-colors">Already have an account?</a>
        </div>
      </div>

      {/* Right: Registration form */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-white">IgniteAds.ai</span>
          </div>

          {/* Mobile plan badge */}
          <div className="lg:hidden mb-6">
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gradient-to-r ${currentPlan.color} text-xs font-bold text-white`}>
              <PlanIcon className="w-3.5 h-3.5" /> {currentPlan.name} Plan — ${currentPlan.price}/mo
            </div>
          </div>

          <h1 className="text-2xl font-bold text-white mb-1">Create your account</h1>
          <p className="text-sm text-gray-400 mb-8">
            {step === "checkout"
              ? "Redirecting to secure checkout..."
              : "Fill in your details to get started with your free trial."}
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-400">
              {error}
            </div>
          )}

          <form onSubmit={handleRegister} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Full Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                placeholder="John Smith"
                className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Work Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="john@company.com"
                className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Company Name</label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Acme Services LLC"
                className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  placeholder="Min. 8 characters"
                  className="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-white placeholder:text-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors text-sm pr-12"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold text-sm shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  Create Account & Start Trial <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-gray-500">
            By creating an account, you agree to our{" "}
            <a href="#" className="text-blue-400 hover:text-blue-300">Terms of Service</a>{" "}
            and{" "}
            <a href="#" className="text-blue-400 hover:text-blue-300">Privacy Policy</a>.
          </p>

          <p className="mt-4 text-center text-sm text-gray-400">
            Already have an account?{" "}
            <a href="/login" className="text-blue-400 hover:text-blue-300 font-medium">Sign in</a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="animate-pulse text-white text-xl">Loading...</div>
      </div>
    }>
      <RegisterContent />
    </Suspense>
  );
}
