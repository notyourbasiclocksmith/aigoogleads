"use client";

import { useState, useRef, useEffect } from "react";
import { HelpCircle } from "lucide-react";

/**
 * Centralized glossary — every ad-related term a beginner might need.
 * Keys are lowercase slugs used in code; values have a short label + plain-English definition.
 */
export const GLOSSARY: Record<string, { label: string; tip: string }> = {
  // ── Core metrics ──────────────────────────────────────────────────────
  impressions: {
    label: "Impressions",
    tip: "The number of times your ad was shown to someone. Think of it like how many people saw your ad on Google.",
  },
  clicks: {
    label: "Clicks",
    tip: "How many times someone clicked on your ad. Each click takes the person to your website or landing page.",
  },
  ctr: {
    label: "CTR (Click-Through Rate)",
    tip: "The percentage of people who clicked your ad after seeing it. Formula: Clicks ÷ Impressions × 100. Higher is better — it means your ad is relevant and compelling. A good CTR is typically 3-5%+.",
  },
  cpc: {
    label: "CPC (Cost Per Click)",
    tip: "How much you pay each time someone clicks your ad. Formula: Total Cost ÷ Clicks. Lower is better — it means you're getting cheaper traffic. Typical range: $1-$10 depending on industry.",
  },
  cost: {
    label: "Cost / Spend",
    tip: "The total amount of money you've spent on ads. This is what Google charges you. Your goal is to spend less while getting more results.",
  },
  conversions: {
    label: "Conversions",
    tip: "The number of valuable actions people took after clicking your ad — like calling your business, filling out a form, or making a purchase. This is the most important metric.",
  },
  cpa: {
    label: "CPA (Cost Per Acquisition)",
    tip: "How much you pay for each conversion (customer action). Formula: Total Cost ÷ Conversions. Lower is better — it means each new customer costs you less. Example: If you spend $100 and get 5 calls, your CPA is $20/call.",
  },
  roas: {
    label: "ROAS (Return on Ad Spend)",
    tip: "How much revenue you earn for every $1 spent on ads. Formula: Revenue ÷ Cost. A ROAS of 5x means you earn $5 for every $1 spent. Higher is better — anything above 3x is generally good.",
  },
  revenue: {
    label: "Revenue",
    tip: "The total money earned from conversions driven by your ads. This is the value of the business your ads are generating.",
  },
  conv_rate: {
    label: "Conv. Rate (Conversion Rate)",
    tip: "The percentage of clicks that turned into conversions. Formula: Conversions ÷ Clicks × 100. Higher is better — it means your landing page is effective at turning visitors into customers.",
  },
  quality_score: {
    label: "QS (Quality Score)",
    tip: "Google's 1-10 rating of your keyword + ad + landing page quality. Higher scores (7-10) mean lower costs and better ad positions. Improve it by making your ads more relevant to what people search for.",
  },

  // ── Campaign concepts ─────────────────────────────────────────────────
  campaign: {
    label: "Campaign",
    tip: "A campaign is a group of ads that share a budget and targeting settings. Think of it like a folder that organizes your ads. Example: 'Emergency Locksmith Ads' or 'Key Cutting Services'.",
  },
  ad_group: {
    label: "Ad Group",
    tip: "A sub-group within a campaign that contains a set of related ads and keywords. Example: Within a 'Locksmith' campaign, you might have ad groups for 'Car Lockout', 'Home Lockout', and 'Lock Change'.",
  },
  budget: {
    label: "Budget",
    tip: "The maximum daily amount you're willing to spend on a campaign. Google will try not to exceed this on average. Example: A $50/day budget means ~$1,500/month.",
  },
  bidding_strategy: {
    label: "Bidding Strategy",
    tip: "How Google decides how much to bid for your ad. 'Maximize Conversions' lets Google auto-bid to get the most customer actions. 'Manual CPC' lets you set exact bid amounts yourself.",
  },

  // ── Keyword concepts ──────────────────────────────────────────────────
  keyword: {
    label: "Keyword",
    tip: "A word or phrase you choose that tells Google when to show your ad. Example: If your keyword is 'locksmith near me', your ad shows when someone searches that phrase.",
  },
  match_type: {
    label: "Match Type",
    tip: "Controls how closely a search must match your keyword. 'Exact' = only that phrase. 'Phrase' = includes that phrase. 'Broad' = related searches too. Broad gets more traffic but less precise.",
  },
  match_broad: {
    label: "Broad Match",
    tip: "Your ad shows for searches related to your keyword, including synonyms, misspellings, and related topics. Example: keyword 'locksmith' could match 'key maker near me'. Gets the most traffic but least precise. Best for: discovery and reaching new customers. Recommended for campaigns using Smart Bidding.",
  },
  match_phrase: {
    label: "Phrase Match",
    tip: "Your ad shows when someone searches for your keyword phrase or close variations of it, in the same order. Example: keyword 'car locksmith' matches 'car locksmith near me' but NOT 'locksmith for house'. Best for: balanced reach with moderate control. Recommended for most campaigns.",
  },
  match_exact: {
    label: "Exact Match",
    tip: "Your ad shows only when someone searches for your exact keyword or very close variations (same meaning). Example: keyword [car locksmith] matches 'car locksmith' and 'auto locksmith' but NOT 'car locksmith reviews'. Best for: tight control and highest relevance. Recommended for high-value keywords where you want precision.",
  },
  negative_keyword: {
    label: "Negative Keyword",
    tip: "A word or phrase that PREVENTS your ad from showing. Example: Adding 'free' as a negative keyword means your ad won't show for 'free locksmith'. This saves money by blocking irrelevant searches.",
  },
  search_term: {
    label: "Search Term",
    tip: "The actual words someone typed into Google that triggered your ad. This can be different from your keyword. Reviewing search terms helps you find irrelevant searches that waste money.",
  },

  // ── Ad concepts ───────────────────────────────────────────────────────
  headline: {
    label: "Headline",
    tip: "The bold, clickable title of your ad. Google Ads allows up to 15 headlines (30 characters each). Google mixes and matches them to find the best combination.",
  },
  description: {
    label: "Description",
    tip: "The body text of your ad that appears below the headline. Up to 4 descriptions (90 characters each). Use this to explain your offer and include a call to action.",
  },
  final_url: {
    label: "Final URL",
    tip: "The web page people land on after clicking your ad. This should be a relevant page on your website — not just your homepage. A good landing page = more conversions.",
  },
  ad_status: {
    label: "Ad Status",
    tip: "Whether your ad is currently active. 'Enabled' = running and showing. 'Paused' = stopped, not spending money. You can pause ads anytime without deleting them.",
  },

  // ── Landing page metrics ──────────────────────────────────────────────
  landing_page: {
    label: "Landing Page",
    tip: "The web page people see after clicking your ad. A fast, mobile-friendly page with clear calls-to-action gets more conversions and lowers your costs.",
  },
  page_speed: {
    label: "Page Speed Score",
    tip: "Google's 0-100 rating of how fast your page loads. 90+ is great, 50-89 needs improvement, below 50 is poor. Slow pages lose customers — 53% of visitors leave if a page takes more than 3 seconds.",
  },
  mobile_friendly: {
    label: "Mobile Friendly",
    tip: "Whether your landing page works well on phones. Over 60% of Google searches happen on mobile, so a mobile-friendly page is essential for good results.",
  },

  // ── Competitor metrics ────────────────────────────────────────────────
  impression_share: {
    label: "Impression Share",
    tip: "The percentage of times your ad was shown out of all the times it could have been shown. 100% means you appeared for every relevant search. Lower means competitors are getting some of your potential views.",
  },
  overlap_rate: {
    label: "Overlap Rate",
    tip: "How often a competitor's ad showed at the same time as yours. High overlap means you're directly competing with them for the same customers.",
  },
  outranking_share: {
    label: "Outranking Share",
    tip: "How often your ad ranked higher than a competitor's, or showed when theirs didn't. Higher is better — it means you're beating them.",
  },
  top_of_page_rate: {
    label: "Top of Page Rate",
    tip: "How often your ad appeared at the very top of Google search results (above all other results). Being at the top gets the most clicks.",
  },

  // ── Optimization concepts ─────────────────────────────────────────────
  wasted_spend: {
    label: "Wasted Spend",
    tip: "Money spent on clicks that never converted into customers. This includes spend on irrelevant search terms, poor-performing keywords, and low-quality ads. Reducing waste = more profit.",
  },
  recommendation: {
    label: "Google Recommendation",
    tip: "Suggestions from Google on how to improve your ads. These can include adding new keywords, adjusting bids, or trying new ad formats. Not all recommendations are good — review carefully.",
  },
  optimization_score: {
    label: "Optimization Score",
    tip: "Google's 0-100% estimate of how well your account is set up. Don't blindly chase 100% — some Google recommendations increase your spending without proportional results.",
  },

  // ── AI features ───────────────────────────────────────────────────────
  ai_operator: {
    label: "AI Operator",
    tip: "Our AI that scans your entire Google Ads account, finds problems, and recommends specific fixes with projected savings. Think of it as a virtual ads expert reviewing your account.",
  },
  auto_optimizer: {
    label: "Auto Optimizer",
    tip: "An AI system that automatically monitors and improves your ads every 4 hours. In Semi-Auto mode, it only makes safe, low-risk changes. You can review everything it does.",
  },
  autonomy_mode: {
    label: "Autonomy Mode",
    tip: "Controls how much the AI can do on its own. 'Suggest Only' = AI recommends but you decide. 'Semi-Auto' = AI auto-applies safe changes. 'Full Auto' = AI handles most optimizations.",
  },
  risk_level: {
    label: "Risk Level",
    tip: "How risky a proposed change is. 'Low' = very safe (e.g., pausing a zero-conversion keyword). 'Medium' = moderate impact. 'High' = significant changes that need your approval.",
  },

  // ── Page descriptions ─────────────────────────────────────────────────
  page_dashboard: {
    label: "Dashboard",
    tip: "Your main overview showing how your ads are performing — how much you're spending, how many customers you're getting, and whether you're making money.",
  },
  page_campaigns: {
    label: "Campaigns",
    tip: "View and manage all your ad campaigns. Each campaign has its own budget and settings. You can pause, enable, or drill into any campaign.",
  },
  page_keywords: {
    label: "Keywords",
    tip: "The search terms you're bidding on. This page shows which keywords are making you money and which ones are wasting it. Focus on high-converting keywords.",
  },
  page_search_terms: {
    label: "Search Terms",
    tip: "See the ACTUAL words people typed into Google that triggered your ads. Use this to find irrelevant searches and add them as negative keywords to stop wasting money.",
  },
  page_ads: {
    label: "Ads",
    tip: "All your individual ads and how they're performing. Compare ads to find your winners (high conversions) and losers (high spend, no results) — then pause the losers.",
  },
  page_landing_pages: {
    label: "Landing Pages",
    tip: "Shows the web pages people land on after clicking your ads, with speed scores and conversion rates. Fast, relevant landing pages = more customers and lower costs.",
  },
  page_competitors: {
    label: "Competitors (Auction Insights)",
    tip: "See who you're competing against in Google Ads auctions. Shows how often you beat them and how often they beat you.",
  },
  page_recommendations: {
    label: "Recommendations",
    tip: "Suggestions from Google on how to improve your account. Review each one carefully — apply the ones that make sense and dismiss the rest.",
  },
};

