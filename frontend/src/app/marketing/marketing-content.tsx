import {
  Zap, Brain, Shield, BarChart3, Target, Sparkles, ArrowRight,
  CheckCircle2, TrendingUp, Users, Lock, RefreshCcw,
  Bot, Eye, Lightbulb, Layers, ChevronDown,
  Search, FileText, Gauge, FlaskConical,
  GitBranch, Plug, Mail, Play, Rocket, Timer, ShieldCheck,
  LineChart, DollarSign, Megaphone, Star, Globe, MousePointerClick,
  X, ChevronRight, Scan, MonitorSmartphone, MapPin, Phone,
  Image, PenTool, LayoutTemplate, Clock, Palette, Wand2,
} from "lucide-react";

function JsonLd() {
  const softwareApp = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "IntelliAds",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description:
      "AI-powered platform that creates professional ad campaigns in under 5 minutes — keyword research, ad copy, images, and landing pages included.",
    offers: [
      {
        "@type": "Offer",
        name: "Starter",
        price: "97",
        priceCurrency: "USD",
        billingIncrement: "P1M",
      },
      {
        "@type": "Offer",
        name: "Pro",
        price: "197",
        priceCurrency: "USD",
        billingIncrement: "P1M",
      },
      {
        "@type": "Offer",
        name: "Elite",
        price: "397",
        priceCurrency: "USD",
        billingIncrement: "P1M",
      },
    ],
    featureList:
      "AI Campaign Builder, Keyword Research, Ad Copy Generator, Image Generation, Landing Page Creator, Google Ads, Meta Ads, Google Business Profile",
  };

  const organization = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "IntelliAds",
    url: "https://getintelliads.com",
    logo: "https://getintelliads.com/logo.png",
    email: "hello@getintelliads.com",
    description:
      "AI-powered marketing automation platform for Google Ads, Meta Ads, and Google Business Profile",
    foundingDate: "2024",
    sameAs: [],
  };

  const faqPage = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "How can IntelliAds create campaigns in 5 minutes?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "We use 6 specialized AI agents that work in parallel. While one researches keywords, another writes ad copy, another generates images, and another builds your landing page. This parallel processing is what makes it possible to do in minutes what takes humans hours.",
        },
      },
      {
        "@type": "Question",
        name: "Do I need any advertising experience?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Not at all. Just describe your business or enter your website URL. Our AI handles keyword research, ad copy, image creation, landing pages, targeting, and bidding strategy. You just review and approve.",
        },
      },
      {
        "@type": "Question",
        name: "What platforms do you support?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Google Ads (Search, Display, Performance Max), Meta Ads (Facebook and Instagram), and Google Business Profile. All managed from one dashboard with one subscription.",
        },
      },
      {
        "@type": "Question",
        name: "How does the AI image generation work?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "We use multiple AI image generation APIs to create professional ad images sized for every placement — feed, stories, display, etc. Just describe what you want or let the AI decide based on your business and campaign goals.",
        },
      },
      {
        "@type": "Question",
        name: "Are landing pages included?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Yes. Our AI Landing Page Agent creates conversion-optimized pages with your branding, deployed and hosted automatically. No developer needed. Each page is designed to match your ad campaign for maximum conversion rates.",
        },
      },
      {
        "@type": "Question",
        name: "Will AI accidentally overspend my budget?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Never. Our guardrails engine enforces hard budget caps, limits spend changes, and blocks all automation if conversion tracking breaks. Every change is logged with one-click rollback.",
        },
      },
      {
        "@type": "Question",
        name: "Can I use this for my agency with multiple clients?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Yes. Our Elite plan supports unlimited accounts with MCC/agency mode. Each client gets their own isolated workspace with role-based access.",
        },
      },
      {
        "@type": "Question",
        name: "Can I cancel anytime?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Absolutely. No contracts, no commitments. Cancel with one click. Your ad accounts and campaigns remain yours.",
        },
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareApp) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(organization) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqPage) }}
      />
    </>
  );
}

