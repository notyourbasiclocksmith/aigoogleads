import type { Metadata } from "next";
import {
  Zap, Brain, Shield, BarChart3, Target, Sparkles, ArrowRight,
  CheckCircle2, TrendingUp, Users, Lock, RefreshCcw,
  Bot, Eye, Lightbulb, Layers, ChevronDown,
  Search, FileText, Gauge, FlaskConical,
  GitBranch, Plug, Mail, Play, Rocket, Timer, ShieldCheck, AlertTriangle,
  LineChart, DollarSign, Megaphone,
} from "lucide-react";

export const metadata: Metadata = {
  metadataBase: new URL("https://aigoogleads.vercel.app"),
  title: "Ignite Ads AI — AI-Powered Google Ads Management Platform",
  description:
    "Stop wasting ad spend. Ignite Ads AI uses artificial intelligence to build, optimize, and manage your Google Ads campaigns with expert-level precision. Prompt-to-campaign in seconds. Built-in guardrails. 3 autonomy modes.",
  keywords:
    "AI Google Ads, Google Ads automation, AI campaign management, Google Ads AI tool, PPC automation, Google Ads optimizer, AI ad copy generator, Google Ads for small business, automated Google Ads, smart bidding AI",
  authors: [{ name: "Ignite Ads AI" }],
  creator: "Ignite Ads AI",
  publisher: "Ignite Ads AI",
  robots: "index, follow",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://aigoogleads.vercel.app/marketing",
    siteName: "Ignite Ads AI",
    title: "Ignite Ads AI — AI-Powered Google Ads Management Platform",
    description:
      "Stop wasting ad spend. AI builds, optimizes, and manages your Google Ads with expert-level precision. Prompt-to-campaign in seconds.",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Ignite Ads AI Platform",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Ignite Ads AI — AI-Powered Google Ads Management",
    description:
      "Stop wasting ad spend. AI builds, optimizes, and manages your Google Ads with expert-level precision.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://aigoogleads.vercel.app/marketing",
  },
};

function JsonLd() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Ignite Ads AI",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description:
      "AI-powered Google Ads management platform that builds, optimizes, and manages campaigns with expert-level precision.",
    offers: [
      {
        "@type": "Offer",
        name: "Starter",
        price: "49",
        priceCurrency: "USD",
        billingIncrement: "P1M",
      },
      {
        "@type": "Offer",
        name: "Pro",
        price: "199",
        priceCurrency: "USD",
        billingIncrement: "P1M",
      },
      {
        "@type": "Offer",
        name: "Elite",
        price: "499",
        priceCurrency: "USD",
        billingIncrement: "P1M",
      },
    ],
    featureList:
      "AI Campaign Generator, Competitive Intelligence, Performance Dashboard, Optimization Engine, A/B Testing, Multi-Workspace, Agency Mode",
    aggregateRating: {
      "@type": "AggregateRating",
      ratingValue: "4.9",
      ratingCount: "127",
      bestRating: "5",
    },
  };
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
    />
  );
}

/* ───────────────────── NAV ───────────────────── */
function Nav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              Ignite Ads AI
            </span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-600">
            <a href="#features" className="hover:text-blue-600 transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-blue-600 transition-colors">How It Works</a>
            <a href="#pricing" className="hover:text-blue-600 transition-colors">Pricing</a>
            <a href="#faq" className="hover:text-blue-600 transition-colors">FAQ</a>
          </div>
          <div className="flex items-center gap-3">
            <a href="/login" className="hidden sm:inline-flex text-sm font-medium text-gray-600 hover:text-blue-600 transition-colors">
              Log In
            </a>
            <a
              href="/login"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transition-all hover:-translate-y-0.5"
            >
              Start Free Trial <ArrowRight className="w-4 h-4" />
            </a>
          </div>
        </div>
      </div>
    </nav>
  );
}

