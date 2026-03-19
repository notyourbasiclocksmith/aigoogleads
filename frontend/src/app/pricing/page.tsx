"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Zap, CheckCircle2, ArrowRight, Shield, Brain, Rocket,
  Star, Users, BarChart3, Lock, TrendingUp, ChevronDown,
} from "lucide-react";

// Use relative URLs so requests go through Next.js rewrite proxy

const plans = [
  {
    id: "starter",
    name: "Starter",
    price: 97,
    desc: "Perfect for single-location businesses getting started with AI ads.",
    features: [
      "1 Google Ads account",
      "Up to $5K/mo ad spend",
      "Suggest mode (manual approval)",
      "50 AI campaign prompts/mo",
      "20 SERP competitor scans",
      "10 SEOpix image credits",
      "Email support",
    ],
    icon: Rocket,
    color: "blue",
    highlighted: false,
  },
  {
    id: "pro",
    name: "Pro",
    price: 197,
    desc: "For growing businesses that want AI doing the heavy lifting.",
    features: [
      "5 Google Ads accounts",
      "Up to $25K/mo ad spend",
      "Semi-Auto mode",
      "500 AI campaign prompts/mo",
      "200 SERP competitor scans",
      "100 SEOpix image credits",
      "Creative Studio",
      "Competitive Intelligence",
      "Priority support",
    ],
    icon: Brain,
    color: "indigo",
    highlighted: true,
  },
  {
    id: "elite",
    name: "Elite",
    price: 397,
    desc: "For agencies and multi-location businesses demanding full power.",
    features: [
      "Unlimited accounts",
      "Unlimited ad spend",
      "Full-Auto mode",
      "Unlimited AI prompts",
      "Unlimited SERP scans",
      "500 SEOpix image credits",
      "Agency / MCC mode",
      "All integrations & connectors",
      "Dedicated support",
    ],
    icon: Star,
    color: "purple",
    highlighted: false,
  },
];

const faqs = [
  {
    q: "Is there a free trial?",
    a: "Yes! Every plan includes a 14-day free trial. No credit card required to start. You'll only be charged after the trial ends and you choose to continue.",
  },
  {
    q: "Can I change plans later?",
    a: "Absolutely. You can upgrade or downgrade at any time from your billing dashboard. Changes take effect immediately and are prorated.",
  },
  {
    q: "What payment methods do you accept?",
    a: "We accept all major credit cards (Visa, Mastercard, Amex, Discover) through our secure Stripe payment processor.",
  },
  {
    q: "What happens if I cancel?",
    a: "You can cancel anytime with no penalties. Your account stays active until the end of your billing period. All your data is retained for 30 days after cancellation.",
  },
  {
    q: "Do you offer annual billing?",
    a: "Annual plans are coming soon with a 20% discount. Sign up monthly now and we'll automatically migrate you when annual billing launches.",
  },
];

function PricingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselected = searchParams.get("plan") || "";
  const [selectedPlan, setSelectedPlan] = useState(preselected || "pro");
  const [loading, setLoading] = useState<string | null>(null);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  useEffect(() => {
    if (preselected && ["starter", "pro", "elite"].includes(preselected)) {
      setSelectedPlan(preselected);
    }
  }, [preselected]);

  async function handleCheckout(planId: string) {
    setLoading(planId);
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        // Not logged in — redirect to register with plan context
        router.push(`/register?plan=${planId}`);
        return;
      }
      const tenantId = localStorage.getItem("tenant_id");
      if (!tenantId) {
        router.push(`/register?plan=${planId}`);
        return;
      }
      const res = await fetch(`/api/v2/billing/checkout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          tenant_id: tenantId,
          plan: planId,
          success_url: `${window.location.origin}/dashboard?checkout=success&plan=${planId}`,
          cancel_url: `${window.location.origin}/pricing?canceled=true`,
        }),
      });
      const data = await res.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      console.error("Checkout error:", err);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900">
      {/* Nav */}
      <nav className="border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <a href="/marketing" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-white">IgniteAds.ai</span>
          </a>
          <div className="flex items-center gap-3">
            <a href="/login" className="text-sm text-gray-400 hover:text-white transition-colors">
              Sign In
            </a>
            <a
              href="/register"
              className="text-sm font-semibold px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            >
              Get Started
            </a>
          </div>
        </div>
      </nav>

      {/* Header */}
      <div className="text-center pt-16 pb-8 px-4">
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white leading-tight">
          Choose Your <span className="bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">Plan</span>
        </h1>
        <p className="mt-4 text-lg text-gray-400 max-w-2xl mx-auto">
          Start with a 14-day free trial. No credit card required. Cancel anytime.
        </p>
      </div>

      {/* Pricing Cards */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
          {plans.map((p) => {
            const isSelected = selectedPlan === p.id;
            const Icon = p.icon;
            return (
              <div
                key={p.id}
                onClick={() => setSelectedPlan(p.id)}
                className={`relative rounded-2xl p-8 cursor-pointer transition-all duration-300 ${
                  p.highlighted
                    ? "bg-white border-2 border-blue-500 shadow-2xl shadow-blue-500/20 scale-[1.02]"
                    : isSelected
                    ? "bg-white border-2 border-blue-400 shadow-xl"
                    : "bg-white/5 backdrop-blur-sm border border-white/10 hover:border-white/30"
                }`}
              >
                {p.highlighted && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-xs font-bold">
                    Most Popular
                  </div>
                )}
                <div className="flex items-center gap-3 mb-4">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                    p.highlighted || isSelected
                      ? "bg-gradient-to-br from-blue-500 to-indigo-600"
                      : "bg-white/10"
                  }`}>
                    <Icon className={`w-5 h-5 ${p.highlighted || isSelected ? "text-white" : "text-gray-400"}`} />
                  </div>
                  <h3 className={`text-xl font-bold ${p.highlighted || isSelected ? "text-gray-900" : "text-white"}`}>
                    {p.name}
                  </h3>
                </div>
                <div className="flex items-baseline gap-1 mb-3">
                  <span className={`text-5xl font-extrabold ${p.highlighted || isSelected ? "text-gray-900" : "text-white"}`}>
                    ${p.price}
                  </span>
                  <span className={p.highlighted || isSelected ? "text-gray-500" : "text-gray-400"}>/mo</span>
                </div>
                <p className={`text-sm mb-6 ${p.highlighted || isSelected ? "text-gray-600" : "text-gray-400"}`}>
                  {p.desc}
                </p>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCheckout(p.id);
                  }}
                  disabled={loading === p.id}
                  className={`w-full py-3 rounded-xl font-semibold text-sm transition-all flex items-center justify-center gap-2 ${
                    p.highlighted || isSelected
                      ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40"
                      : "bg-white/10 text-white hover:bg-white/20"
                  }`}
                >
                  {loading === p.id ? (
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <>
                      Start Free Trial <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
                <ul className="mt-6 space-y-2.5">
                  {p.features.map((f, i) => (
                    <li key={i} className={`flex items-center gap-2.5 text-sm ${
                      p.highlighted || isSelected ? "text-gray-700" : "text-gray-300"
                    }`}>
                      <CheckCircle2 className={`w-4 h-4 flex-shrink-0 ${
                        p.highlighted || isSelected ? "text-blue-500" : "text-blue-400/60"
                      }`} />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Trust badges */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-8 text-sm text-gray-400">
          <span className="flex items-center gap-2"><Shield className="w-4 h-4" /> Secured by Stripe</span>
          <span className="flex items-center gap-2"><Lock className="w-4 h-4" /> 256-bit encryption</span>
          <span className="flex items-center gap-2"><TrendingUp className="w-4 h-4" /> 14-day free trial</span>
          <span className="flex items-center gap-2"><Users className="w-4 h-4" /> 2,100+ campaigns launched</span>
        </div>

        {/* FAQ */}
        <div className="mt-20 max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-white text-center mb-8">Frequently Asked Questions</h2>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div key={i} className="rounded-xl border border-white/10 overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-5 text-left hover:bg-white/5 transition-colors"
                >
                  <span className="text-sm font-semibold text-white">{faq.q}</span>
                  <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${openFaq === i ? "rotate-180" : ""}`} />
                </button>
                {openFaq === i && (
                  <div className="px-5 pb-5">
                    <p className="text-sm text-gray-400 leading-relaxed">{faq.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Money-back guarantee */}
        <div className="mt-16 text-center">
          <div className="inline-flex items-center gap-3 px-6 py-4 rounded-2xl bg-white/5 border border-white/10">
            <Shield className="w-8 h-8 text-green-400" />
            <div className="text-left">
              <p className="text-sm font-bold text-white">30-Day Money-Back Guarantee</p>
              <p className="text-xs text-gray-400">Not satisfied? Get a full refund within 30 days. No questions asked.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PricingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="animate-pulse text-white text-xl">Loading...</div>
      </div>
    }>
      <PricingPageContent />
    </Suspense>
  );
}
