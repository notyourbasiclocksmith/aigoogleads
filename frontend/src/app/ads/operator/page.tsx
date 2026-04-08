"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Send, Bot, User, AlertTriangle, CheckCircle, XCircle,
  Loader2, Zap, Search, TrendingDown, PlusCircle, Ban,
  DollarSign, BarChart3, Wrench, ChevronDown, ChevronUp,
  Sparkles, Shield, Clock, Globe, Image as ImageIcon, Star, MessageSquare,
  StopCircle, PanelLeftOpen, PanelLeftClose, Pencil, Trash2, Plus, Check, X, ExternalLink,
} from "lucide-react";

// ── Types ───────────────────────────────────────────────────

interface Finding {
  system?: string;
  type: string;
  title: string;
  description: string;
  severity: string;
  data?: any[];
}

interface ProposedAction {
  id: string;
  system?: string;
  action_type: string;
  label: string;
  reasoning: string;
  expected_impact: string;
  risk_level: string;
  status: string;
  action_payload: any;
}

interface ConnectedSystem {
  name: string;
  connected: boolean;
  error?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  structured_payload?: {
    type?: string;
    summary?: string;
    findings?: Finding[];
    recommended_actions?: ProposedAction[];
    questions?: string[];
    next_steps?: string[];
    message?: string;
    results?: any[];
    succeeded?: number;
    failed?: number;
    _systems_used?: string[];
    _system_errors?: Record<string, string>;
    // Pipeline progress fields
    agent?: string;
    status?: string;
    detail?: string;
  };
  proposed_actions?: ProposedAction[];
  created_at: string;
}

interface ConversationSession {
  conversation_id: string;
  title: string;
  mode: OperatorMode;
  created_at: string;
  updated_at: string;
  actions_executed: number;
  actions_failed: number;
  actions_total: number;
}

// ── Channel Config ──────────────────────────────────────────

type OperatorMode = "auto" | "google_ads" | "meta_ads" | "gbp" | "image";

interface ModeConfig {
  label: string;
  icon: any;
  color: string;
  gradient: string;
  description: string;
}

const MODE_CONFIG: Record<OperatorMode, ModeConfig> = {
  auto: {
    label: "Auto",
    icon: Sparkles,
    color: "text-violet-400",
    gradient: "from-violet-500 to-fuchsia-600",
    description: "AI automatically routes your request to the right systems. Ask anything about your marketing.",
  },
  google_ads: {
    label: "Google Ads",
    icon: Search,
    color: "text-blue-400",
    gradient: "from-blue-500 to-violet-600",
    description: "Audit campaigns, find wasted spend, build new campaigns, and apply fixes through chat.",
  },
  meta_ads: {
    label: "Meta Ads",
    icon: Globe,
    color: "text-pink-400",
    gradient: "from-blue-500 to-pink-600",
    description: "Manage Facebook & Instagram campaigns, audit spend, create ads, and optimize creatives.",
  },
  gbp: {
    label: "GBP",
    icon: Star,
    color: "text-amber-400",
    gradient: "from-amber-500 to-orange-600",
    description: "Manage Google Business Profile — reply to reviews, create posts, monitor local presence.",
  },
  image: {
    label: "Image",
    icon: ImageIcon,
    color: "text-emerald-400",
    gradient: "from-emerald-500 to-teal-600",
    description: "Generate AI images for ads, social posts, and marketing materials.",
  },
};

// ── Quick Prompts per Mode ──────────────────────────────────

const QUICK_PROMPTS: Record<OperatorMode, { icon: any; label: string; prompt: string }[]> = {
  auto: [
    { icon: Search, label: "Audit my marketing", prompt: "Audit my marketing across all channels and tell me the top issues to fix" },
    { icon: TrendingDown, label: "Where am I wasting money?", prompt: "Where am I wasting money across Google Ads and Meta Ads?" },
    { icon: PlusCircle, label: "Create spring promo", prompt: "Help me create a spring promotion across all channels — Google Ads campaign, Meta Ads campaign, GBP post, and promotional image" },
    { icon: Star, label: "Review management", prompt: "Show me unanswered Google Business reviews and draft AI replies" },
    { icon: BarChart3, label: "Cross-channel performance", prompt: "Compare performance across Google Ads and Meta Ads — which channel is giving me better ROI?" },
    { icon: Sparkles, label: "What should I do this week?", prompt: "What should I do this week to improve my marketing? Prioritize by impact." },
  ],
  google_ads: [
    { icon: Search, label: "Audit my account", prompt: "Audit my campaigns and tell me the top 5 things I should fix" },
    { icon: TrendingDown, label: "Find wasted spend", prompt: "Show me keywords and search terms wasting money with no conversions in the last 30 days" },
    { icon: Ban, label: "Add negative keywords", prompt: "Find search terms I should add as negative keywords to stop wasting money" },
    { icon: DollarSign, label: "Fix budgets", prompt: "Which campaigns need more budget and which are overspending?" },
    { icon: BarChart3, label: "Improve low CTR", prompt: "Find my lowest CTR ads and tell me how to fix them" },
    { icon: PlusCircle, label: "Create campaign", prompt: "Help me create a new search campaign" },
  ],
  meta_ads: [
    { icon: Search, label: "Audit account", prompt: "Audit my Meta Ads account — show health score, top issues, and fix recommendations" },
    { icon: TrendingDown, label: "Find wasted spend", prompt: "Which campaigns have high spend but low conversions in the last 30 days?" },
    { icon: BarChart3, label: "Performance summary", prompt: "Give me a performance summary of all my active campaigns" },
    { icon: DollarSign, label: "Fix budgets", prompt: "Which campaigns need more budget and which are overspending?" },
    { icon: PlusCircle, label: "Create campaign", prompt: "Help me create a new Meta Ads campaign for lead generation" },
    { icon: Wrench, label: "Refresh creatives", prompt: "Which ads have creative fatigue and need new creatives?" },
  ],
  gbp: [
    { icon: Star, label: "Unanswered reviews", prompt: "Show me all unanswered reviews and draft professional replies" },
    { icon: MessageSquare, label: "Reply to all reviews", prompt: "Generate AI replies for all my unanswered reviews" },
    { icon: PlusCircle, label: "Create a post", prompt: "Generate a professional Google Business post about our services this week" },
    { icon: BarChart3, label: "Review summary", prompt: "Summarize my review sentiment — what do customers love and complain about?" },
    { icon: Search, label: "Local presence audit", prompt: "Audit my Google Business Profile and tell me what to improve" },
    { icon: Sparkles, label: "AI post with image", prompt: "Create an engaging GBP post with an AI-generated image" },
  ],
  image: [
    { icon: ImageIcon, label: "Ad image", prompt: "Generate a professional ad image for my business" },
    { icon: Globe, label: "Social media image", prompt: "Create an eye-catching Instagram post image for my business" },
    { icon: PlusCircle, label: "Facebook cover", prompt: "Generate a Facebook-sized promotional image for my business" },
    { icon: Sparkles, label: "Promo banner", prompt: "Create a promotional banner image for a seasonal sale" },
    { icon: Star, label: "Google Ads image", prompt: "Generate a Google Ads display image for my services" },
    { icon: Wrench, label: "Custom image", prompt: "Generate a custom marketing image with specific requirements" },
  ],
};

// ── System Label Helpers ────────────────────────────────────