/* ───────────────────── HERO ───────────────────── */
function Hero() {
  return (
    <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-28 overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-indigo-50/50 to-white" />
      <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-blue-400/10 rounded-full blur-3xl" />
      <div className="absolute top-40 right-0 w-[400px] h-[400px] bg-indigo-400/10 rounded-full blur-3xl" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-100 text-blue-700 text-sm font-medium mb-6">
            <Sparkles className="w-4 h-4" />
            AI-Powered Google Ads Management
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-gray-900 leading-[1.1]">
            Stop Wasting Ad Spend.{" "}
            <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
              Let AI Run Your Google Ads.
            </span>
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed">
            Describe what you want in plain English. Our AI builds expert-level campaigns, writes
            psychology-driven ad copy, and optimizes 24/7 with built-in safety guardrails.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="/login"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold text-lg shadow-xl shadow-blue-500/25 hover:shadow-blue-500/40 transition-all hover:-translate-y-0.5"
            >
              <Rocket className="w-5 h-5" /> Start Free Trial
            </a>
            <a
              href="#how-it-works"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-4 rounded-xl bg-white text-gray-700 font-semibold text-lg border border-gray-200 shadow-sm hover:shadow-md transition-all hover:-translate-y-0.5"
            >
              <Play className="w-5 h-5" /> See How It Works
            </a>
          </div>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm text-gray-500">
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> No credit card required</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> 14-day free trial</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> Cancel anytime</span>
          </div>
        </div>

        {/* Dashboard mockup */}
        <div className="mt-16 max-w-5xl mx-auto">
          <div className="relative rounded-2xl bg-gray-900 shadow-2xl shadow-gray-900/20 p-2 sm:p-3">
            <div className="flex gap-1.5 mb-3 px-2">
              <div className="w-3 h-3 rounded-full bg-red-400" />
              <div className="w-3 h-3 rounded-full bg-yellow-400" />
              <div className="w-3 h-3 rounded-full bg-green-400" />
            </div>
            <div className="rounded-xl bg-gradient-to-br from-gray-50 to-white p-4 sm:p-8">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Impressions", value: "142,891", change: "+18%", up: true },
                  { label: "Clicks", value: "8,234", change: "+24%", up: true },
                  { label: "Conversions", value: "312", change: "+31%", up: true },
                  { label: "CPA", value: "$28.40", change: "-12%", up: true },
                ].map((kpi) => (
                  <div key={kpi.label} className="bg-white rounded-lg border border-gray-100 p-3 sm:p-4 shadow-sm">
                    <p className="text-xs text-gray-500 font-medium">{kpi.label}</p>
                    <p className="text-lg sm:text-2xl font-bold text-gray-900 mt-1">{kpi.value}</p>
                    <p className={`text-xs font-semibold mt-1 ${kpi.up ? "text-green-600" : "text-red-600"}`}>
                      {kpi.change}
                    </p>
                  </div>
                ))}
              </div>
              <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="sm:col-span-2 bg-white rounded-lg border border-gray-100 p-4 shadow-sm h-40 flex items-end gap-1">
                  {[40, 55, 45, 60, 52, 70, 65, 80, 75, 85, 78, 95].map((h, i) => (
                    <div key={i} className="flex-1 bg-gradient-to-t from-blue-600 to-blue-400 rounded-t" style={{ height: `${h}%` }} />
                  ))}
                </div>
                <div className="bg-white rounded-lg border border-gray-100 p-4 shadow-sm">
                  <p className="text-xs text-gray-500 font-medium mb-3">AI Recommendations</p>
                  {["Pause 3 waste keywords", "Add 8 negatives", "Boost top ad group bid"].map((r, i) => (
                    <div key={i} className="flex items-center gap-2 py-1.5 text-xs">
                      <div className={`w-1.5 h-1.5 rounded-full ${i === 0 ? "bg-red-400" : i === 1 ? "bg-yellow-400" : "bg-green-400"}`} />
                      <span className="text-gray-700">{r}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── PROBLEM / SOLUTION ───────────────────── */
function ProblemSolution() {
  const problems = [
    { icon: DollarSign, text: "Wasting thousands on underperforming keywords" },
    { icon: Timer, text: "Hours spent manually adjusting bids and budgets" },
    { icon: AlertTriangle, text: "Missing broken conversion tracking for days" },
    { icon: Eye, text: "No visibility into what competitors are doing" },
    { icon: FileText, text: "Writing ad copy that doesn't convert" },
    { icon: TrendingUp, text: "No time to analyze data and optimize" },
  ];
  return (
    <section className="py-20 sm:py-28 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900 leading-tight">
              Managing Google Ads Is{" "}
              <span className="text-red-500">Exhausting</span>
            </h2>
            <p className="mt-4 text-lg text-gray-600 leading-relaxed">
              Small business owners and agencies spend 10+ hours per week on manual campaign management
              — and still miss critical optimizations that bleed budget.
            </p>
            <div className="mt-8 space-y-4">
              {problems.map((p, i) => (
                <div key={i} className="flex items-center gap-3 text-gray-700">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-red-50 flex items-center justify-center">
                    <p.icon className="w-5 h-5 text-red-500" />
                  </div>
                  <span className="font-medium">{p.text}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="relative">
            <div className="absolute -inset-4 bg-gradient-to-r from-blue-500/10 to-indigo-500/10 rounded-3xl blur-2xl" />
            <div className="relative bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl p-8 sm:p-10 text-white">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/15 text-sm font-medium mb-6">
                <Sparkles className="w-4 h-4" /> The Ignite Ads AI Solution
              </div>
              <h3 className="text-2xl sm:text-3xl font-bold leading-tight">
                AI That Manages Your Ads Like an Expert — 24/7
              </h3>
              <div className="mt-6 space-y-4">
                {[
                  "Builds campaigns from a simple English prompt",
                  "Detects waste and pauses underperformers automatically",
                  "Monitors conversion tracking health around the clock",
                  "Scans competitors and finds messaging gaps",
                  "Writes psychology-driven ad copy in your brand voice",
                  "Never exceeds your budget — guaranteed guardrails",
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-green-300 flex-shrink-0" />
                    <span className="text-blue-50">{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── HOW IT WORKS ───────────────────── */
function HowItWorks() {
  const steps = [
    {
      num: "01",
      title: "Connect Your Account",
      desc: "Link your Google Ads account in one click via OAuth. Our AI automatically scans your website, social profiles, and existing campaigns.",
      icon: Plug,
      color: "from-blue-500 to-blue-600",
    },
    {
      num: "02",
      title: "AI Analyzes Everything",
      desc: "Our AI crawls your website, extracts services, locations, trust signals, and brand voice. It studies your competitors and builds a strategic playbook.",
      icon: Brain,
      color: "from-indigo-500 to-indigo-600",
    },
    {
      num: "03",
      title: "Campaigns Launch & Optimize",
      desc: "Describe what you want in plain English. AI generates expert campaigns, writes ad copy, and optimizes 24/7 with safety guardrails protecting your budget.",
      icon: Rocket,
      color: "from-purple-500 to-purple-600",
    },
  ];
  return (
    <section id="how-it-works" className="py-20 sm:py-28 bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Up and Running in <span className="text-blue-600">3 Simple Steps</span>
          </h2>
          <p className="mt-4 text-lg text-gray-600">
            No PPC expertise required. Connect your account, let AI do the heavy lifting, and watch your results improve.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map((s, i) => (
            <div key={i} className="relative group">
              {i < 2 && (
                <div className="hidden md:block absolute top-16 left-full w-full h-0.5 bg-gradient-to-r from-gray-200 to-transparent z-0" />
              )}
              <div className="relative bg-white rounded-2xl p-8 shadow-sm border border-gray-100 hover:shadow-xl hover:border-blue-100 transition-all duration-300">
                <div className={`inline-flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br ${s.color} shadow-lg mb-6`}>
                  <s.icon className="w-7 h-7 text-white" />
                </div>
                <div className="text-xs font-bold text-blue-600 mb-2">STEP {s.num}</div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{s.title}</h3>
                <p className="text-gray-600 leading-relaxed">{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── AI PIPELINE ───────────────────── */
function AIPipeline() {
  const steps = [
    { icon: Search, label: "Intent Parsing", desc: "Extracts services, locations, urgency, goals" },
    { icon: Eye, label: "Competitor Intel", desc: "Pulls messaging themes & landing pages" },
    { icon: Layers, label: "Keyword Strategy", desc: "Tiered by intent: emergency to informational" },
    { icon: LineChart, label: "Performance Learnings", desc: "Same-industry historical playbook" },
    { icon: Target, label: "Campaign Type", desc: "Search, Display, PMax with reasoning" },
    { icon: GitBranch, label: "Themed Ad Groups", desc: "SKAGs & close-variant groups" },
    { icon: Megaphone, label: "Psychology-Driven Copy", desc: "Urgency, social proof, CTAs" },
    { icon: Plug, label: "Expert Extensions", desc: "Sitelinks, callouts, snippets, call" },
    { icon: DollarSign, label: "Smart Budget & Bids", desc: "Scheduling, device & location bids" },
    { icon: CheckCircle2, label: "Full Preview", desc: "Expert reasoning for every decision" },
  ];
  return (
    <section className="py-20 sm:py-28 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-100 text-indigo-700 text-sm font-medium mb-4">
            <Brain className="w-4 h-4" /> Core Differentiator
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            10-Step Expert Campaign Pipeline
          </h2>
          <p className="mt-4 text-lg text-gray-600">
            Type a prompt like &ldquo;Launch an emergency locksmith campaign for Dallas&rdquo; and our AI
            executes a 10-step expert pipeline that rivals a senior PPC strategist.
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
          {steps.map((s, i) => (
            <div key={i} className="group relative bg-gray-50 hover:bg-white rounded-xl p-5 border border-gray-100 hover:border-blue-200 hover:shadow-lg transition-all duration-300 text-center">
              <div className="absolute top-3 left-3 text-[10px] font-bold text-blue-400">{String(i + 1).padStart(2, "0")}</div>
              <div className="inline-flex items-center justify-center w-11 h-11 rounded-lg bg-blue-100 group-hover:bg-blue-600 transition-colors mb-3">
                <s.icon className="w-5 h-5 text-blue-600 group-hover:text-white transition-colors" />
              </div>
              <h4 className="text-sm font-bold text-gray-900 mb-1">{s.label}</h4>
              <p className="text-xs text-gray-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
        <div className="mt-10 text-center">
          <div className="inline-flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-6 py-3 text-green-800 text-sm font-medium">
            <CheckCircle2 className="w-5 h-5 text-green-600" />
            Save draft &rarr; Review &rarr; Approve &amp; Launch to Google Ads with one click
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── FEATURES GRID ───────────────────── */
function Features() {
  const features = [
    {
      icon: Brain,
      title: "AI Business Intelligence",
      desc: "Crawls your website & socials. Extracts services, locations, USPs, trust signals. Detects brand voice for all future ad copy.",
      gradient: "from-blue-500 to-blue-600",
    },
    {
      icon: Megaphone,
      title: "Creative Studio",
      desc: "AI generates headlines, descriptions, callouts, sitelinks in your brand voice. Plus AI image generation via DALL-E 3, Stability AI, and Flux.1.",
      gradient: "from-purple-500 to-purple-600",
    },
    {
      icon: BarChart3,
      title: "Performance Dashboard",
      desc: "Real-time KPIs, trend charts, campaign drill-downs. Impressions, clicks, cost, conversions, CTR, CPC, CPA, ROAS — all in one view.",
      gradient: "from-green-500 to-green-600",
    },
    {
      icon: Gauge,
      title: "Diagnostic Engine",
      desc: "Daily automated diagnostics: budget pacing, CTR drops, CPA spikes, conversion tracking health, and waste keyword detection.",
      gradient: "from-orange-500 to-orange-600",
    },
    {
      icon: Eye,
      title: "Competitive Intelligence",
      desc: "SERP ad scanner, auction insights, competitor profiles, messaging heatmaps, landing page comparisons, and opportunity gap analysis.",
      gradient: "from-red-500 to-red-600",
    },
    {
      icon: FlaskConical,
      title: "A/B Experiments",
      desc: "Hypothesis-driven tests with multi-variant support. Full lifecycle: draft, start, monitor, stop, promote winner — all tracked.",
      gradient: "from-pink-500 to-pink-600",
    },
    {
      icon: Target,
      title: "Conversion Truth Layer",
      desc: "GA4 integration, tracking health scanner, offline conversion uploads, and a profit model that calculates your true target CPA.",
      gradient: "from-cyan-500 to-cyan-600",
    },
    {
      icon: Users,
      title: "Multi-Workspace & Agency Mode",
      desc: "Manage multiple businesses with workspace switching. MCC support, role-based access (Owner, Admin, Analyst, Viewer), and team invitations.",
      gradient: "from-indigo-500 to-indigo-600",
    },
  ];
  return (
    <section id="features" className="py-20 sm:py-28 bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Everything You Need to <span className="text-blue-600">Dominate Google Ads</span>
          </h2>
          <p className="mt-4 text-lg text-gray-600">
            A complete AI-powered platform that replaces your PPC agency — at a fraction of the cost.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => (
            <div key={i} className="group bg-white rounded-2xl p-6 border border-gray-100 hover:border-blue-200 shadow-sm hover:shadow-xl transition-all duration-300">
              <div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br ${f.gradient} shadow-lg mb-5`}>
                <f.icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">{f.title}</h3>
              <p className="text-sm text-gray-600 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── AUTONOMY MODES ───────────────────── */
function AutonomyModes() {
  const modes = [
    {
      name: "Suggest",
      icon: Lightbulb,
      desc: "AI analyzes and recommends — all changes require your manual approval. Full visibility, zero surprises.",
      color: "blue",
      features: [
        "AI generates recommendations",
        "You review every change",
        "One-click approve or reject",
        "Full change history & reasoning",
      ],
    },
    {
      name: "Semi-Auto",
      icon: Bot,
      desc: "Low-risk changes applied automatically. Medium and high-risk changes still require your approval.",
      color: "indigo",
      badge: "Most Popular",
      features: [
        "Auto-pauses waste keywords",
        "Auto-adds negative keywords",
        "Budget changes need approval",
        "Bid strategy changes need approval",
      ],
    },
    {
      name: "Full-Auto",
      icon: Rocket,
      desc: "AI handles low and medium-risk optimizations automatically. High-risk changes still require approval.",
      color: "purple",
      features: [
        "Automated bid adjustments",
        "Automated budget tuning",
        "Schedule & geo optimization",
        "High-risk still needs your OK",
      ],
    },
  ];
  const colorMap: Record<string, { bg: string; border: string; badge: string; icon: string; check: string }> = {
    blue: { bg: "bg-blue-50", border: "border-blue-200", badge: "bg-blue-600", icon: "bg-blue-100 text-blue-600", check: "text-blue-500" },
    indigo: { bg: "bg-indigo-50", border: "border-indigo-200", badge: "bg-indigo-600", icon: "bg-indigo-100 text-indigo-600", check: "text-indigo-500" },
    purple: { bg: "bg-purple-50", border: "border-purple-200", badge: "bg-purple-600", icon: "bg-purple-100 text-purple-600", check: "text-purple-500" },
  };
  return (
    <section className="py-20 sm:py-28 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            You Choose How Much <span className="text-blue-600">Control AI Gets</span>
          </h2>
          <p className="mt-4 text-lg text-gray-600">
            Three autonomy modes let you decide the perfect balance between automation and oversight.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {modes.map((m) => {
            const c = colorMap[m.color];
            return (
              <div key={m.name} className={`relative rounded-2xl p-8 border-2 ${m.badge ? c.border : "border-gray-100"} ${m.badge ? c.bg : "bg-white"} transition-all hover:shadow-lg`}>
                {m.badge && (
                  <div className={`absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full ${c.badge} text-white text-xs font-bold`}>
                    {m.badge}
                  </div>
                )}
                <div className={`inline-flex items-center justify-center w-14 h-14 rounded-xl ${c.icon} mb-6`}>
                  <m.icon className="w-7 h-7" />
                </div>
                <h3 className="text-2xl font-bold text-gray-900 mb-3">{m.name} Mode</h3>
                <p className="text-gray-600 mb-6 leading-relaxed">{m.desc}</p>
                <ul className="space-y-3">
                  {m.features.map((f, i) => (
                    <li key={i} className="flex items-center gap-2.5 text-sm text-gray-700">
                      <CheckCircle2 className={`w-4 h-4 flex-shrink-0 ${c.check}`} />
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── GUARDRAILS ───────────────────── */
function Guardrails() {
  const rules = [
    { icon: DollarSign, title: "Budget Cap Enforcement", desc: "Never exceeds your daily cap or weekly change limit" },
    { icon: Shield, title: "Broad Match Protection", desc: "Never auto-switches all keywords to broad match" },
    { icon: AlertTriangle, title: "Conversion Tracking Guard", desc: "All autopilot blocked if tracking breaks" },
    { icon: Timer, title: "72-Hour Cooldown", desc: "Max 3 system changes per 72h for major actions" },
    { icon: Lock, title: "Blocked Dangerous Actions", desc: "Delete campaign & remove conversions permanently blocked" },
    { icon: RefreshCcw, title: "One-Click Rollback", desc: "Every change logged with full diff and instant undo" },
  ];
  return (
    <section className="py-20 sm:py-28 bg-gradient-to-br from-gray-900 via-gray-900 to-indigo-950 text-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div>
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/10 text-blue-300 text-sm font-medium mb-6">
              <ShieldCheck className="w-4 h-4" /> Non-Negotiable Safety
            </div>
            <h2 className="text-3xl sm:text-4xl font-extrabold leading-tight">
              Built-In Guardrails{" "}
              <span className="text-blue-400">Protect Every Dollar</span>
            </h2>
            <p className="mt-4 text-lg text-gray-300 leading-relaxed">
              AI automation without guardrails is dangerous. Our safety engine enforces budget caps,
              blocks risky actions, monitors conversion health, and provides instant rollback for every
              single change.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {rules.map((r, i) => (
              <div key={i} className="bg-white/5 backdrop-blur-sm rounded-xl p-5 border border-white/10 hover:border-blue-500/30 hover:bg-white/10 transition-all">
                <r.icon className="w-8 h-8 text-blue-400 mb-3" />
                <h4 className="font-bold text-white mb-1">{r.title}</h4>
                <p className="text-sm text-gray-400 leading-relaxed">{r.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── PRICING ───────────────────── */
function Pricing() {
  const plans = [
    {
      name: "Starter",
      price: 49,
      desc: "Perfect for single-location businesses getting started with AI ads.",
      features: ["1 Google Ads account", "Suggest mode (manual approval)", "1 report per month", "10 AI campaign prompts", "Email support"],
      cta: "Start Free Trial",
      highlighted: false,
    },
    {
      name: "Pro",
      price: 199,
      desc: "For growing businesses that want AI doing the heavy lifting.",
      features: ["3 Google Ads accounts", "Semi-Auto mode", "Weekly reports", "50 AI campaign prompts", "Creative Studio", "Competitive Intelligence", "Priority support"],
      cta: "Start Free Trial",
      highlighted: true,
    },
    {
      name: "Elite",
      price: 499,
      desc: "For agencies and multi-location businesses demanding full power.",
      features: ["Unlimited accounts", "Full-Auto mode", "Weekly + Monthly reports", "Unlimited AI prompts", "Agency / MCC mode", "All integrations", "All connectors", "Dedicated support"],
      cta: "Start Free Trial",
      highlighted: false,
    },
  ];
  return (
    <section id="pricing" className="py-20 sm:py-28 bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Simple, Transparent <span className="text-blue-600">Pricing</span>
          </h2>
          <p className="mt-4 text-lg text-gray-600">
            No hidden fees. No long-term contracts. Start free and upgrade when you&apos;re ready.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {plans.map((p) => (
            <div key={p.name} className={`relative rounded-2xl p-8 ${p.highlighted ? "bg-white border-2 border-blue-500 shadow-xl shadow-blue-500/10 scale-[1.02]" : "bg-white border border-gray-200 shadow-sm"}`}>
              {p.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-blue-600 text-white text-xs font-bold">
                  Most Popular
                </div>
              )}
              <h3 className="text-xl font-bold text-gray-900">{p.name}</h3>
              <div className="mt-4 flex items-baseline gap-1">
                <span className="text-5xl font-extrabold text-gray-900">${p.price}</span>
                <span className="text-gray-500">/mo</span>
              </div>
              <p className="mt-3 text-sm text-gray-600">{p.desc}</p>
              <a
                href="/login"
                className={`mt-6 block w-full text-center py-3 rounded-xl font-semibold text-sm transition-all ${
                  p.highlighted
                    ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40"
                    : "bg-gray-100 text-gray-900 hover:bg-gray-200"
                }`}
              >
                {p.cta}
              </a>
              <ul className="mt-8 space-y-3">
                {p.features.map((f, i) => (
                  <li key={i} className="flex items-center gap-2.5 text-sm text-gray-700">
                    <CheckCircle2 className="w-4 h-4 text-blue-500 flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── INTEGRATIONS ───────────────────── */
function Integrations() {
  const integrations = [
    "Google Ads", "Google Analytics 4", "HubSpot", "Salesforce",
    "CallRail", "Slack", "SendGrid", "Stripe",
    "Meta Ads", "TikTok Ads", "YouTube Ads", "Webhooks",
  ];
  return (
    <section className="py-20 sm:py-28 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
          Connects With Your <span className="text-blue-600">Entire Stack</span>
        </h2>
        <p className="mt-4 text-lg text-gray-600 max-w-2xl mx-auto">
          Native integrations with the tools you already use. CRM, call tracking, analytics, notifications, and billing — all connected.
        </p>
        <div className="mt-12 grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-4">
          {integrations.map((name) => (
            <div key={name} className="flex items-center justify-center h-20 bg-gray-50 rounded-xl border border-gray-100 hover:border-blue-200 hover:shadow-md transition-all">
              <span className="text-sm font-semibold text-gray-700">{name}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── FAQ ───────────────────── */
function FAQ() {
  const faqs = [
    {
      q: "Do I need Google Ads experience to use Ignite Ads AI?",
      a: "Not at all. Our AI handles the complexity. Just describe what you want in plain English — like \"Launch a campaign for emergency plumbing in Houston\" — and our 10-step AI pipeline builds an expert-level campaign for you.",
    },
    {
      q: "Will AI accidentally overspend my budget?",
      a: "Never. Our guardrails engine enforces hard budget caps, limits weekly spend changes to 20% (configurable), and blocks all automation if conversion tracking breaks. Every change is logged with one-click rollback.",
    },
    {
      q: "How is this different from Google's Smart Campaigns?",
      a: "Google's Smart Campaigns give you almost zero control and transparency. Ignite Ads AI gives you expert-level campaign structure (SKAGs, themed ad groups), psychology-driven ad copy, competitive intelligence, three autonomy modes, and full visibility into every decision the AI makes.",
    },
    {
      q: "Can I use this for my agency with multiple clients?",
      a: "Yes. Our Elite plan supports unlimited accounts with MCC/agency mode. Each client gets their own isolated workspace with role-based access (Owner, Admin, Analyst, Viewer). Cross-account KPI rollups included.",
    },
    {
      q: "What happens to my existing campaigns?",
      a: "We sync your existing campaigns, ad groups, keywords, and performance data. The AI audits everything and generates optimization recommendations — but never makes changes without your approval (in Suggest mode).",
    },
    {
      q: "Can I cancel anytime?",
      a: "Absolutely. No contracts, no commitments. Cancel with one click from your billing portal. Your Google Ads account and campaigns remain yours — we never lock you in.",
    },
  ];
  return (
    <section id="faq" className="py-20 sm:py-28 bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Frequently Asked <span className="text-blue-600">Questions</span>
          </h2>
        </div>
        <div className="space-y-4">
          {faqs.map((f, i) => (
            <details key={i} className="group bg-white rounded-xl border border-gray-200 overflow-hidden">
              <summary className="flex items-center justify-between cursor-pointer px-6 py-5 text-left font-semibold text-gray-900 hover:bg-gray-50 transition-colors">
                {f.q}
                <ChevronDown className="w-5 h-5 text-gray-400 transition-transform group-open:rotate-180 flex-shrink-0 ml-4" />
              </summary>
              <div className="px-6 pb-5 text-gray-600 leading-relaxed">
                {f.a}
              </div>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── CTA FOOTER ───────────────────── */
function CTAFooter() {
  return (
    <section className="py-20 sm:py-28 bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-700 text-white">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold leading-tight">
          Ready to Let AI Manage Your Google Ads?
        </h2>
        <p className="mt-6 text-lg sm:text-xl text-blue-100 max-w-2xl mx-auto">
          Join hundreds of businesses saving time and money with AI-powered campaign management. Start your free trial today.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="/login"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-10 py-4 rounded-xl bg-white text-blue-600 font-bold text-lg shadow-xl hover:shadow-2xl transition-all hover:-translate-y-0.5"
          >
            <Rocket className="w-5 h-5" /> Start Free Trial
          </a>
          <a
            href="mailto:contact@thekeybot.com"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-10 py-4 rounded-xl bg-white/10 backdrop-blur-sm text-white font-semibold text-lg border border-white/20 hover:bg-white/20 transition-all"
          >
            <Mail className="w-5 h-5" /> Contact Sales
          </a>
        </div>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm text-blue-200">
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> 14-day free trial</span>
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> No credit card required</span>
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Cancel anytime</span>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── FOOTER ───────────────────── */
function Footer() {
  return (
    <footer className="bg-gray-900 text-gray-400 py-12 sm:py-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
          <div className="col-span-2 sm:col-span-1">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <span className="text-lg font-bold text-white">Ignite Ads AI</span>
            </div>
            <p className="text-sm leading-relaxed">
              AI-powered Google Ads management for service businesses and agencies.
            </p>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Product</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="#features" className="hover:text-white transition-colors">Features</a></li>
              <li><a href="#pricing" className="hover:text-white transition-colors">Pricing</a></li>
              <li><a href="#how-it-works" className="hover:text-white transition-colors">How It Works</a></li>
              <li><a href="#faq" className="hover:text-white transition-colors">FAQ</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Platform</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/login" className="hover:text-white transition-colors">Log In</a></li>
              <li><a href="/login" className="hover:text-white transition-colors">Sign Up</a></li>
              <li><a href="mailto:contact@thekeybot.com" className="hover:text-white transition-colors">Contact</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Legal</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="#" className="hover:text-white transition-colors">Privacy Policy</a></li>
              <li><a href="#" className="hover:text-white transition-colors">Terms of Service</a></li>
            </ul>
          </div>
        </div>
        <div className="mt-12 pt-8 border-t border-gray-800 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
          <p>&copy; {new Date().getFullYear()} Ignite Ads AI. All rights reserved.</p>
          <p>Built with AI for businesses that demand results.</p>
        </div>
      </div>
    </footer>
  );
}

/* ───────────────────── PAGE ───────────────────── */
export default function MarketingPage() {
  return (
    <>
      <JsonLd />
      <Nav />
      <main>
        <Hero />
        <ProblemSolution />
        <HowItWorks />
        <AIPipeline />
        <Features />
        <AutonomyModes />
        <Guardrails />
        <Pricing />
        <Integrations />
        <FAQ />
        <CTAFooter />
      </main>
      <Footer />
    </>
  );
}
