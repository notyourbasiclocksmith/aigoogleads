"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Brain, Send, RotateCcw, Loader2, Rocket, Sparkles,
  Shield, Zap, Globe, FileText, CheckCircle, AlertCircle,
  ChevronDown, ChevronUp, ExternalLink, Eye, Megaphone,
  Target, TrendingUp, Star, Wand2,
} from "lucide-react";

interface QuickAction {
  label: string;
  action: string;
}

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  quick_actions?: QuickAction[];
  campaign_draft?: any;
  landing_page?: any;
  campaign_audit?: any;
  lp_audit?: any;
  expansions?: any[];
  bulk_task_id?: string;
}

export default function StrategistPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionState, setSessionState] = useState<any>({});
  const [error, setError] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Side panel state
  const [showDraft, setShowDraft] = useState(false);
  const [activeDraft, setActiveDraft] = useState<any>(null);
  const [showLp, setShowLp] = useState(false);
  const [activeLp, setActiveLp] = useState<any>(null);
  const [showAudit, setShowAudit] = useState(false);
  const [activeAudit, setActiveAudit] = useState<any>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(text?: string, action?: string) {
    const msg = (text || input).trim();
    if (!msg && !action) return;
    if (loading) return;

    const userMsg: ChatMsg = { role: "user", content: msg || action || "" };
    const updated = [...messages, userMsg];
    setMessages(updated);
    setInput("");
    setLoading(true);
    setError("");

    try {
      const history = updated.map((m) => ({ role: m.role, content: m.content }));
      const result = await api.post("/api/v2/strategist/chat", {
        message: msg,
        action: action || undefined,
        session_state: sessionState,
        conversation_history: history,
      });

      // Update session state
      if (result.session_state) setSessionState(result.session_state);

      const assistantMsg: ChatMsg = {
        role: "assistant",
        content: result.reply || "I'm processing your request...",
        quick_actions: result.quick_actions || [],
        campaign_draft: result.campaign_draft || undefined,
        landing_page: result.landing_page || undefined,
        campaign_audit: result.campaign_audit || undefined,
        lp_audit: result.lp_audit || undefined,
        expansions: result.expansions || undefined,
        bulk_task_id: result.bulk_task_id || undefined,
      };

      setMessages([...updated, assistantMsg]);

      // Auto-show side panels for rich content
      if (result.campaign_draft) {
        setActiveDraft(result.campaign_draft);
        setShowDraft(true);
      }
      if (result.landing_page) {
        setActiveLp(result.landing_page);
        setShowLp(true);
      }
      if (result.campaign_audit) {
        setActiveAudit(result.campaign_audit);
        setShowAudit(true);
      }
    } catch (err: any) {
      setError(err.message || "Failed to process message");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function handleQuickAction(action: QuickAction) {
    sendMessage(undefined, action.action);
  }

  function handleNewChat() {
    setMessages([]);
    setInput("");
    setSessionState({});
    setError("");
    setShowDraft(false);
    setActiveDraft(null);
    setShowLp(false);
    setActiveLp(null);
    setShowAudit(false);
    setActiveAudit(null);
  }

  const hasChat = messages.length > 0;
  const hasSidePanel = showDraft || showLp || showAudit;

  return (
    <AppLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-blue-600" />
              AI Marketing Operator
            </h1>
            <p className="text-slate-500 text-sm">
              Build campaigns, generate landing pages, audit, expand — all through AI chat
            </p>
          </div>
          {hasChat && (
            <Button variant="outline" size="sm" onClick={handleNewChat}>
              <RotateCcw className="w-4 h-4 mr-2" /> New Session
            </Button>
          )}
        </div>

        {/* Main Layout: Chat + Side Panel */}
        <div className={`grid gap-4 ${hasSidePanel ? "lg:grid-cols-[1fr_400px]" : "grid-cols-1"}`}>

          {/* ── Chat Panel ──────────────────────────────────── */}
          <Card className="flex flex-col overflow-hidden">
            <CardHeader className="pb-3 border-b bg-gradient-to-r from-blue-50/80 to-indigo-50/50">
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-blue-600" />
                <CardTitle className="text-base">Campaign Strategist</CardTitle>
                <Badge className="text-[10px] bg-blue-100 text-blue-700 border-blue-200">AI Operator</Badge>
                {sessionState.phase && (
                  <Badge className="text-[10px] bg-slate-100 text-slate-600 ml-auto">
                    {sessionState.phase?.replace(/_/g, " ")}
                  </Badge>
                )}
              </div>
            </CardHeader>

            <CardContent className="flex-1 p-0">
              <div className="min-h-[400px] max-h-[600px] overflow-y-auto p-4 space-y-4">
                {/* Welcome */}
                {!hasChat && (
                  <div className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
                      <Brain className="w-5 h-5 text-white" />
                    </div>
                    <div className="flex-1 space-y-3">
                      <div className="bg-slate-50 rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-700">
                        <p className="font-semibold text-slate-900 mb-2">I'm your AI Marketing Operator.</p>
                        <p>I'll help you build campaigns, generate landing pages, audit everything, and find growth opportunities. Tell me what you need!</p>
                        <p className="mt-2 text-slate-500">Try: <em>"Need a campaign for Ford car key replacement in DFW"</em></p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {[
                          "Build a campaign for emergency locksmith in Miami",
                          "Create campaigns for all car key brands in Dallas",
                          "I need a landing page for AC repair",
                          "Audit my current campaigns",
                        ].map((suggestion, i) => (
                          <button
                            key={i}
                            onClick={() => sendMessage(suggestion)}
                            className="text-xs bg-white border border-blue-200 text-blue-700 rounded-full px-3 py-1.5 hover:bg-blue-50 transition"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Messages */}
                {messages.map((msg, i) => (
                  <div key={i} className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                      msg.role === "user"
                        ? "bg-slate-800"
                        : "bg-gradient-to-br from-blue-500 to-indigo-600"
                    }`}>
                      {msg.role === "user" ? (
                        <span className="text-white text-xs font-bold">You</span>
                      ) : (
                        <Brain className="w-4 h-4 text-white" />
                      )}
                    </div>

                    <div className={`flex-1 max-w-[85%] ${msg.role === "user" ? "text-right" : ""}`}>
                      {/* Message bubble */}
                      <div className={`inline-block text-left rounded-2xl px-4 py-3 text-sm ${
                        msg.role === "user"
                          ? "bg-slate-800 text-white rounded-tr-sm"
                          : "bg-slate-50 text-slate-700 rounded-tl-sm"
                      }`}>
                        <div className="whitespace-pre-wrap prose prose-sm prose-slate max-w-none"
                          dangerouslySetInnerHTML={{ __html: formatMarkdown(msg.content) }}
                        />
                      </div>

                      {/* Rich content cards */}
                      {msg.role === "assistant" && (
                        <div className="space-y-2 mt-2">
                          {/* Campaign draft indicator */}
                          {msg.campaign_draft && (
                            <button
                              onClick={() => { setActiveDraft(msg.campaign_draft); setShowDraft(true); }}
                              className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 text-sm text-emerald-800 hover:bg-emerald-100 transition w-full text-left"
                            >
                              <Megaphone className="w-4 h-4" />
                              <span className="font-medium">Campaign Draft Ready</span>
                              <ChevronDown className="w-3 h-3 ml-auto" />
                            </button>
                          )}

                          {/* Landing page indicator */}
                          {msg.landing_page && (
                            <button
                              onClick={() => { setActiveLp(msg.landing_page); setShowLp(true); }}
                              className="flex items-center gap-2 bg-purple-50 border border-purple-200 rounded-lg px-3 py-2 text-sm text-purple-800 hover:bg-purple-100 transition w-full text-left"
                            >
                              <Globe className="w-4 h-4" />
                              <span className="font-medium">Landing Page Generated — {msg.landing_page.variants?.length || 0} variants</span>
                              <Eye className="w-3 h-3 ml-auto" />
                            </button>
                          )}

                          {/* Audit indicator */}
                          {msg.campaign_audit && (
                            <button
                              onClick={() => { setActiveAudit(msg.campaign_audit); setShowAudit(true); }}
                              className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800 hover:bg-amber-100 transition w-full text-left"
                            >
                              <Shield className="w-4 h-4" />
                              <span className="font-medium">
                                Campaign Audit: {msg.campaign_audit.overall_score}/100 ({msg.campaign_audit.grade})
                              </span>
                              <Eye className="w-3 h-3 ml-auto" />
                            </button>
                          )}

                          {/* LP Audit */}
                          {msg.lp_audit && msg.lp_audit.overall_score !== undefined && (
                            <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800">
                              <div className="flex items-center gap-2">
                                <Shield className="w-4 h-4" />
                                <span className="font-medium">
                                  Landing Page Audit: {msg.lp_audit.overall_score}/100 ({msg.lp_audit.grade})
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Bulk task */}
                          {msg.bulk_task_id && (
                            <div className="bg-orange-50 border border-orange-200 rounded-lg px-3 py-2 text-sm text-orange-800">
                              <div className="flex items-center gap-2">
                                <Rocket className="w-4 h-4" />
                                <span className="font-medium">Bulk generation started — Track progress in Growth AI → Bulk Campaigns</span>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Quick action buttons */}
                      {msg.role === "assistant" && msg.quick_actions && msg.quick_actions.length > 0 && (
                        <div className="flex flex-wrap gap-2 mt-3">
                          {msg.quick_actions.map((qa, qi) => (
                            <button
                              key={qi}
                              onClick={() => handleQuickAction(qa)}
                              disabled={loading}
                              className={`text-xs border rounded-full px-3 py-1.5 transition-colors disabled:opacity-50 ${
                                actionStyle(qa.action)
                              }`}
                            >
                              {actionIcon(qa.action)}
                              {qa.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* Loading */}
                {loading && (
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center flex-shrink-0">
                      <Brain className="w-4 h-4 text-white" />
                    </div>
                    <div className="bg-slate-50 rounded-2xl rounded-tl-sm px-4 py-3">
                      <div className="flex items-center gap-2 text-sm text-slate-500">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Thinking...</span>
                      </div>
                    </div>
                  </div>
                )}

                {error && (
                  <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4" />
                    {error}
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>

              {/* Input */}
              <div className="border-t p-3 bg-white">
                <div className="flex gap-2">
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={hasChat ? "Type your reply or click a quick action..." : "Describe your campaign idea..."}
                    className="flex-1 min-h-[44px] max-h-[120px] rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                    rows={1}
                  />
                  <Button
                    onClick={() => sendMessage()}
                    disabled={loading || !input.trim()}
                    className="h-[44px] w-[44px] rounded-xl p-0 bg-blue-600 hover:bg-blue-700"
                  >
                    <Send className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* ── Side Panel ──────────────────────────────────── */}
          {hasSidePanel && (
            <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
              {/* Campaign Draft Panel */}
              {showDraft && activeDraft && (
                <CampaignDraftPanel
                  draft={activeDraft}
                  onClose={() => setShowDraft(false)}
                />
              )}

              {/* Landing Page Panel */}
              {showLp && activeLp && (
                <LandingPagePanel
                  lp={activeLp}
                  onClose={() => setShowLp(false)}
                />
              )}

              {/* Audit Panel */}
              {showAudit && activeAudit && (
                <AuditPanel
                  audit={activeAudit}
                  onClose={() => setShowAudit(false)}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}

// ── Sub-components ─────────────────────────────────────────────

function CampaignDraftPanel({ draft, onClose }: { draft: any; onClose: () => void }) {
  const campaign = draft.campaign || {};
  const adGroups = draft.ad_groups || [];
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]));

  return (
    <Card className="border-emerald-200">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Megaphone className="w-4 h-4 text-emerald-600" />
            <CardTitle className="text-sm">Campaign Draft</CardTitle>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xs">✕</button>
        </div>
      </CardHeader>
      <CardContent className="text-xs space-y-3 max-h-[500px] overflow-y-auto">
        <div className="bg-emerald-50 rounded-lg p-2">
          <p className="font-semibold text-emerald-900">{campaign.name || "Campaign"}</p>
          <p className="text-emerald-700 mt-0.5">Budget: ${campaign.daily_budget || "auto"}/day • {campaign.bidding_strategy || "auto"}</p>
        </div>

        {adGroups.map((ag: any, i: number) => (
          <div key={i} className="border rounded-lg overflow-hidden">
            <button
              onClick={() => {
                const next = new Set(expanded);
                next.has(i) ? next.delete(i) : next.add(i);
                setExpanded(next);
              }}
              className="w-full flex items-center justify-between px-2 py-1.5 bg-slate-50 hover:bg-slate-100"
            >
              <span className="font-medium text-slate-800">{ag.name}</span>
              <span className="text-slate-400">{ag.keywords?.length || 0} kw</span>
            </button>
            {expanded.has(i) && (
              <div className="p-2 space-y-1">
                {ag.keywords?.slice(0, 10).map((kw: any, ki: number) => (
                  <div key={ki} className="flex items-center gap-1">
                    <span className="text-slate-600">{typeof kw === "string" ? kw : kw.text}</span>
                    <Badge className="text-[9px] bg-slate-100 text-slate-500 px-1">
                      {typeof kw === "string" ? "PHRASE" : kw.match_type}
                    </Badge>
                  </div>
                ))}
                {(ag.keywords?.length || 0) > 10 && (
                  <p className="text-slate-400">+{ag.keywords.length - 10} more</p>
                )}
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function LandingPagePanel({ lp, onClose }: { lp: any; onClose: () => void }) {
  const [activeVariant, setActiveVariant] = useState(0);
  const variants = lp.variants || [];

  return (
    <Card className="border-purple-200">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-purple-600" />
            <CardTitle className="text-sm">Landing Page</CardTitle>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xs">✕</button>
        </div>
      </CardHeader>
      <CardContent className="text-xs space-y-3 max-h-[500px] overflow-y-auto">
        <p className="text-slate-600">Slug: <code className="bg-slate-100 px-1 rounded">{lp.slug}</code></p>

        {/* Variant tabs */}
        {variants.length > 0 && (
          <>
            <div className="flex gap-1">
              {variants.map((v: any, i: number) => (
                <button
                  key={i}
                  onClick={() => setActiveVariant(i)}
                  className={`px-2 py-1 rounded text-xs font-medium transition ${
                    activeVariant === i
                      ? "bg-purple-100 text-purple-800"
                      : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                  }`}
                >
                  {v.key}: {v.name}
                </button>
              ))}
            </div>

            {/* Active variant content */}
            {variants[activeVariant] && (
              <VariantPreview content={variants[activeVariant].content} />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function VariantPreview({ content }: { content: any }) {
  if (!content) return <p className="text-slate-400 text-xs">No content</p>;

  const hero = content.hero || {};
  const trustBar = content.trust_bar || {};
  const reviews = content.reviews_section || {};

  return (
    <div className="space-y-2 border rounded-lg overflow-hidden">
      {/* Mini hero preview */}
      <div className="bg-gradient-to-r from-slate-800 to-slate-900 text-white p-3 text-center">
        <p className="font-bold text-sm">{hero.headline || "Headline"}</p>
        <p className="text-slate-300 text-[10px] mt-1">{hero.subheadline || ""}</p>
        {hero.cta_text && (
          <div className="mt-2 bg-blue-500 text-white text-[10px] font-medium rounded px-2 py-1 inline-block">
            {hero.cta_text}
          </div>
        )}
        {hero.urgency_badge && (
          <p className="text-amber-400 text-[10px] mt-1">{hero.urgency_badge}</p>
        )}
      </div>

      {/* Trust bar */}
      {trustBar.items && (
        <div className="flex flex-wrap gap-1 px-2 py-1 bg-slate-50">
          {trustBar.items.map((item: string, i: number) => (
            <span key={i} className="text-[9px] bg-white border rounded px-1 py-0.5 text-slate-600">{item}</span>
          ))}
        </div>
      )}

      {/* Reviews count */}
      {reviews.reviews && (
        <div className="px-2 py-1">
          <p className="text-[10px] text-slate-500">
            {reviews.reviews.length} reviews • {reviews.heading || ""}
          </p>
        </div>
      )}
    </div>
  );
}

function AuditPanel({ audit, onClose }: { audit: any; onClose: () => void }) {
  const score = audit.overall_score || 0;
  const grade = audit.grade || "?";
  const issues = audit.issues || [];
  const strengths = audit.strengths || [];

  const scoreColor = score >= 80 ? "text-green-600" : score >= 60 ? "text-amber-600" : "text-red-600";

  return (
    <Card className="border-amber-200">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-amber-600" />
            <CardTitle className="text-sm">Campaign Audit</CardTitle>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xs">✕</button>
        </div>
      </CardHeader>
      <CardContent className="text-xs space-y-3 max-h-[500px] overflow-y-auto">
        {/* Score */}
        <div className="text-center py-2">
          <p className={`text-3xl font-bold ${scoreColor}`}>{score}</p>
          <p className="text-slate-500">/ 100 (Grade: {grade})</p>
        </div>

        {/* Strengths */}
        {strengths.length > 0 && (
          <div>
            <p className="font-semibold text-green-800 mb-1">Strengths</p>
            {strengths.map((s: string, i: number) => (
              <div key={i} className="flex items-center gap-1 text-green-700 mb-0.5">
                <CheckCircle className="w-3 h-3" /> {s}
              </div>
            ))}
          </div>
        )}

        {/* Issues */}
        {issues.length > 0 && (
          <div>
            <p className="font-semibold text-red-800 mb-1">Issues ({issues.length})</p>
            {issues.map((issue: any, i: number) => (
              <div key={i} className="mb-2 bg-red-50 rounded p-2">
                <div className="flex items-center gap-1">
                  <Badge className={`text-[9px] ${
                    issue.severity === "critical" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                  }`}>
                    {issue.severity}
                  </Badge>
                  <span className="font-medium text-slate-800">{issue.title}</span>
                </div>
                {issue.fix && <p className="text-slate-600 mt-0.5">Fix: {issue.fix}</p>}
              </div>
            ))}
          </div>
        )}

        {audit.summary && (
          <p className="text-slate-600 italic">{audit.summary}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Helpers ─────────────────────────────────────────────────────

function formatMarkdown(text: string): string {
  if (!text) return "";
  let html = text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, '<code class="bg-slate-100 px-1 rounded text-xs">$1</code>')
    .replace(/^- (.*)/gm, '<li class="ml-4">$1</li>')
    .replace(/^---$/gm, '<hr class="my-2 border-slate-200">')
    .replace(/\n/g, "<br>");
  return html;
}

function actionStyle(action: string): string {
  if (action.includes("launch") || action.includes("approve"))
    return "bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100";
  if (action.includes("expand") || action.includes("bulk"))
    return "bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100";
  if (action.includes("lp") || action.includes("page"))
    return "bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100";
  if (action.includes("audit"))
    return "bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100";
  return "bg-white border-blue-200 text-blue-700 hover:bg-blue-50";
}

function actionIcon(action: string): React.ReactNode {
  return null; // Icons inline via Lucide would need JSX; keep buttons clean with text only
}