interface HelpTipProps {
  term: string;
  showLabel?: boolean;
  size?: "sm" | "md";
  className?: string;
}

/**
 * Hover/click tooltip that shows a plain-English definition.
 * Usage: <HelpTip term="ctr" />  or  <HelpTip term="cpa" showLabel />
 */
export function HelpTip({ term, showLabel = false, size = "sm", className = "" }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<"above" | "below">("above");
  const ref = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const entry = GLOSSARY[term];
  if (!entry) return null;

  const iconSize = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";

  // Position tooltip above or below depending on available space
  useEffect(() => {
    if (open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setPosition(rect.top < 200 ? "below" : "above");
    }
  }, [open]);

  return (
    <span
      ref={ref}
      className={`relative inline-flex items-center ${className}`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
    >
      {showLabel && <span className="mr-1">{entry.label}</span>}
      <HelpCircle className={`${iconSize} text-slate-300 hover:text-blue-500 cursor-help transition-colors`} />
      {open && (
        <div
          ref={tooltipRef}
          className={`absolute z-50 w-72 px-4 py-3 rounded-xl bg-slate-900 text-white text-[12px] leading-relaxed shadow-xl
            ${position === "above" ? "bottom-full mb-2" : "top-full mt-2"} left-1/2 -translate-x-1/2`}
        >
          <p className="font-semibold text-blue-300 text-[11px] uppercase tracking-wider mb-1">{entry.label}</p>
          <p className="text-white/90">{entry.tip}</p>
          <div className={`absolute left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 rotate-45
            ${position === "above" ? "-bottom-1" : "-top-1"}`} />
        </div>
      )}
    </span>
  );
}

/**
 * Inline info banner for page-level descriptions.
 * Usage: <PageInfo term="page_dashboard" />
 */
export function PageInfo({ term, className = "" }: { term: string; className?: string }) {
  const [dismissed, setDismissed] = useState(false);
  const entry = GLOSSARY[term];
  if (!entry || dismissed) return null;

  return (
    <div className={`flex items-start gap-3 px-4 py-3 rounded-xl bg-blue-50/70 border border-blue-100/50 ${className}`}>
      <HelpCircle className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        <p className="text-[13px] text-blue-700 leading-relaxed">{entry.tip}</p>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="text-blue-300 hover:text-blue-500 text-[11px] flex-shrink-0"
      >
        ✕
      </button>
    </div>
  );
}