/* ───────────────────── NAV ───────────────────── */
function Nav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-xl border-b border-gray-100/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-violet-600 to-indigo-600 bg-clip-text text-transparent tracking-tight">
              IntelliAds
            </span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-600">
            <a href="#how-it-works" className="hover:text-violet-600 transition-colors">How It Works</a>
            <a href="#features" className="hover:text-violet-600 transition-colors">Features</a>
            <a href="#pricing" className="hover:text-violet-600 transition-colors">Pricing</a>
            <a href="#faq" className="hover:text-violet-600 transition-colors">FAQ</a>
          </div>
          <div className="flex items-center gap-3">
            <a href="/login" className="hidden sm:inline-flex text-sm font-medium text-gray-600 hover:text-violet-600 transition-colors">
              Log In
            </a>
            <a
              href="/pricing"
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-semibold shadow-lg shadow-violet-500/25 hover:shadow-violet-500/40 transition-all hover:-translate-y-0.5"
            >
              Get Started <ArrowRight className="w-4 h-4" />
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
    <section className="relative pt-32 pb-24 sm:pt-40 sm:pb-32 overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-violet-50 via-white to-white" />
      <div className="absolute top-20 left-1/4 w-[600px] h-[600px] bg-violet-400/8 rounded-full blur-3xl" />
      <div className="absolute top-40 right-1/4 w-[400px] h-[400px] bg-indigo-400/8 rounded-full blur-3xl" />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-violet-50 border border-violet-100 text-violet-700 text-sm font-medium mb-8">
            <Clock className="w-4 h-4" />
            What takes agencies 2-3 hours, takes IntelliAds 5 minutes
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-7xl font-extrabold tracking-tight text-gray-900 leading-[1.05]">
            Professional Ad Campaigns{" "}
            <span className="bg-gradient-to-r from-violet-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
              in Under 5 Minutes
            </span>
          </h1>
          <p className="mt-8 text-lg sm:text-xl text-gray-500 max-w-2xl mx-auto leading-relaxed">
            AI agents handle everything — keyword research, ad copy, image generation,
            and landing pages. Just describe your business and launch.
          </p>

          {/* Platform badges */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            {[
              { label: "Google Ads", color: "bg-blue-50 text-blue-700 border-blue-100" },
              { label: "Meta / Instagram", color: "bg-pink-50 text-pink-700 border-pink-100" },
              { label: "Google Business Profile", color: "bg-green-50 text-green-700 border-green-100" },
              { label: "Landing Pages", color: "bg-amber-50 text-amber-700 border-amber-100" },
            ].map((p) => (
              <span key={p.label} className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${p.color}`}>
                {p.label}
              </span>
            ))}
          </div>

          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="/pricing"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-10 py-4 rounded-2xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-bold text-lg shadow-xl shadow-violet-500/25 hover:shadow-violet-500/40 transition-all hover:-translate-y-0.5"
            >
              <Rocket className="w-5 h-5" /> Start Free Trial
            </a>
            <a
              href="#how-it-works"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-10 py-4 rounded-2xl bg-white text-gray-700 font-semibold text-lg border border-gray-200 shadow-sm hover:shadow-lg transition-all hover:-translate-y-0.5"
            >
              <Play className="w-5 h-5" /> Watch Demo
            </a>
          </div>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm text-gray-400">
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> No credit card required</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> 14-day free trial</span>
            <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-green-500" /> Cancel anytime</span>
          </div>
        </div>

        {/* Campaign Builder Preview */}
        <div className="mt-20 max-w-5xl mx-auto">
          <div className="relative rounded-2xl bg-gray-950 shadow-2xl shadow-gray-900/30 p-2 sm:p-3">
            <div className="flex gap-1.5 mb-3 px-2">
              <div className="w-3 h-3 rounded-full bg-red-400" />
              <div className="w-3 h-3 rounded-full bg-yellow-400" />
              <div className="w-3 h-3 rounded-full bg-green-400" />
            </div>
            <div className="rounded-xl bg-gradient-to-br from-gray-50 to-white p-6 sm:p-8">
              {/* Chat prompt */}
              <div className="flex items-start gap-3 mb-6">
                <div className="w-8 h-8 rounded-full bg-violet-100 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-violet-600" />
                </div>
                <div className="bg-violet-50 rounded-2xl rounded-tl-md px-5 py-3 max-w-md">
                  <p className="text-sm text-gray-700">Create a lead generation campaign for my locksmith business in Dallas, TX. Budget $30/day.</p>
                </div>
              </div>

              {/* AI Pipeline Progress */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
                {[
                  { label: "Keyword Research", status: "done", icon: Search },
                  { label: "Competitor Intel", status: "done", icon: Eye },
                  { label: "Ad Copy", status: "done", icon: PenTool },
                  { label: "Image Generation", status: "done", icon: Image },
                  { label: "Landing Page", status: "done", icon: LayoutTemplate },
                  { label: "Campaign Ready", status: "done", icon: Rocket },
                ].map((s) => (
                  <div key={s.label} className="bg-white rounded-xl border border-gray-100 p-3 text-center shadow-sm">
                    <s.icon className="w-5 h-5 text-violet-600 mx-auto mb-1.5" />
                    <p className="text-[10px] font-semibold text-gray-900">{s.label}</p>
                    <div className="flex items-center justify-center gap-1 mt-1">
                      <CheckCircle2 className="w-3 h-3 text-green-500" />
                      <span className="text-[9px] text-green-600 font-medium">Complete</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Results summary */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Keywords Found", value: "47", sub: "High-intent" },
                  { label: "Ad Variations", value: "12", sub: "A/B ready" },
                  { label: "Landing Page", value: "1", sub: "Conversion optimized" },
                  { label: "Time Elapsed", value: "4:32", sub: "Minutes" },
                ].map((kpi) => (
                  <div key={kpi.label} className="bg-gradient-to-br from-violet-50 to-indigo-50 rounded-xl border border-violet-100 p-4">
                    <p className="text-xs text-gray-500 font-medium">{kpi.label}</p>
                    <p className="text-2xl font-extrabold text-gray-900 mt-1">{kpi.value}</p>
                    <p className="text-xs text-violet-600 font-medium mt-0.5">{kpi.sub}</p>
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

/* ───────────────────── SOCIAL PROOF ───────────────────── */
function SocialProof() {
  const stats = [
    { value: "5 min", label: "Avg. Campaign Creation" },
    { value: "2,100+", label: "Campaigns Launched" },
    { value: "86%", label: "Avg. CPA Reduction" },
    { value: "$1.2M+", label: "Ad Spend Managed" },
  ];
  return (
    <section className="py-16 bg-white border-y border-gray-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <div className="text-3xl sm:text-4xl font-extrabold bg-gradient-to-r from-violet-600 to-indigo-600 bg-clip-text text-transparent">{s.value}</div>
              <p className="mt-1 text-sm text-gray-500 font-medium">{s.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── THE PROBLEM ───────────────────── */
function Problem() {
  return (
    <section className="py-24 sm:py-32 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900 leading-tight">
              Creating Ad Campaigns Is{" "}
              <span className="text-red-500">Expensive & Slow</span>
            </h2>
            <p className="mt-5 text-lg text-gray-500 leading-relaxed">
              Marketing agencies charge thousands per month and take weeks to launch. DIY means
              hours of keyword research, writing ad copy, designing images, and building landing pages.
            </p>
            <div className="mt-8 space-y-4">
              {[
                { icon: Timer, text: "2-3 hours to create a single campaign manually" },
                { icon: DollarSign, text: "$1,500 - $5,000/mo for a PPC agency" },
                { icon: Search, text: "Hours on keyword research without the right tools" },
                { icon: PenTool, text: "Writing ad copy that doesn't convert" },
                { icon: Image, text: "No budget for professional ad images" },
                { icon: LayoutTemplate, text: "No developer to build landing pages" },
              ].map((p, i) => (
                <div key={i} className="flex items-center gap-3 text-gray-600">
                  <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center">
                    <p.icon className="w-5 h-5 text-red-400" />
                  </div>
                  <span className="font-medium">{p.text}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="relative">
            <div className="absolute -inset-4 bg-gradient-to-r from-violet-500/10 to-indigo-500/10 rounded-3xl blur-2xl" />
            <div className="relative bg-gradient-to-br from-violet-600 to-indigo-700 rounded-2xl p-10 text-white">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/15 text-sm font-medium mb-6">
                <Sparkles className="w-4 h-4" /> The IntelliAds Way
              </div>
              <h3 className="text-2xl sm:text-3xl font-bold leading-tight">
                6 AI Agents Build Your Entire Campaign — Automatically
              </h3>
              <div className="mt-8 space-y-4">
                {[
                  "Keyword research powered by Ahrefs intelligence",
                  "AI writes conversion-optimized ad copy",
                  "Professional images generated in seconds",
                  "Landing pages created and deployed instantly",
                  "Google Ads + Meta/Instagram + Google Business",
                  "From idea to live campaign in under 5 minutes",
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-green-300 flex-shrink-0" />
                    <span className="text-violet-50">{item}</span>
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
      title: "Describe Your Business",
      desc: "Enter your website URL or describe your business in plain English. Our AI scans everything — services, locations, competitors, and brand voice.",
      icon: Globe,
      color: "from-violet-500 to-violet-600",
    },
    {
      num: "02",
      title: "AI Agents Go to Work",
      desc: "6 specialized AI agents run in parallel — researching keywords, writing ad copy, generating images, and building your landing page.",
      icon: Bot,
      color: "from-indigo-500 to-indigo-600",
    },
    {
      num: "03",
      title: "Review & Launch",
      desc: "Preview your complete campaign — ads, keywords, images, landing page. One click to deploy to Google Ads, Meta, or both.",
      icon: Rocket,
      color: "from-purple-500 to-purple-600",
    },
  ];
  return (
    <section id="how-it-works" className="py-24 sm:py-32 bg-gray-50/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-violet-50 border border-violet-100 text-violet-700 text-sm font-medium mb-4">
            <Sparkles className="w-4 h-4" /> Simple 3-Step Process
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            From Zero to Live Campaign in{" "}
            <span className="text-violet-600">5 Minutes</span>
          </h2>
          <p className="mt-4 text-lg text-gray-500">
            No PPC expertise. No design skills. No developer needed.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map((s, i) => (
            <div key={i} className="relative group">
              {i < 2 && (
                <div className="hidden md:block absolute top-16 left-full w-full h-0.5 bg-gradient-to-r from-gray-200 to-transparent z-0" />
              )}
              <div className="relative bg-white rounded-2xl p-8 shadow-sm border border-gray-100 hover:shadow-xl hover:border-violet-100 transition-all duration-300">
                <div className={`inline-flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br ${s.color} shadow-lg mb-6`}>
                  <s.icon className="w-7 h-7 text-white" />
                </div>
                <div className="text-xs font-bold text-violet-600 mb-2">STEP {s.num}</div>
                <h3 className="text-xl font-bold text-gray-900 mb-3">{s.title}</h3>
                <p className="text-gray-500 leading-relaxed">{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── AI AGENT PIPELINE ───────────────────── */
function AgentPipeline() {
  const agents = [
    { icon: Brain, label: "Strategist Agent", desc: "Analyzes your business, competitors, and market to choose optimal campaign structure", color: "from-violet-500 to-violet-600" },
    { icon: Search, label: "Keyword Agent", desc: "Uses Ahrefs data to find high-intent keywords, long-tail variations, and negative keywords", color: "from-blue-500 to-blue-600" },
    { icon: Target, label: "Targeting Agent", desc: "Sets geo-targeting, demographics, ad schedule, and device bids for maximum ROI", color: "from-cyan-500 to-cyan-600" },
    { icon: PenTool, label: "Ad Copy Agent", desc: "Writes 15 headlines, 4 descriptions per ad group with psychology-driven messaging", color: "from-indigo-500 to-indigo-600" },
    { icon: Image, label: "Creative Agent", desc: "Generates professional ad images using AI — sized for feed, stories, and display", color: "from-purple-500 to-purple-600" },
    { icon: LayoutTemplate, label: "Landing Page Agent", desc: "Creates conversion-optimized landing pages with your branding, deployed instantly", color: "from-pink-500 to-pink-600" },
  ];
  return (
    <section className="py-24 sm:py-32 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 text-sm font-medium mb-4">
            <Bot className="w-4 h-4" /> Powered by 6 AI Agents
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Each Agent Is an Expert at{" "}
            <span className="text-violet-600">One Thing</span>
          </h2>
          <p className="mt-4 text-lg text-gray-500">
            Instead of one generic AI doing everything poorly, 6 specialized agents each handle
            what they do best — then assemble the perfect campaign together.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((a, i) => (
            <div key={i} className="group bg-white rounded-2xl p-7 border border-gray-100 hover:border-violet-200 shadow-sm hover:shadow-xl transition-all duration-300">
              <div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br ${a.color} shadow-lg mb-5`}>
                <a.icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">{a.label}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{a.desc}</p>
            </div>
          ))}
        </div>
        <div className="mt-12 text-center">
          <div className="inline-flex items-center gap-3 bg-violet-50 border border-violet-200 rounded-2xl px-8 py-4 text-violet-800 font-medium">
            <Wand2 className="w-5 h-5 text-violet-600" />
            All 6 agents run in parallel — your campaign is ready in minutes, not hours
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
      icon: Search,
      title: "Keyword Intelligence",
      desc: "Powered by Ahrefs. Finds high-intent keywords, search volumes, difficulty scores, and competitor gaps automatically.",
      gradient: "from-blue-500 to-blue-600",
    },
    {
      icon: PenTool,
      title: "AI Ad Copy",
      desc: "Writes headlines, descriptions, and extensions in your brand voice. Psychology-driven copy that converts.",
      gradient: "from-violet-500 to-violet-600",
    },
    {
      icon: Image,
      title: "AI Image Generation",
      desc: "Professional ad images generated via multiple AI APIs — sized perfectly for every placement and platform.",
      gradient: "from-purple-500 to-purple-600",
    },
    {
      icon: LayoutTemplate,
      title: "Landing Page Builder",
      desc: "AI creates conversion-optimized landing pages with your branding. Deployed and hosted automatically.",
      gradient: "from-pink-500 to-pink-600",
    },
    {
      icon: BarChart3,
      title: "Performance Dashboard",
      desc: "Real-time KPIs, trend charts, campaign drill-downs. Impressions, clicks, conversions, CPA, ROAS — all in one view.",
      gradient: "from-green-500 to-green-600",
    },
    {
      icon: Eye,
      title: "Competitive Intelligence",
      desc: "SERP ad scanner, competitor profiles, messaging heatmaps, and opportunity gap analysis.",
      gradient: "from-orange-500 to-orange-600",
    },
    {
      icon: Bot,
      title: "AI Operator Chat",
      desc: "Talk to your campaigns in plain English. Ask questions, request changes, get insights — the AI handles it.",
      gradient: "from-cyan-500 to-cyan-600",
    },
    {
      icon: Shield,
      title: "Budget Guardrails",
      desc: "AI never overspends. Hard budget caps, change limits, conversion tracking monitors, and instant rollback.",
      gradient: "from-indigo-500 to-indigo-600",
    },
  ];
  return (
    <section id="features" className="py-24 sm:py-32 bg-gray-50/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Everything You Need.{" "}
            <span className="text-violet-600">One Platform.</span>
          </h2>
          <p className="mt-4 text-lg text-gray-500">
            Stop paying for 5 different tools. IntelliAds replaces your keyword tool, copywriter, designer, developer, and PPC manager.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => (
            <div key={i} className="group bg-white rounded-2xl p-6 border border-gray-100 hover:border-violet-200 shadow-sm hover:shadow-xl transition-all duration-300">
              <div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br ${f.gradient} shadow-lg mb-5`}>
                <f.icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">{f.title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── PLATFORMS ───────────────────── */
function Platforms() {
  const platforms = [
    {
      name: "Google Ads",
      desc: "Search, Display, and Performance Max campaigns with expert-level keyword strategy and ad copy.",
      features: ["Search campaigns", "Display ads", "Performance Max", "Smart bidding"],
      color: "from-blue-500 to-blue-600",
      icon: Search,
    },
    {
      name: "Meta / Instagram",
      desc: "Facebook and Instagram ads with AI-generated creatives, carousel ads, and audience targeting.",
      features: ["Facebook feed ads", "Instagram stories", "Carousel creatives", "Lead generation"],
      color: "from-pink-500 to-rose-600",
      icon: Users,
    },
    {
      name: "Google Business Profile",
      desc: "Keep your GBP updated with AI-generated posts, offers, and event updates automatically.",
      features: ["Auto-post updates", "Offer promotions", "Event posts", "Photo uploads"],
      color: "from-green-500 to-emerald-600",
      icon: MapPin,
    },
  ];
  return (
    <section className="py-24 sm:py-32 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            One Platform.{" "}
            <span className="text-violet-600">Every Channel.</span>
          </h2>
          <p className="mt-4 text-lg text-gray-500">
            Manage Google Ads, Meta/Instagram, and Google Business Profile from a single dashboard.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {platforms.map((p) => (
            <div key={p.name} className="bg-white rounded-2xl p-8 border border-gray-100 shadow-sm hover:shadow-xl transition-all">
              <div className={`inline-flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br ${p.color} shadow-lg mb-6`}>
                <p.icon className="w-7 h-7 text-white" />
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-3">{p.name}</h3>
              <p className="text-gray-500 mb-6 leading-relaxed">{p.desc}</p>
              <ul className="space-y-2.5">
                {p.features.map((f, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm text-gray-600">
                    <CheckCircle2 className="w-4 h-4 text-violet-500 flex-shrink-0" />
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

/* ───────────────────── COMPARISON ───────────────────── */
function Comparison() {
  return (
    <section className="py-24 sm:py-32 bg-gradient-to-br from-gray-900 via-gray-900 to-indigo-950 text-white">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold leading-tight">
            Replace Your Agency.{" "}
            <span className="text-violet-300">Save Thousands.</span>
          </h2>
          <p className="mt-4 text-lg text-gray-400 max-w-2xl mx-auto">
            Get better results than a $3,000/mo agency — at a fraction of the cost.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-2xl p-8 border border-white/10">
            <h3 className="text-xl font-bold text-white/60 mb-8">Traditional Agency</h3>
            <ul className="space-y-5">
              {[
                { label: "Monthly cost", value: "$1,500 - $5,000" },
                { label: "Campaign creation", value: "2 - 4 weeks" },
                { label: "Keyword research", value: "Basic, manual" },
                { label: "Ad images", value: "Extra $500+ per set" },
                { label: "Landing pages", value: "Extra $1,000+" },
                { label: "Optimization", value: "Weekly (maybe)" },
              ].map((row) => (
                <li key={row.label} className="flex justify-between text-sm">
                  <span className="text-gray-400">{row.label}</span>
                  <span className="text-white/50 font-medium">{row.value}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-white rounded-2xl p-8 border-2 border-violet-400 shadow-2xl relative">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-violet-600 text-white text-xs font-bold">
              10x Better Value
            </div>
            <h3 className="text-xl font-bold text-gray-900 mb-8">IntelliAds</h3>
            <ul className="space-y-5">
              {[
                { label: "Monthly cost", value: "$97 - $397" },
                { label: "Campaign creation", value: "Under 5 minutes" },
                { label: "Keyword research", value: "Ahrefs-powered AI" },
                { label: "Ad images", value: "AI-generated, included" },
                { label: "Landing pages", value: "AI-built, included" },
                { label: "Optimization", value: "24/7 continuous AI" },
              ].map((row) => (
                <li key={row.label} className="flex justify-between text-sm">
                  <span className="text-gray-500">{row.label}</span>
                  <span className="font-bold text-violet-600">{row.value}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ───────────────────── REAL RESULTS ───────────────────── */
function RealResults() {
  const cases = [
    {
      industry: "Locksmith",
      location: "Dallas, TX",
      before: { cpa: "$52", ctr: "2.1%", leads: "18/mo" },
      after: { cpa: "$28", ctr: "5.8%", leads: "47/mo" },
      improvement: "+161% more leads",
      time: "Campaign built in 4 min",
    },
    {
      industry: "HVAC",
      location: "Houston, TX",
      before: { cpa: "$89", ctr: "1.4%", leads: "12/mo" },
      after: { cpa: "$41", ctr: "4.2%", leads: "34/mo" },
      improvement: "+183% more leads",
      time: "Campaign built in 3 min",
    },
    {
      industry: "Plumbing",
      location: "Austin, TX",
      before: { cpa: "$67", ctr: "1.8%", leads: "22/mo" },
      after: { cpa: "$33", ctr: "5.1%", leads: "51/mo" },
      improvement: "+132% more leads",
      time: "Campaign built in 5 min",
    },
  ];
  return (
    <section className="py-24 sm:py-32 bg-gray-50/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Real Results From{" "}
            <span className="text-violet-600">Real Businesses</span>
          </h2>
          <p className="mt-4 text-lg text-gray-500">
            See how local businesses transformed their advertising with IntelliAds.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {cases.map((c) => (
            <div key={c.industry} className="bg-white rounded-2xl border border-gray-100 overflow-hidden shadow-sm hover:shadow-xl transition-all">
              <div className="bg-gradient-to-r from-violet-600 to-indigo-600 px-6 py-4">
                <h3 className="text-white font-bold text-lg">{c.industry}</h3>
                <p className="text-violet-200 text-sm flex items-center gap-1"><MapPin className="w-3.5 h-3.5" /> {c.location}</p>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Before</p>
                    <div className="space-y-1.5 text-sm">
                      <p className="text-gray-500">CPA: <span className="font-bold text-red-500">{c.before.cpa}</span></p>
                      <p className="text-gray-500">CTR: <span className="font-bold text-red-500">{c.before.ctr}</span></p>
                      <p className="text-gray-500">Leads: <span className="font-bold text-red-500">{c.before.leads}</span></p>
                    </div>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase mb-2">After IntelliAds</p>
                    <div className="space-y-1.5 text-sm">
                      <p className="text-gray-500">CPA: <span className="font-bold text-green-600">{c.after.cpa}</span></p>
                      <p className="text-gray-500">CTR: <span className="font-bold text-green-600">{c.after.ctr}</span></p>
                      <p className="text-gray-500">Leads: <span className="font-bold text-green-600">{c.after.leads}</span></p>
                    </div>
                  </div>
                </div>
                <div className="bg-green-50 rounded-xl px-4 py-2.5 text-center mb-3">
                  <span className="text-green-700 font-bold text-sm">{c.improvement}</span>
                </div>
                <p className="text-xs text-violet-600 font-medium text-center flex items-center justify-center gap-1">
                  <Clock className="w-3 h-3" /> {c.time}
                </p>
              </div>
            </div>
          ))}
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
      price: 97,
      desc: "Perfect for single-location businesses getting started.",
      features: [
        "1 Google Ads account",
        "1 Meta Ads account",
        "Up to $5K/mo ad spend",
        "50 AI campaign builds/mo",
        "AI image generation",
        "5 landing pages",
        "Email support",
      ],
      cta: "Start Free Trial",
      highlighted: false,
    },
    {
      name: "Pro",
      price: 197,
      desc: "For growing businesses that want the full AI advantage.",
      features: [
        "5 ad accounts (Google + Meta)",
        "Up to $25K/mo ad spend",
        "500 AI campaign builds/mo",
        "Unlimited AI images",
        "25 landing pages",
        "Competitive intelligence",
        "AI Operator chat",
        "Priority support",
      ],
      cta: "Start Free Trial",
      highlighted: true,
    },
    {
      name: "Elite",
      price: 397,
      desc: "For agencies and multi-location businesses.",
      features: [
        "Unlimited ad accounts",
        "Unlimited ad spend",
        "Unlimited AI builds",
        "Unlimited everything",
        "Agency / MCC mode",
        "Google Business Profile",
        "White-label options",
        "Dedicated support",
      ],
      cta: "Start Free Trial",
      highlighted: false,
    },
  ];
  return (
    <section id="pricing" className="py-24 sm:py-32 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Simple, Transparent{" "}
            <span className="text-violet-600">Pricing</span>
          </h2>
          <p className="mt-4 text-lg text-gray-500">
            No hidden fees. No contracts. Everything you need to create professional campaigns.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {plans.map((p) => (
            <div key={p.name} className={`relative rounded-2xl p-8 ${p.highlighted ? "bg-white border-2 border-violet-500 shadow-xl shadow-violet-500/10 scale-[1.02]" : "bg-white border border-gray-200 shadow-sm"}`}>
              {p.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-violet-600 text-white text-xs font-bold">
                  Most Popular
                </div>
              )}
              <h3 className="text-xl font-bold text-gray-900">{p.name}</h3>
              <div className="mt-4 flex items-baseline gap-1">
                <span className="text-5xl font-extrabold text-gray-900">${p.price}</span>
                <span className="text-gray-400">/mo</span>
              </div>
              <p className="mt-3 text-sm text-gray-500">{p.desc}</p>
              <a
                href={`/pricing?plan=${p.name.toLowerCase()}`}
                className={`mt-6 block w-full text-center py-3.5 rounded-xl font-semibold text-sm transition-all ${
                  p.highlighted
                    ? "bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-lg shadow-violet-500/25 hover:shadow-violet-500/40"
                    : "bg-gray-100 text-gray-900 hover:bg-gray-200"
                }`}
              >
                {p.cta}
              </a>
              <ul className="mt-8 space-y-3">
                {p.features.map((f, i) => (
                  <li key={i} className="flex items-center gap-2.5 text-sm text-gray-600">
                    <CheckCircle2 className="w-4 h-4 text-violet-500 flex-shrink-0" />
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

/* ───────────────────── FAQ ───────────────────── */
function FAQ() {
  const faqs = [
    {
      q: "How can IntelliAds create campaigns in 5 minutes?",
      a: "We use 6 specialized AI agents that work in parallel. While one researches keywords, another writes ad copy, another generates images, and another builds your landing page. This parallel processing is what makes it possible to do in minutes what takes humans hours.",
    },
    {
      q: "Do I need any advertising experience?",
      a: "Not at all. Just describe your business or enter your website URL. Our AI handles keyword research, ad copy, image creation, landing pages, targeting, and bidding strategy. You just review and approve.",
    },
    {
      q: "What platforms do you support?",
      a: "Google Ads (Search, Display, Performance Max), Meta Ads (Facebook and Instagram), and Google Business Profile. All managed from one dashboard with one subscription.",
    },
    {
      q: "How does the AI image generation work?",
      a: "We use multiple AI image generation APIs to create professional ad images sized for every placement — feed, stories, display, etc. Just describe what you want or let the AI decide based on your business and campaign goals.",
    },
    {
      q: "Are landing pages included?",
      a: "Yes. Our AI Landing Page Agent creates conversion-optimized pages with your branding, deployed and hosted automatically. No developer needed. Each page is designed to match your ad campaign for maximum conversion rates.",
    },
    {
      q: "Will AI accidentally overspend my budget?",
      a: "Never. Our guardrails engine enforces hard budget caps, limits spend changes, and blocks all automation if conversion tracking breaks. Every change is logged with one-click rollback.",
    },
    {
      q: "Can I use this for my agency with multiple clients?",
      a: "Yes. Our Elite plan supports unlimited accounts with MCC/agency mode. Each client gets their own isolated workspace with role-based access.",
    },
    {
      q: "Can I cancel anytime?",
      a: "Absolutely. No contracts, no commitments. Cancel with one click. Your ad accounts and campaigns remain yours.",
    },
  ];
  return (
    <section id="faq" className="py-24 sm:py-32 bg-gray-50/50">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-gray-900">
            Frequently Asked{" "}
            <span className="text-violet-600">Questions</span>
          </h2>
        </div>
        <div className="space-y-4">
          {faqs.map((f, i) => (
            <details key={i} className="group bg-white rounded-xl border border-gray-200 overflow-hidden">
              <summary className="flex items-center justify-between cursor-pointer px-6 py-5 text-left font-semibold text-gray-900 hover:bg-gray-50 transition-colors">
                {f.q}
                <ChevronDown className="w-5 h-5 text-gray-400 transition-transform group-open:rotate-180 flex-shrink-0 ml-4" />
              </summary>
              <div className="px-6 pb-5 text-gray-500 leading-relaxed">
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
    <section className="py-24 sm:py-32 bg-gradient-to-br from-violet-600 via-indigo-600 to-purple-700 text-white">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold leading-tight">
          Your Next Campaign Is{" "}
          <span className="text-violet-200">5 Minutes Away</span>
        </h2>
        <p className="mt-6 text-lg sm:text-xl text-violet-100 max-w-2xl mx-auto">
          Stop spending hours on campaign creation. Let 6 AI agents build professional
          campaigns with keyword research, ad copy, images, and landing pages — all included.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="/pricing"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-10 py-4 rounded-2xl bg-white text-violet-600 font-bold text-lg shadow-xl hover:shadow-2xl transition-all hover:-translate-y-0.5"
          >
            <Rocket className="w-5 h-5" /> Start Free Trial
          </a>
          <a
            href="mailto:hello@getintelliads.com"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-10 py-4 rounded-2xl bg-white/10 backdrop-blur-sm text-white font-semibold text-lg border border-white/20 hover:bg-white/20 transition-all"
          >
            <Mail className="w-5 h-5" /> Contact Sales
          </a>
        </div>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm text-violet-200">
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
    <footer className="bg-gray-950 text-gray-400 py-12 sm:py-16">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
          <div className="col-span-2 sm:col-span-1">
            <div className="flex items-center gap-2.5 mb-4">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <span className="text-lg font-bold text-white tracking-tight">IntelliAds</span>
            </div>
            <p className="text-sm leading-relaxed">
              Professional ad campaigns in under 5 minutes. Powered by AI.
            </p>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Product</h4>
            <ul className="space-y-2.5 text-sm">
              <li><a href="#features" className="hover:text-white transition-colors">Features</a></li>
              <li><a href="#pricing" className="hover:text-white transition-colors">Pricing</a></li>
              <li><a href="#how-it-works" className="hover:text-white transition-colors">How It Works</a></li>
              <li><a href="#faq" className="hover:text-white transition-colors">FAQ</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Platform</h4>
            <ul className="space-y-2.5 text-sm">
              <li><a href="/login" className="hover:text-white transition-colors">Log In</a></li>
              <li><a href="/register" className="hover:text-white transition-colors">Sign Up</a></li>
              <li><a href="mailto:hello@getintelliads.com" className="hover:text-white transition-colors">Contact</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white mb-4">Legal</h4>
            <ul className="space-y-2.5 text-sm">
              <li><a href="/privacy" className="hover:text-white transition-colors">Privacy Policy</a></li>
              <li><a href="/privacy" className="hover:text-white transition-colors">Terms of Service</a></li>
            </ul>
          </div>
        </div>
        <div className="mt-12 pt-8 border-t border-gray-800 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
          <p>&copy; {new Date().getFullYear()} IntelliAds. All rights reserved.</p>
          <p className="text-gray-500">Professional campaigns. Minutes, not hours.</p>
        </div>
      </div>
    </footer>
  );
}

/* ───────────────────── PAGE ───────────────────── */
export default function MarketingContent() {
  return (
    <>
      <JsonLd />
      <Nav />
      <main>
        <Hero />
        <SocialProof />
        <Problem />
        <HowItWorks />
        <AgentPipeline />
        <Features />
        <Platforms />
        <Comparison />
        <RealResults />
        <Pricing />
        <FAQ />
        <CTAFooter />
      </main>
      <Footer />
    </>
  );
}
