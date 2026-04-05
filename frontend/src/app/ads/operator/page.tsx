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
  Sparkles, Shield, Clock, Globe, Image, Star, MessageSquare,
  StopCircle,
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
    message?: string;
    results?: any[];
    succeeded?: number;
    failed?: number;
    _systems_used?: string[];
    _system_errors?: Record<string, string>;
  };
  proposed_actions?: ProposedAction[];
  created_at: string;
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
    icon: Image,
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
    { icon: Image, label: "Ad image", prompt: "Generate a professional ad image for my business" },
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

  const [customerId, setCustomerId] = useState("");

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
    setSending(false);
    setLiveLog(prev => [...prev, "Process cancelled by user"]);
  }

  function startLiveLog(logMode: OperatorMode) {
    const steps = logMode === "auto"
      ? [
          "Classifying intent...",
          "Checking connected systems...",
          "Querying Google Ads API...",
          "Fetching campaign performance (30 days)...",
          "Pulling keyword data (top 200)...",
          "Analyzing search term report...",
          "Loading ad performance...",
          "Building account context...",
          "Sending to Claude for analysis...",
          "Generating findings & recommendations...",
        ]
      : logMode === "google_ads"
        ? [
            "Connecting to Google Ads API...",
            "Fetching account info...",
            "Loading campaign performance...",
            "Pulling keyword data (top 200 by spend)...",
            "Analyzing search term report...",
            "Loading ad performance...",
            "Fetching conversion tracking config...",
            "Computing heuristics (wasted spend, low CTR)...",
            "Sending to Claude for analysis...",
            "Generating structured recommendations...",
          ]
        : logMode === "meta_ads"
          ? [
              "Connecting to Meta Ads API...",
              "Fetching campaigns & ad sets...",
              "Loading ad performance...",
              "Sending to Claude for analysis...",
              "Generating recommendations...",
            ]
          : [
              "Processing request...",
              "Fetching data...",
              "Sending to Claude for analysis...",
              "Generating response...",
            ];

    setLiveLog([steps[0]]);
    let stepIdx = 1;
    logTimerRef.current = setInterval(() => {
      if (stepIdx < steps.length) {
        setLiveLog(prev => [...prev, steps[stepIdx]]);
        stepIdx++;
      } else {
        if (logTimerRef.current) clearInterval(logTimerRef.current);
      }
    }, 2500);
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
        };
        if (customerId) body.customer_id = customerId;
      } else if (apiBase === "/api/operator/meta") {
        body = {
          conversation_id: conversationId,
          message: msg,
        };
      } else {
        body = {
          conversation_id: conversationId,
          message: msg,
          customer_id: customerId,
          date_range: "LAST_30_DAYS",
        };
      }

      const result = await api.post(`${apiBase}/chat`, body, { signal: controller.signal });

      if (!conversationId && result.conversation_id) {
        setConversationId(result.conversation_id);
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

  return (
    <AppLayout>
      <div className="flex flex-col h-[calc(100vh-4rem)]">
        {/* Header */}
        <div className="flex-shrink-0 px-6 py-4 border-b border-white/5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${modeCfg.gradient} flex items-center justify-center`}>
                <ModeIcon className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">Claude Operator</h1>
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
              {messages.map((msg) => (
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
                        <ExecutionResultCard payload={msg.structured_payload} />
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
              ))}

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
                        : `Ask Claude about your ${modeCfg.label}...`
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
              <span>Powered by Claude</span>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