const SYSTEM_LABELS: Record<string, { label: string; color: string }> = {
  google_ads: { label: "Google Ads", color: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  meta_ads: { label: "Meta Ads", color: "bg-pink-500/20 text-pink-400 border-pink-500/30" },
  gbp: { label: "GBP", color: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  image: { label: "Image", color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  general: { label: "General", color: "bg-white/10 text-white/60 border-white/20" },
};

function SystemBadge({ system }: { system?: string }) {
  if (!system) return null;
  const cfg = SYSTEM_LABELS[system] || SYSTEM_LABELS.general;
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold border ${cfg.color}`}>
      {cfg.label}
    </span>
  );
}

// ── Helper Components ───────────────────────────────────────

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    high: "bg-red-500/20 text-red-400 border-red-500/30",
    medium: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    low: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${colors[severity] || colors.medium}`}>
      {severity.toUpperCase()}
    </span>
  );
}

function RiskBadge({ risk }: { risk: string }) {
  const colors: Record<string, string> = {
    high: "bg-red-500/10 text-red-400",
    medium: "bg-amber-500/10 text-amber-400",
    low: "bg-emerald-500/10 text-emerald-400",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${colors[risk] || colors.medium}`}>
      <Shield className="w-3 h-3" /> {risk} risk
    </span>
  );
}

function SystemsUsedPills({ systems }: { systems?: string[] }) {
  if (!systems?.length) return null;
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <span className="text-[10px] text-white/30">Queried:</span>
      {systems.map(s => <SystemBadge key={s} system={s} />)}
    </div>
  );
}

function FindingsCard({ findings }: { findings: Finding[] }) {
  if (!findings?.length) return null;
  return (
    <div className="space-y-2 mt-3">
      <div className="text-xs font-semibold text-white/50 uppercase tracking-wider">Findings</div>
      {findings.map((f, i) => (
        <div key={i} className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex items-start justify-between gap-2 mb-1">
            <div className="flex items-center gap-2">
              <SystemBadge system={f.system} />
              <span className="text-sm font-semibold text-white/90">{f.title}</span>
            </div>
            <SeverityBadge severity={f.severity} />
          </div>
          <p className="text-xs text-white/50 leading-relaxed">{f.description}</p>
        </div>
      ))}
    </div>
  );
}

function ActionsCard({
  actions,
  onApprove,
  onReject,
  approving,
}: {
  actions: ProposedAction[];
  onApprove: (ids: string[]) => void;
  onReject: (ids: string[]) => void;
  approving: boolean;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  if (!actions?.length) return null;

  const pendingActions = actions.filter(a => a.status === "proposed");
  const allIds = pendingActions.map(a => a.id);

  return (
    <div className="space-y-2 mt-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-white/50 uppercase tracking-wider">
          Recommended Actions ({actions.length})
        </div>
        {pendingActions.length > 1 && (
          <Button
            size="sm"
            onClick={() => onApprove(allIds)}
            disabled={approving}
            className="h-7 px-3 text-xs bg-emerald-600 hover:bg-emerald-500"
          >
            {approving ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <CheckCircle className="w-3 h-3 mr-1" />}
            Approve All
          </Button>
        )}
      </div>
      {actions.map((a, i) => (
        <div key={a.id} className="rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden">
          <div className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <SystemBadge system={a.system} />
                  <span className="text-sm font-semibold text-white/90">{a.label}</span>
                  <RiskBadge risk={a.risk_level} />
                  {a.status !== "proposed" && (
                    <Badge variant={a.status === "executed" ? "default" : "destructive"} className="text-[10px]">
                      {a.status}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-white/40">{a.expected_impact}</p>
              </div>
              {a.status === "proposed" && (
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <Button
                    size="sm"
                    onClick={() => onApprove([a.id])}
                    disabled={approving}
                    className="h-7 px-3 text-xs bg-emerald-600 hover:bg-emerald-500"
                  >
                    {approving ? <Loader2 className="w-3 h-3 animate-spin" /> : "Approve"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onReject([a.id])}
                    className="h-7 px-3 text-xs text-red-400 hover:bg-red-500/10"
                  >
                    Reject
                  </Button>
                </div>
              )}
            </div>

            <button
              onClick={() => {
                const next = new Set(expanded);
                next.has(i) ? next.delete(i) : next.add(i);
                setExpanded(next);
              }}
              className="flex items-center gap-1 mt-2 text-[10px] text-white/30 hover:text-white/50 transition-colors"
            >
              {expanded.has(i) ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {expanded.has(i) ? "Hide details" : "Show details"}
            </button>
          </div>

          {expanded.has(i) && (
            <div className="border-t border-white/5 px-4 py-3 bg-white/[0.01]">
              <div className="text-xs text-white/40 leading-relaxed">
                <strong className="text-white/60">Reasoning:</strong> {a.reasoning}
              </div>
              {a.action_payload && (
                <pre className="mt-2 text-[10px] text-white/25 bg-black/20 rounded-lg p-2 overflow-x-auto">
                  {JSON.stringify(a.action_payload, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ExecutionResultCard({ payload }: { payload: any }) {
  if (payload?.type !== "execution_result") return null;
  const { results = [], succeeded = 0, failed = 0 } = payload;
  return (
    <div className="space-y-2 mt-3">
      <div className="text-xs font-semibold text-white/50 uppercase tracking-wider">Execution Results</div>
      <div className="flex gap-3 mb-2">
        {succeeded > 0 && (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <CheckCircle className="w-3.5 h-3.5" /> {succeeded} succeeded
          </span>
        )}
        {failed > 0 && (
          <span className="flex items-center gap-1 text-xs text-red-400">
            <XCircle className="w-3.5 h-3.5" /> {failed} failed
          </span>
        )}
      </div>
      {results.map((r: any, i: number) => (
        <div key={i} className={`rounded-lg border p-3 text-xs ${
          r.status === "success"
            ? "border-emerald-500/20 bg-emerald-500/5"
            : "border-red-500/20 bg-red-500/5"
        }`}>
          <div className="flex items-center gap-2">
            {r.status === "success" ? (
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-red-400" />
            )}
            <SystemBadge system={r.system} />
            <span className="font-semibold text-white/80">{r.label || r.action_type}</span>
          </div>
          {r.summary && <p className="mt-1 text-white/50">{r.summary}</p>}
          {r.error && <p className="mt-1 text-red-400/60">{r.error}</p>}
        </div>
      ))}
    </div>
  );
}

// ── Audit Result Card ──────────────────────────────────────

function AuditResultCard({ payload, onApprove, approving }: {
  payload: any;
  onApprove: (ids: string[]) => void;
  approving: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (payload?.type !== "audit_result") return null;

  const { status, score, issues = [], metrics = {}, fix_count = 0 } = payload;
  const passed = status === "valid";
  const critical = issues.filter((i: any) => i.severity === "critical");
  const warnings = issues.filter((i: any) => i.severity === "warning");

  return (
    <div className={`rounded-xl border p-4 mt-3 ${
      passed
        ? "border-emerald-500/20 bg-emerald-500/5"
        : "border-amber-500/20 bg-amber-500/5"
    }`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {passed ? (
            <CheckCircle className="w-4 h-4 text-emerald-400" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          )}
          <span className="text-xs font-semibold uppercase tracking-wider text-white/60">
            Post-Deployment Audit
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold ${
            score >= 90 ? "text-emerald-400" : score >= 70 ? "text-amber-400" : "text-red-400"
          }`}>
            {score}/100
          </span>
        </div>
      </div>

      {/* Summary stats */}
      <div className="flex gap-4 text-[10px] text-white/40 mb-2">
        {metrics.actual_ad_groups != null && (
          <span>Ad Groups: {metrics.actual_ad_groups}/{metrics.intended_ad_groups}</span>
        )}
        {metrics.actual_keywords != null && (
          <span>Keywords: {metrics.actual_keywords}/{metrics.intended_keywords}</span>
        )}
        {metrics.extensions_attached != null && (
          <span>Extensions: {metrics.extensions_attached ? "Attached" : "Missing"}</span>
        )}
      </div>

      {issues.length > 0 && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-white/30 hover:text-white/50 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {critical.length} critical, {warnings.length} warnings
          </button>

          {expanded && (
            <div className="mt-2 space-y-1.5">
              {issues.map((issue: any, i: number) => (
                <div key={i} className={`rounded-lg border p-2 text-[10px] ${
                  issue.severity === "critical"
                    ? "border-red-500/20 bg-red-500/5"
                    : issue.severity === "warning"
                      ? "border-amber-500/20 bg-amber-500/5"
                      : "border-white/5 bg-white/[0.02]"
                }`}>
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className={`font-semibold uppercase ${
                      issue.severity === "critical" ? "text-red-400" : issue.severity === "warning" ? "text-amber-400" : "text-white/40"
                    }`}>
                      {issue.severity}
                    </span>
                    <span className="text-white/20">|</span>
                    <span className="text-white/50">{issue.category?.replace(/_/g, " ")}</span>
                  </div>
                  <p className="text-white/60">{issue.description}</p>
                  {issue.intended && (
                    <p className="text-white/25 mt-0.5">Expected: {issue.intended}</p>
                  )}
                  {issue.actual && (
                    <p className="text-white/25">Got: {issue.actual}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {passed && issues.length === 0 && (
        <p className="text-xs text-emerald-400/70">Campaign deployed correctly — all entities match intended spec.</p>
      )}
    </div>
  );
}

// ── Audit Progress (stepper entry) ─────────────────────────

function AuditProgressCard({ messages: auditMsgs }: { messages: Message[] }) {
  if (auditMsgs.length === 0) return null;

  // Show latest status
  const latest = auditMsgs[auditMsgs.length - 1];
  const sp = latest.structured_payload as any;

  return (
    <div className="flex items-start gap-2.5 text-xs mt-2">
      {sp?.status === "running" ? (
        <Loader2 className="w-4 h-4 animate-spin text-blue-400 flex-shrink-0 mt-0.5" />
      ) : (
        <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
      )}
      <div>
        <span className={sp?.status === "running" ? "text-white/70 font-medium" : "text-white/50"}>
          Post-Deployment Audit
        </span>
        <p className="text-white/30 text-[10px] leading-tight mt-0.5">{sp?.detail}</p>
      </div>
    </div>
  );
}

// ── Pipeline Progress Card ──────────────────────────────────

const PIPELINE_AGENTS = [
  "Strategist", "Keyword Research", "Targeting", "Extensions", "Ad Copy",
  "Asset Groups", "Call Tracking", "Landing Pages", "Quality Assurance", "Campaign Summary",
];

function PipelineProgressCard({ messages: pipelineMsgs }: { messages: Message[] }) {
  // Collect latest status per agent from pipeline progress messages
  const agentStatus: Record<string, { status: string; detail: string }> = {};
  let campaignSummary: any = null;
  for (const m of pipelineMsgs) {
    const sp = m.structured_payload as any;
    if (sp?.type === "pipeline_progress" && sp.agent) {
      agentStatus[sp.agent] = { status: sp.status, detail: sp.detail };
    }
    if (sp?.type === "campaign_summary") {
      campaignSummary = sp;
    }
  }

  if (Object.keys(agentStatus).length === 0) return null;

  return (
    <div className="space-y-3 mt-3">
      <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-violet-400" />
          <span className="text-xs font-semibold text-violet-300 uppercase tracking-wider">Campaign Builder Pipeline</span>
        </div>
        <div className="space-y-2">
          {PIPELINE_AGENTS.map((agent) => {
            const st = agentStatus[agent];
            if (!st) return (
              <div key={agent} className="flex items-center gap-2.5 text-xs text-white/20">
                <div className="w-4 h-4 rounded-full border border-white/10 flex-shrink-0" />
                <span>{agent}</span>
              </div>
            );
            return (
              <div key={agent} className="flex items-start gap-2.5 text-xs">
                {st.status === "running" ? (
                  <Loader2 className="w-4 h-4 animate-spin text-blue-400 flex-shrink-0 mt-0.5" />
                ) : st.status === "error" ? (
                  <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <span className={st.status === "running" ? "text-white/70 font-medium" : st.status === "error" ? "text-red-400" : "text-white/50"}>
                    {agent}
                  </span>
                  <p className="text-white/30 text-[10px] leading-tight mt-0.5">{st.detail}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {campaignSummary && <CampaignSummaryCard summary={campaignSummary} />}
    </div>
  );
}

function CampaignSummaryCard({ summary }: { summary: any }) {
  const [expanded, setExpanded] = useState(true);
  const s = summary;
  if (!s?.campaign_name) return null;

  const StatBox = ({ label, value, sub }: { label: string; value: string | number; sub?: string }) => (
    <div className="bg-white/[0.04] rounded-lg px-3 py-2">
      <p className="text-[10px] text-white/40 uppercase tracking-wide">{label}</p>
      <p className="text-sm font-semibold text-white/90 mt-0.5">{value}</p>
      {sub && <p className="text-[10px] text-white/30 mt-0.5">{sub}</p>}
    </div>
  );

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 overflow-hidden">
      <button onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors">
        <div className="flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-bold text-emerald-300">{s.campaign_name}</span>
          {s.qa_score && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
              s.qa_score >= 80 ? "bg-emerald-500/20 text-emerald-300" :
              s.qa_score >= 60 ? "bg-yellow-500/20 text-yellow-300" :
              "bg-red-500/20 text-red-300"
            }`}>QA {s.qa_score}/100 ({s.qa_grade})</span>
          )}
        </div>
        <ChevronDown className={`w-3.5 h-3.5 text-white/30 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Campaign Settings */}
          <div className="grid grid-cols-3 gap-2">
            <StatBox label="Budget" value={`$${s.budget_daily?.toFixed(0) || 0}/day`} sub={`$${s.budget_monthly?.toFixed(0) || 0}/mo`} />
            <StatBox label="Type" value={s.campaign_type || "SEARCH"} sub={s.bidding_strategy?.replace(/_/g, " ")} />
            <StatBox label="Status" value="PAUSED" sub="Enable when ready" />
          </div>

          {/* Keywords & Copy */}
          <div className="grid grid-cols-4 gap-2">
            <StatBox label="Keywords" value={s.total_keywords || 0} sub={`${s.total_negatives || 0} negatives`} />
            <StatBox label="Headlines" value={s.total_headlines || 0} sub="Per RSA ad" />
            <StatBox label="Descriptions" value={s.total_descriptions || 0} sub="Per RSA ad" />
            <StatBox label="KW Match" value={`${s.keyword_headline_match || 0}%`} sub="Ad relevance" />
          </div>

          {/* Ad Groups (Search/Call campaigns) */}
          {s.ad_groups?.length > 0 && (
            <div>
              <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1.5">Ad Groups ({s.ad_groups.length})</p>
              <div className="space-y-1.5">
                {s.ad_groups.map((ag: any, i: number) => (
                  <div key={i} className="bg-white/[0.03] rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-white/70">{ag.name}</span>
                      <span className="text-[10px] text-white/30">{ag.keywords} kws • {ag.headlines} h • {ag.descriptions} d</span>
                    </div>
                    {ag.top_keywords?.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {ag.top_keywords.slice(0, 4).map((kw: string, j: number) => (
                          <span key={j} className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300/70">{kw}</span>
                        ))}
                      </div>
                    )}
                    {ag.final_url && (
                      <p className="text-[9px] text-white/20 mt-1 truncate">→ {ag.final_url}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* PMax Asset Groups */}
          {s.campaign_type === "PERFORMANCE_MAX" && s.asset_groups?.length > 0 && (
            <div>
              <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1.5">
                <span className="text-violet-400">⚡</span> Asset Groups ({s.asset_groups.length}) — Performance Max
              </p>
              <div className="space-y-1.5">
                {s.asset_groups.map((ag: any, i: number) => (
                  <div key={i} className="bg-gradient-to-r from-violet-500/5 to-blue-500/5 border border-violet-500/10 rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-white/70">{ag.name}</span>
                      <span className="text-[10px] text-white/30">
                        {ag.headlines?.length || 0}h • {ag.long_headlines?.length || 0}lh • {ag.descriptions?.length || 0}d
                      </span>
                    </div>
                    {ag.search_themes?.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {ag.search_themes.slice(0, 4).map((theme: string, j: number) => (
                          <span key={j} className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300/70">{theme}</span>
                        ))}
                        {ag.search_themes.length > 4 && (
                          <span className="text-[9px] text-white/20">+{ag.search_themes.length - 4} more</span>
                        )}
                      </div>
                    )}
                    {ag.final_url && (
                      <p className="text-[9px] text-white/20 mt-1 truncate">→ {ag.final_url}</p>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-[9px] text-white/20 mt-1.5">PMax shows ads across Search, Display, YouTube, Maps, Gmail, and Discover</p>
            </div>
          )}

          {/* Targeting & Extensions */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-white/[0.04] rounded-lg px-3 py-2">
              <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1">Targeting</p>
              {s.geo && <p className="text-[10px] text-white/60">📍 {s.geo}</p>}
              {s.mobile_bid_adj !== undefined && <p className="text-[10px] text-white/60">📱 Mobile: {s.mobile_bid_adj > 0 ? "+" : ""}{s.mobile_bid_adj}%</p>}
              {s.schedule && <p className="text-[10px] text-white/60">⏰ {s.schedule}</p>}
            </div>
            <div className="bg-white/[0.04] rounded-lg px-3 py-2">
              <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1">Extensions</p>
              <p className="text-[10px] text-white/60">🔗 {s.sitelinks || 0} sitelinks</p>
              <p className="text-[10px] text-white/60">💬 {s.callouts || 0} callouts</p>
              {s.has_snippets && <p className="text-[10px] text-white/60">📋 Structured snippets</p>}
              {s.call_extension && <p className="text-[10px] text-white/60">📞 {s.call_extension}</p>}
            </div>
          </div>

          {/* Call Tracking */}
          {s.tracking_number && (
            <div className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/10 rounded-lg px-3 py-2">
              <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1">Call Tracking (CallFlux)</p>
              <p className="text-xs font-semibold text-green-400">{s.tracking_number}</p>
              <p className="text-[9px] text-white/30 mt-0.5">Forwards to: {s.forward_to}</p>
              <p className="text-[9px] text-white/30">Recording + AI transcription + GCLID attribution</p>
            </div>
          )}

          {/* Landing Pages */}
          {(s.landing_pages_generated > 0 || s.landing_pages_existing > 0) && (
            <div className="bg-white/[0.04] rounded-lg px-3 py-2">
              <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1">Landing Pages</p>
              {s.landing_pages_existing > 0 && <p className="text-[10px] text-white/60">✅ {s.landing_pages_existing} existing pages linked</p>}
              {s.landing_pages_generated > 0 && <p className="text-[10px] text-white/60">🆕 {s.landing_pages_generated} AI pages generated</p>}
            </div>
          )}

          {/* Estimates */}
          <div className="bg-gradient-to-r from-violet-500/10 to-blue-500/10 border border-violet-500/10 rounded-lg px-3 py-2">
            <p className="text-[10px] text-white/40 uppercase tracking-wide mb-1">What to Expect (estimated)</p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-xs font-semibold text-white/80">{s.est_clicks_month || "?"}</p>
                <p className="text-[9px] text-white/30">clicks/month</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-white/80">{s.est_conversions_month || "?"}</p>
                <p className="text-[9px] text-white/30">conversions/month</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-white/80">{s.est_cpa || "?"}</p>
                <p className="text-[9px] text-white/30">est. CPA</p>
              </div>
            </div>
            <p className="text-[9px] text-white/20 mt-2">Campaign starts PAUSED • Google learning period: 1-2 weeks • Meaningful data after 7-14 days</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Image Generation Result Card ──────────────────────────

function ImageResultCard({ payload }: { payload: any }) {
  if (!payload || payload?.type !== "image_generation_result") return null;
  const images = payload.images || [];
  const successful = images.filter((img: any) => img.status === "success" && img.image_url);
  if (successful.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-violet-500/20 bg-violet-500/5 p-4">
      <div className="flex items-center gap-2 mb-3">
        <ImageIcon className="w-4 h-4 text-violet-400" />
        <span className="text-xs font-semibold text-violet-300 uppercase tracking-wider">
          Generated Images ({successful.length})
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {successful.map((img: any, i: number) => (
          <div key={i} className="group relative rounded-lg overflow-hidden border border-white/10 bg-black/30">
            <img
              src={img.image_url}
              alt={img.service || `Campaign image ${i + 1}`}
              className="w-full h-32 object-cover transition-transform group-hover:scale-105"
              loading="lazy"
            />
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
              <p className="text-[10px] text-white/80 truncate">{img.service || "Campaign Image"}</p>
            </div>
            <a
              href={img.image_url}
              target="_blank"
              rel="noopener noreferrer"
              className="absolute top-1.5 right-1.5 w-6 h-6 bg-black/60 rounded-md flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <ExternalLink className="w-3 h-3 text-white/70" />
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Campaign Detail View ───────────────────────────────────

function CampaignDetailCard({ payload }: { payload: any }) {
  const [showDetail, setShowDetail] = useState(false);

  if (!payload || payload.action_type !== "deploy_full_campaign") return null;
  const spec = payload.action_payload;
  if (!spec?.campaign) return null;

  const campaign = spec.campaign;
  const adGroups = spec.ad_groups || [];
  const sitelinks = spec.sitelinks || [];
  const callouts = spec.callouts || [];
  const snippets = spec.structured_snippets;
  const meta = spec._pipeline_metadata;

  return (
    <div className="mt-2">
      <button
        onClick={() => setShowDetail(!showDetail)}
        className="flex items-center gap-1.5 text-[10px] text-violet-400/70 hover:text-violet-400 transition-colors"
      >
        {showDetail ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {showDetail ? "Hide campaign details" : "View campaign details"}
      </button>

      {showDetail && (
        <div className="mt-3 space-y-3">
          {/* Campaign Overview */}
          <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
            <div className="text-xs font-semibold text-white/60 mb-2 uppercase tracking-wider">Campaign</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div><span className="text-white/30">Name:</span> <span className="text-white/80">{campaign.name}</span></div>
              <div><span className="text-white/30">Type:</span> <span className="text-white/80">{campaign.channel_type || campaign.bidding_strategy}</span></div>
              <div><span className="text-white/30">Budget:</span> <span className="text-emerald-400">${(campaign.budget_micros / 1_000_000).toFixed(0)}/day</span></div>
              <div><span className="text-white/30">Bidding:</span> <span className="text-white/80">{campaign.bidding_strategy?.replace(/_/g, " ")}</span></div>
              {meta?.qa_score != null && (
                <div>
                  <span className="text-white/30">QA Score:</span>{" "}
                  <span className={meta.qa_score >= 80 ? "text-emerald-400" : meta.qa_score >= 60 ? "text-amber-400" : "text-red-400"}>
                    {meta.qa_score}/100
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Ad Groups */}
          {adGroups.map((ag: any, i: number) => (
            <div key={i} className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
              <div className="text-xs font-semibold text-blue-400/80 mb-2">Ad Group: {ag.name}</div>

              {/* Keywords */}
              {ag.keywords?.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-white/30 mb-1 uppercase tracking-wider">Keywords ({ag.keywords.length})</div>
                  <div className="flex flex-wrap gap-1">
                    {ag.keywords.slice(0, 20).map((kw: any, ki: number) => (
                      <span key={ki} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-blue-500/10 text-blue-300/70 border border-blue-500/15">
                        [{kw.match_type?.charAt(0)}] {kw.text}
                      </span>
                    ))}
                    {ag.keywords.length > 20 && (
                      <span className="text-[10px] text-white/20">+{ag.keywords.length - 20} more</span>
                    )}
                  </div>
                </div>
              )}

              {/* Ads */}
              {ag.ads?.map((ad: any, ai: number) => (
                <div key={ai} className="mb-2">
                  <div className="text-[10px] text-white/30 mb-1 uppercase tracking-wider">RSA {ai + 1}</div>
                  {/* Headlines */}
                  <div className="mb-1.5">
                    <span className="text-[10px] text-white/20">Headlines ({ad.headlines?.length || 0}):</span>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {(ad.headlines || []).map((h: string, hi: number) => (
                        <span key={hi} className={`inline-flex px-1.5 py-0.5 rounded text-[10px] border ${
                          h.length > 30 ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-white/5 bg-white/[0.03] text-white/50"
                        }`}>
                          {h} <span className="text-white/15 ml-1">({h.length})</span>
                        </span>
                      ))}
                    </div>
                  </div>
                  {/* Descriptions */}
                  <div>
                    <span className="text-[10px] text-white/20">Descriptions ({ad.descriptions?.length || 0}):</span>
                    <div className="space-y-0.5 mt-0.5">
                      {(ad.descriptions || []).map((d: string, di: number) => (
                        <div key={di} className={`text-[10px] px-1.5 py-0.5 rounded border ${
                          d.length > 90 ? "border-red-500/30 bg-red-500/10 text-red-300" : "border-white/5 bg-white/[0.03] text-white/50"
                        }`}>
                          {d} <span className="text-white/15">({d.length})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {ad.final_url && (
                    <div className="text-[10px] text-white/20 mt-1">URL: {ad.final_url}</div>
                  )}
                </div>
              ))}

              {/* Negative keywords */}
              {ag.negative_keywords?.length > 0 && (
                <div>
                  <div className="text-[10px] text-white/30 mb-1 uppercase tracking-wider">Negatives ({ag.negative_keywords.length})</div>
                  <div className="flex flex-wrap gap-1">
                    {ag.negative_keywords.slice(0, 15).map((n: string, ni: number) => (
                      <span key={ni} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-red-500/10 text-red-300/60 border border-red-500/15">
                        -{n}
                      </span>
                    ))}
                    {ag.negative_keywords.length > 15 && (
                      <span className="text-[10px] text-white/20">+{ag.negative_keywords.length - 15} more</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Extensions */}
          {(sitelinks.length > 0 || callouts.length > 0 || snippets) && (
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
              <div className="text-xs font-semibold text-white/60 mb-2 uppercase tracking-wider">Extensions</div>

              {sitelinks.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-white/30 mb-1">Sitelinks ({sitelinks.length})</div>
                  <div className="space-y-1">
                    {sitelinks.map((sl: any, si: number) => (
                      <div key={si} className="text-[10px] text-white/50">
                        <span className="text-blue-300/70 font-medium">{sl.link_text}</span>
                        {sl.description1 && <span className="text-white/20"> — {sl.description1}</span>}
                        {sl.final_url && <span className="text-white/15 block">{sl.final_url}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {callouts.length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] text-white/30 mb-1">Callouts ({callouts.length})</div>
                  <div className="flex flex-wrap gap-1">
                    {callouts.map((c: string, ci: number) => (
                      <span key={ci} className="inline-flex px-1.5 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-300/70 border border-amber-500/15">
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {snippets && (
                <div>
                  <div className="text-[10px] text-white/30 mb-1">Snippets: {snippets.header}</div>
                  <div className="flex flex-wrap gap-1">
                    {(snippets.values || []).map((v: string, vi: number) => (
                      <span key={vi} className="inline-flex px-1.5 py-0.5 rounded text-[10px] bg-violet-500/10 text-violet-300/70 border border-violet-500/15">
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Strategy reasoning */}
          {meta?.strategy?.reasoning && (
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
              <div className="text-xs font-semibold text-white/60 mb-1 uppercase tracking-wider">Strategy</div>
              <p className="text-[10px] text-white/40 leading-relaxed">{meta.strategy.reasoning}</p>
              {meta.strategy.profit_potential && (
                <p className="text-[10px] text-emerald-400/60 mt-1">{meta.strategy.profit_potential}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────

export default function OperatorPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [approving, setApproving] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<OperatorMode>("auto");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [liveLog, setLiveLog] = useState<string[]>([]);
  const logTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pipelinePollRef = useRef<NodeJS.Timeout | null>(null);

  // ── Session History State ──
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const [customerId, setCustomerId] = useState("");
  const [imageEngine, setImageEngine] = useState<string>("google");

  useEffect(() => {
    // Auto-detect Google Ads customer ID from connected accounts
    api.get("/api/ads/accounts").then((accounts: any) => {
      const accts = Array.isArray(accounts) ? accounts : [];
      const active = accts.find((a: any) => a.customer_id && a.status === "active");
      if (active) {
        setCustomerId(active.customer_id);
      } else if (accts.length > 0 && accts[0].customer_id) {
        setCustomerId(accts[0].customer_id);
      }
    }).catch(() => {});
  }, []);

  // ── Session History Functions ──
  async function loadSessions() {
    setLoadingSessions(true);
    try {
      const data = await api.get("/api/operator/unified/chat");
      setSessions(Array.isArray(data) ? data : []);
    } catch { /* ignore */ }
    setLoadingSessions(false);
  }

  function toggleSessions() {
    const next = !showSessions;
    setShowSessions(next);
    if (next) loadSessions();
  }

  async function loadSession(session: ConversationSession) {
    try {
      const data = await api.get(`/api/operator/unified/chat/${session.conversation_id}`);
      setConversationId(session.conversation_id);
      setMode(session.mode || "auto");
      // Rebuild messages from server data
      const msgs: Message[] = (data.messages || []).map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content || m.structured_payload?.summary || "",
        structured_payload: m.structured_payload,
        proposed_actions: m.proposed_actions,
        created_at: m.created_at,
      }));
      setMessages(msgs);
      setError("");
    } catch (err: any) {
      setError(err.message || "Failed to load session");
    }
  }

  async function renameSession(sessionId: string, title: string) {
    try {
      await api.patch(`/api/operator/unified/chat/${sessionId}`, { title });
      setSessions(prev => prev.map(s =>
        s.conversation_id === sessionId ? { ...s, title } : s
      ));
      setEditingSessionId(null);
    } catch { /* ignore */ }
  }

  async function deleteSession(sessionId: string) {
    try {
      await api.delete(`/api/operator/unified/chat/${sessionId}`);
      setSessions(prev => prev.filter(s => s.conversation_id !== sessionId));
      if (conversationId === sessionId) {
        setConversationId(null);
        setMessages([]);
      }
    } catch { /* ignore */ }
  }

  function startNewSession() {
    setConversationId(null);
    setMessages([]);
    setError("");
    setInput("");
  }

  // Unified API for auto mode and explicit channel modes
  const apiBase = mode === "auto" || mode === "gbp" || mode === "image"
    ? "/api/operator/unified"
    : mode === "meta_ads"
      ? "/api/operator/meta"
      : "/api/operator";

  const quickPrompts = QUICK_PROMPTS[mode];
  const modeCfg = MODE_CONFIG[mode];

  // Auto mode and unified modes don't need customerId
  const needsCustomerId = mode === "google_ads";
  const canSend = mode === "auto" || mode === "meta_ads" || mode === "gbp" || mode === "image" || !!customerId;

  function switchMode(m: OperatorMode) {
    if (m === mode) return;
    setMode(m);
    setMessages([]);
    setConversationId(null);
    setError("");
    setInput("");
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function stopProcess() {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (logTimerRef.current) {
      clearInterval(logTimerRef.current);
      logTimerRef.current = null;
    }
    stopPipelinePolling();
    setSending(false);
    setLiveLog(prev => [...prev, "Process cancelled by user"]);
  }

  function startLiveLog(logMode: OperatorMode) {
    // If this is a follow-up message (conversation already exists), show shorter log
    // since the backend uses cached context and skips the full scan
    const isFollowUp = messages.length > 0;

    const steps = isFollowUp
      ? [
          "Processing your message...",
          "Sending to IntelliDrive AI...",
          "Generating response...",
        ]
      : logMode === "auto"
        ? [
            "Classifying intent...",
            "Checking connected systems...",
            "Querying Google Ads API...",
            "Fetching campaign performance (30 days)...",
            "Building account context...",
            "Sending to IntelliDrive AI for analysis...",
            "Generating findings & recommendations...",
          ]
        : logMode === "google_ads"
          ? [
              "Connecting to Google Ads API...",
              "Fetching account info...",
              "Loading campaign performance...",
              "Pulling keyword data...",
              "Building account context...",
              "Sending to IntelliDrive AI for analysis...",
              "Generating recommendations...",
            ]
          : logMode === "meta_ads"
            ? [
                "Connecting to Meta Ads API...",
                "Fetching campaigns & ad sets...",
                "Sending to IntelliDrive AI for analysis...",
                "Generating recommendations...",
              ]
            : [
                "Processing request...",
                "Sending to IntelliDrive AI...",
                "Generating response...",
              ];

    setLiveLog([steps[0]]);
    let stepIdx = 1;
    const interval = isFollowUp ? 1500 : 2500;
    logTimerRef.current = setInterval(() => {
      if (stepIdx < steps.length) {
        setLiveLog(prev => [...prev, steps[stepIdx]]);
        stepIdx++;
      } else {
        if (logTimerRef.current) clearInterval(logTimerRef.current);
      }
    }, interval);
  }

  function startPipelinePolling(convId: string) {
    if (pipelinePollRef.current) clearInterval(pipelinePollRef.current);
    const seenIds = new Set<string>();
    pipelinePollRef.current = setInterval(async () => {
      try {
        const data = await api.get(`/api/operator/unified/chat/${convId}`);
        const allMsgs: Message[] = (data.messages || []).map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content || m.structured_payload?.summary || "",
          structured_payload: m.structured_payload,
          proposed_actions: m.proposed_actions,
          created_at: m.created_at,
        }));
        const progressMsgs = allMsgs.filter(
          (m) => m.structured_payload?.type === "pipeline_progress" && !seenIds.has(m.id)
        );
        if (progressMsgs.length > 0) {
          for (const pm of progressMsgs) seenIds.add(pm.id);
          // Inject real pipeline progress messages into the messages state
          // so PipelineProgressCard renders them in real-time
          setMessages((prev) => {
            const existingIds = new Set(prev.map((m) => m.id));
            const newMsgs = progressMsgs.filter((m) => !existingIds.has(m.id));
            return newMsgs.length > 0 ? [...prev, ...newMsgs] : prev;
          });
          // Stop the fake log stepper once real progress arrives
          if (logTimerRef.current) {
            clearInterval(logTimerRef.current);
            logTimerRef.current = null;
          }
          setLiveLog([]);
        }
      } catch {
        // Ignore polling errors
      }
    }, 3000);
  }

  function stopPipelinePolling() {
    if (pipelinePollRef.current) {
      clearInterval(pipelinePollRef.current);
      pipelinePollRef.current = null;
    }
  }

  async function handleSend(text?: string) {
    const msg = text || input.trim();
    if (!msg || sending) return;

    setInput("");
    setError("");
    setSending(true);
    setLiveLog([]);

    // Start live log simulation
    startLiveLog(mode);

    // Create abort controller
    const controller = new AbortController();
    abortRef.current = controller;

    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: msg,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);

    try {
      let body: any;

      if (apiBase === "/api/operator/unified") {
        body = {
          conversation_id: conversationId,
          message: msg,
          mode: mode,
          date_range: "LAST_30_DAYS",
          image_engine: imageEngine,
        };
        if (customerId) body.customer_id = customerId;
      } else if (apiBase === "/api/operator/meta") {
        body = {
          conversation_id: conversationId,
          message: msg,
          image_engine: imageEngine,
        };
      } else {
        body = {
          conversation_id: conversationId,
          message: msg,
          customer_id: customerId,
          date_range: "LAST_30_DAYS",
          image_engine: imageEngine,
        };
      }

      // Start polling for pipeline progress if we have a conversation
      if (conversationId) {
        startPipelinePolling(conversationId);
      }

      const result = await api.post(`${apiBase}/chat`, body, { signal: controller.signal });

      // Stop polling now that the response arrived
      stopPipelinePolling();

      if (!conversationId && result.conversation_id) {
        setConversationId(result.conversation_id);
        if (showSessions) loadSessions();
      }

      const assistantMsg: Message = {
        id: result.message_id || `assistant-${Date.now()}`,
        role: "assistant",
        content: result.summary || "",
        structured_payload: {
          summary: result.summary,
          findings: result.findings,
          recommended_actions: result.recommended_actions,
          questions: result.questions,
          message: result.message,
          _systems_used: result.systems_used,
          _system_errors: result.system_errors,
        },
        proposed_actions: result.recommended_actions || [],
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: any) {
      if (err.name === "AbortError") {
        // User cancelled — don't show error
      } else {
        setError(err.message || "Failed to send message");
      }
    } finally {
      setSending(false);
      abortRef.current = null;
      stopPipelinePolling();
      if (logTimerRef.current) {
        clearInterval(logTimerRef.current);
        logTimerRef.current = null;
      }
      setLiveLog([]);
    }
  }

  async function handleApprove(actionIds: string[]) {
    if (!conversationId || approving) return;
    setApproving(true);
    try {
      const body: any = { action_ids: actionIds };
      if (apiBase === "/api/operator" && customerId) body.customer_id = customerId;
      const result = await api.post(`${apiBase}/chat/${conversationId}/approve`, body);

      const execMsg: Message = {
        id: `exec-${Date.now()}`,
        role: "assistant",
        content: `Executed ${result.succeeded} action(s) successfully.${result.failed ? ` ${result.failed} failed.` : ""}`,
        structured_payload: {
          type: "execution_result",
          results: result.results,
          succeeded: result.succeeded,
          failed: result.failed,
        },
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, execMsg]);

      setMessages(prev =>
        prev.map(m => {
          if (!m.proposed_actions) return m;
          return {
            ...m,
            proposed_actions: m.proposed_actions.map(a => {
              const execResult = result.results?.find((r: any) => r.action_id === a.id);
              if (execResult) {
                return { ...a, status: execResult.status === "success" ? "executed" : "failed" };
              }
              return a;
            }),
          };
        })
      );
    } catch (err: any) {
      setError(err.message || "Failed to execute actions");
    } finally {
      setApproving(false);
    }
  }

  async function handleReject(actionIds: string[]) {
    if (!conversationId) return;
    try {
      await api.post(`${apiBase}/chat/${conversationId}/reject`, {
        action_ids: actionIds,
      });
      setMessages(prev =>
        prev.map(m => {
          if (!m.proposed_actions) return m;
          return {
            ...m,
            proposed_actions: m.proposed_actions.map(a =>
              actionIds.includes(a.id) ? { ...a, status: "rejected" } : a
            ),
          };
        })
      );
    } catch (err: any) {
      setError(err.message);
    }
  }

  const isEmpty = messages.length === 0;
  const ModeIcon = modeCfg.icon;

  // Group sessions by date
  function groupSessionsByDate(list: ConversationSession[]) {
    const groups: { label: string; items: ConversationSession[] }[] = [];
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    const todayStr = today.toDateString();
    const yesterdayStr = yesterday.toDateString();

    const todayItems: ConversationSession[] = [];
    const yesterdayItems: ConversationSession[] = [];
    const olderItems: ConversationSession[] = [];

    for (const s of list) {
      const d = new Date(s.updated_at).toDateString();
      if (d === todayStr) todayItems.push(s);
      else if (d === yesterdayStr) yesterdayItems.push(s);
      else olderItems.push(s);
    }

    if (todayItems.length) groups.push({ label: "Today", items: todayItems });
    if (yesterdayItems.length) groups.push({ label: "Yesterday", items: yesterdayItems });
    if (olderItems.length) groups.push({ label: "Older", items: olderItems });
    return groups;
  }

  return (
    <AppLayout>
      <div className="flex h-[calc(100vh-4rem)]">
        {/* Session History Sidebar */}
        {showSessions && (
          <div className="w-72 flex-shrink-0 border-r border-white/5 bg-white/[0.01] flex flex-col h-full">
            {/* Sidebar Header */}
            <div className="flex items-center justify-between px-3 py-3 border-b border-white/5">
              <span className="text-xs font-semibold text-white/60 uppercase tracking-wider">Sessions</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={startNewSession}
                  className="p-1.5 rounded-lg hover:bg-white/10 text-white/40 hover:text-white/80 transition-colors"
                  title="New session"
                >
                  <Plus className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setShowSessions(false)}
                  className="p-1.5 rounded-lg hover:bg-white/10 text-white/40 hover:text-white/80 transition-colors"
                >
                  <PanelLeftClose className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Session List */}
            <div className="flex-1 overflow-y-auto">
              {loadingSessions ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-4 h-4 animate-spin text-white/30" />
                </div>
              ) : sessions.length === 0 ? (
                <div className="text-center py-8 text-xs text-white/20">
                  No sessions yet
                </div>
              ) : (
                groupSessionsByDate(sessions).map(group => (
                  <div key={group.label}>
                    <div className="px-3 pt-3 pb-1 text-[10px] font-semibold text-white/25 uppercase tracking-wider">
                      {group.label}
                    </div>
                    {group.items.map(s => {
                      const isActive = conversationId === s.conversation_id;
                      const isEditing = editingSessionId === s.conversation_id;
                      const modeBadge = MODE_CONFIG[s.mode] || MODE_CONFIG.auto;

                      return (
                        <div
                          key={s.conversation_id}
                          className={`group relative mx-2 mb-0.5 rounded-lg transition-all ${
                            isActive
                              ? "bg-white/10 border border-white/10"
                              : "hover:bg-white/[0.04] border border-transparent"
                          }`}
                        >
                          {isEditing ? (
                            <div className="flex items-center gap-1 p-2">
                              <input
                                autoFocus
                                value={editingTitle}
                                onChange={e => setEditingTitle(e.target.value)}
                                onKeyDown={e => {
                                  if (e.key === "Enter") renameSession(s.conversation_id, editingTitle);
                                  if (e.key === "Escape") setEditingSessionId(null);
                                }}
                                className="flex-1 bg-white/10 rounded px-2 py-1 text-xs text-white outline-none border border-white/20"
                              />
                              <button
                                onClick={() => renameSession(s.conversation_id, editingTitle)}
                                className="p-1 text-emerald-400 hover:text-emerald-300"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => setEditingSessionId(null)}
                                className="p-1 text-white/30 hover:text-white/60"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => loadSession(s)}
                              className="w-full text-left p-2"
                            >
                              <div className="flex items-center gap-1.5 mb-1">
                                <span className={`inline-flex items-center px-1 py-0.5 rounded text-[8px] font-bold ${
                                  modeBadge.color.replace("text-", "text-").replace("-400", "-300")
                                } bg-white/5`}>
                                  {modeBadge.label}
                                </span>
                                {(s.actions_executed > 0 || s.actions_failed > 0) && (
                                  <span className="text-[10px] text-white/25 ml-auto">
                                    {s.actions_executed > 0 && (
                                      <span className="text-emerald-400/60">+{s.actions_executed}</span>
                                    )}
                                    {s.actions_failed > 0 && (
                                      <span className="text-red-400/60 ml-1">-{s.actions_failed}</span>
                                    )}
                                  </span>
                                )}
                              </div>
                              <div className="text-xs text-white/70 truncate leading-tight">
                                {s.title}
                              </div>
                              <div className="text-[10px] text-white/20 mt-0.5">
                                {new Date(s.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                              </div>
                            </button>
                          )}

                          {/* Hover actions */}
                          {!isEditing && (
                            <div className="absolute top-1.5 right-1.5 hidden group-hover:flex items-center gap-0.5">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingSessionId(s.conversation_id);
                                  setEditingTitle(s.title);
                                }}
                                className="p-1 rounded hover:bg-white/10 text-white/20 hover:text-white/60 transition-colors"
                                title="Rename"
                              >
                                <Pencil className="w-3 h-3" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (confirm("Delete this session?")) deleteSession(s.conversation_id);
                                }}
                                className="p-1 rounded hover:bg-red-500/20 text-white/20 hover:text-red-400 transition-colors"
                                title="Delete"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-white/5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={toggleSessions}
                className="w-10 h-10 rounded-xl bg-white/5 hover:bg-white/10 flex items-center justify-center transition-colors"
                title={showSessions ? "Hide sessions" : "Show sessions"}
              >
                {showSessions ? (
                  <PanelLeftClose className="w-5 h-5 text-white/50" />
                ) : (
                  <PanelLeftOpen className="w-5 h-5 text-white/50" />
                )}
              </button>
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${modeCfg.gradient} flex items-center justify-center`}>
                <ModeIcon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">IntelliDrive Operator</h1>
                <p className="text-xs text-white/40">{modeCfg.description}</p>
              </div>
            </div>
            {/* Mode Tabs */}
            <div className="flex items-center gap-1 bg-white/5 rounded-lg p-1">
              {(Object.keys(MODE_CONFIG) as OperatorMode[]).map((m) => {
                const cfg = MODE_CONFIG[m];
                const TabIcon = cfg.icon;
                return (
                  <button
                    key={m}
                    onClick={() => switchMode(m)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      mode === m
                        ? "bg-white/10 text-white shadow-sm"
                        : "text-white/40 hover:text-white/60"
                    }`}
                  >
                    <TabIcon className="w-3.5 h-3.5" />
                    {cfg.label}
                  </button>
                );
              })}
            </div>
            {/* Image Engine Selector */}
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-white/30 font-medium">Image AI:</span>
              <select
                value={imageEngine}
                onChange={(e) => setImageEngine(e.target.value)}
                className="bg-white/5 border border-white/10 rounded-md text-xs text-white/70 px-2 py-1 focus:outline-none focus:ring-1 focus:ring-violet-500/50"
              >
                <option value="google" className="bg-gray-900 text-white">Nano Banana (Google)</option>
                <option value="dalle" className="bg-gray-900 text-white">DALL-E 3</option>
                <option value="stability" className="bg-gray-900 text-white">Stability AI</option>
                <option value="flux" className="bg-gray-900 text-white">Flux.1 Pro</option>
              </select>
            </div>
          </div>
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center h-full max-w-2xl mx-auto">
              <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${modeCfg.gradient} bg-opacity-20 border border-white/5 flex items-center justify-center mb-6`}>
                <Bot className="w-8 h-8 text-white/80" />
              </div>
              <h2 className="text-xl font-bold text-white mb-2">
                {mode === "auto" ? "What can I help you with?" : `${modeCfg.label} Operator`}
              </h2>
              <p className="text-sm text-white/40 text-center mb-8 max-w-md">
                {modeCfg.description}
              </p>

              {mode === "auto" && (
                <div className="flex items-center gap-2 mb-6 text-xs text-violet-400/80 bg-violet-500/10 border border-violet-500/20 rounded-lg px-4 py-2.5">
                  <Sparkles className="w-4 h-4 flex-shrink-0" />
                  <span>Auto mode analyzes your request and queries the right systems automatically.</span>
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full max-w-xl">
                {quickPrompts.map((qp) => (
                  <button
                    key={qp.label}
                    onClick={() => handleSend(qp.prompt)}
                    disabled={sending || !canSend}
                    className="flex items-center gap-2.5 p-3 rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/10 transition-all text-left group"
                  >
                    <qp.icon className={`w-4 h-4 ${modeCfg.color} opacity-60 group-hover:opacity-100 flex-shrink-0`} />
                    <span className="text-xs font-medium text-white/60 group-hover:text-white/80">{qp.label}</span>
                  </button>
                ))}
              </div>

              {needsCustomerId && !customerId && (
                <div className="mt-6 flex items-center gap-2 text-xs text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-2.5">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>No Google Ads account connected. Go to Settings &gt; Accounts to connect one.</span>
                </div>
              )}
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4">
              {(() => {
                // Group consecutive pipeline_progress and audit_progress messages
                const rendered: React.ReactNode[] = [];
                let pipelineBatch: Message[] = [];
                let auditBatch: Message[] = [];

                function flushPipeline() {
                  if (pipelineBatch.length > 0) {
                    rendered.push(
                      <div key={`pipeline-${pipelineBatch[0].id}`} className="flex gap-3">
                        <div className={`w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center flex-shrink-0 mt-1`}>
                          <Sparkles className="w-4 h-4 text-white" />
                        </div>
                        <div className="max-w-[85%]">
                          <PipelineProgressCard messages={pipelineBatch} />
                          {auditBatch.length > 0 && <AuditProgressCard messages={auditBatch} />}
                        </div>
                      </div>
                    );
                    pipelineBatch = [];
                    auditBatch = [];
                  } else if (auditBatch.length > 0) {
                    rendered.push(
                      <div key={`audit-progress-${auditBatch[0].id}`} className="flex gap-3">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center flex-shrink-0 mt-1">
                          <Shield className="w-4 h-4 text-white" />
                        </div>
                        <div className="max-w-[85%]">
                          <AuditProgressCard messages={auditBatch} />
                        </div>
                      </div>
                    );
                    auditBatch = [];
                  }
                }

                for (const msg of messages) {
                  const sp = msg.structured_payload as any;
                  if (sp?.type === "pipeline_progress") {
                    pipelineBatch.push(msg);
                    continue;
                  }
                  if (sp?.type === "audit_progress") {
                    auditBatch.push(msg);
                    continue;
                  }
                  flushPipeline();

                  rendered.push(
                    <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
                      {msg.role === "assistant" && (
                        <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${modeCfg.gradient} flex items-center justify-center flex-shrink-0 mt-1`}>
                          <Bot className="w-4 h-4 text-white" />
                        </div>
                      )}
                      <div className={`max-w-[85%] ${msg.role === "user" ? "order-first" : ""}`}>
                        {msg.role === "user" ? (
                          <div className="rounded-2xl rounded-tr-md bg-blue-600/20 border border-blue-500/20 px-4 py-3">
                            <p className="text-sm text-white/90">{msg.content}</p>
                          </div>
                        ) : (
                          <div className="rounded-2xl rounded-tl-md bg-white/[0.03] border border-white/5 px-4 py-3">
                            <SystemsUsedPills systems={msg.structured_payload?._systems_used} />
                            {msg.content && (
                              <p className="text-sm text-white/80 leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                            )}
                            {msg.structured_payload?.message && msg.structured_payload.message !== msg.content && (
                              <p className="text-sm text-white/60 mt-2 leading-relaxed">{msg.structured_payload.message}</p>
                            )}
                            <FindingsCard findings={msg.structured_payload?.findings || []} />
                            <ActionsCard
                              actions={msg.proposed_actions || msg.structured_payload?.recommended_actions || []}
                              onApprove={handleApprove}
                              onReject={handleReject}
                              approving={approving}
                            />
                            {/* Campaign detail view for deploy_full_campaign actions */}
                            {(msg.proposed_actions || msg.structured_payload?.recommended_actions || [])
                              .filter((a: any) => a.action_type === "deploy_full_campaign")
                              .map((a: any) => (
                                <CampaignDetailCard key={`detail-${a.id}`} payload={a} />
                              ))}
                            <ExecutionResultCard payload={msg.structured_payload} />
                            <AuditResultCard payload={msg.structured_payload} onApprove={handleApprove} approving={approving} />
                            <ImageResultCard payload={msg.structured_payload} />
                            {/* Next Steps */}
                            {msg.structured_payload?.next_steps?.length ? (
                              <div className="mt-3 bg-violet-500/10 border border-violet-500/20 rounded-xl p-3">
                                <div className="flex items-center gap-1.5 mb-2">
                                  <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                                  <span className="text-[11px] font-semibold text-violet-300">Next Steps</span>
                                </div>
                                <div className="space-y-1.5">
                                  {msg.structured_payload.next_steps.map((step, i) => (
                                    <div key={i} className="flex items-start gap-2 text-xs text-violet-200/80">
                                      <span className="text-violet-400 font-bold mt-0.5">{i + 1}.</span>
                                      <span>{step}</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {/* Follow-up Questions */}
                            {msg.structured_payload?.questions?.length ? (
                              <div className="mt-3 space-y-1">
                                {msg.structured_payload.questions.map((q, i) => (
                                  <button
                                    key={i}
                                    onClick={() => handleSend(q)}
                                    className="block text-xs text-blue-400/80 hover:text-blue-400 transition-colors cursor-pointer"
                                  >
                                    &rarr; {q}
                                  </button>
                                ))}
                              </div>
                            ) : null}
                            {/* System errors */}
                            {msg.structured_payload?._system_errors && Object.keys(msg.structured_payload._system_errors).length > 0 && (
                              <div className="mt-3 text-[10px] text-amber-400/60 bg-amber-500/5 rounded-lg p-2">
                                {Object.entries(msg.structured_payload._system_errors).map(([sys, err]) => (
                                  <div key={sys} className="flex items-center gap-1">
                                    <AlertTriangle className="w-3 h-3" />
                                    <span>{SYSTEM_LABELS[sys]?.label || sys}: {err}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                        <span className="text-[10px] text-white/20 mt-1 block px-1">
                          {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      {msg.role === "user" && (
                        <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center flex-shrink-0 mt-1">
                          <User className="w-4 h-4 text-white/60" />
                        </div>
                      )}
                    </div>
                  );
                }
                flushPipeline();
                return rendered;
              })()}

              {sending && (
                <div className="flex gap-3">
                  <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${modeCfg.gradient} flex items-center justify-center flex-shrink-0`}>
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                  <div className="rounded-2xl rounded-tl-md bg-white/[0.03] border border-white/5 px-4 py-3 min-w-[300px]">
                    <div className="space-y-1.5">
                      {liveLog.map((step, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          {i === liveLog.length - 1 ? (
                            <Loader2 className="w-3 h-3 animate-spin text-blue-400 flex-shrink-0" />
                          ) : (
                            <CheckCircle className="w-3 h-3 text-emerald-500 flex-shrink-0" />
                          )}
                          <span className={i === liveLog.length - 1 ? "text-white/60" : "text-white/30"}>
                            {step}
                          </span>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={stopProcess}
                      className="flex items-center gap-1.5 mt-3 px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-medium hover:bg-red-500/20 transition-colors"
                    >
                      <StopCircle className="w-3.5 h-3.5" />
                      Stop
                    </button>
                  </div>
                </div>
              )}

              {error && (
                <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="flex-shrink-0 border-t border-white/5 px-6 py-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder={
                    !canSend
                      ? "Connect a Google Ads account to get started..."
                      : mode === "auto"
                        ? "Ask anything — audit marketing, find wasted spend, create campaigns, manage reviews..."
                        : `Ask IntelliDrive about your ${modeCfg.label}...`
                  }
                  disabled={sending || !canSend}
                  rows={1}
                  className="w-full resize-none rounded-xl bg-white/[0.04] border border-white/10 px-4 py-3 pr-12 text-sm text-white placeholder:text-white/25 focus:outline-none focus:border-blue-500/40 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-40 transition-all"
                />
                <button
                  onClick={() => handleSend()}
                  disabled={!input.trim() || sending || !canSend}
                  className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-white/5 disabled:text-white/20 flex items-center justify-center transition-colors"
                >
                  {sending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </button>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-2 text-[10px] text-white/20">
              <Clock className="w-3 h-3" />
              <span>Analyzing last 30 days of data</span>
              <span>·</span>
              <span>All changes require your approval</span>
              <span>·</span>
              <span>{mode === "auto" ? "Auto-routes to connected systems" : modeCfg.label}</span>
              <span>·</span>
              <span>Powered by IntelliDrive AI</span>
            </div>
          </div>
        </div>
        </div>{/* Close Main Chat Area */}
      </div>
    </AppLayout>
  );
}
