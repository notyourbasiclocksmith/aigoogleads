"use client";

import { useState, useRef, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Wand2, Save, Rocket, ChevronDown, ChevronUp,
  CheckCircle2, Loader2, Brain, Search, Users, Target,
  DollarSign, Sparkles, Puzzle, Eye, EyeOff, AlertCircle,
  MessageSquare, ArrowRight, RotateCcw, X, Lightbulb, MapPin, Tag,
} from "lucide-react";

interface LogEntry {
  step: string;
  status: string;
  message: string;
  detail?: any;
}

const STEP_ICONS: Record<string, any> = {
  parse_intent: Brain,
  existing_campaigns: Search,
  research: Target,
  competitors: Users,
  keywords: Search,
  strategy: DollarSign,
  ai_copy: Sparkles,
  ai_copy_result: Sparkles,
  extensions: Puzzle,
  complete: CheckCircle2,
  error: AlertCircle,
};

interface RefinementResult {
  original_prompt: string;
  refined_prompt: string;
  detected_services?: string[];
  detected_locations?: string[];
  detected_goal?: string;
  detected_urgency?: string;
  suggested_budget?: string;
  overlap_warning?: string | null;
  suggestions?: string[];
  ai_powered: boolean;
}

export default function PromptPage() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<any>(null);
  const [error, setError] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set([0]));
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [showLog, setShowLog] = useState(true);
  const [aiPromptExpanded, setAiPromptExpanded] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Refinement state
  const [refining, setRefining] = useState(false);
  const [refinement, setRefinement] = useState<RefinementResult | null>(null);
  const [refinedPrompt, setRefinedPrompt] = useState("");

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logEntries]);

  async function handleRefine() {
    if (!prompt.trim()) return;
    setError("");
    setRefining(true);
    setRefinement(null);
    setDraft(null);
    setLogEntries([]);

    try {
      const result = await api.post("/api/ads/prompt/refine", { prompt });
      setRefinement(result);
      setRefinedPrompt(result.refined_prompt || prompt);
    } catch (err: any) {
      setError(err.message || "Refinement failed");
    } finally {
      setRefining(false);
    }
  }

  function handleUseRefined() {
    if (refinedPrompt.trim()) {
      setPrompt(refinedPrompt);
      setRefinement(null);
      setRefinedPrompt("");
    }
  }

  function handleConfirmAndGenerate() {
    if (refinedPrompt.trim()) {
      setPrompt(refinedPrompt);
      setRefinement(null);
      setRefinedPrompt("");
      // Trigger generation after state updates
      setTimeout(() => {
        handleGenerateWithPrompt(refinedPrompt);
      }, 0);
    }
  }

  function handleDismissRefinement() {
    setRefinement(null);
    setRefinedPrompt("");
  }

  async function handleGenerateWithPrompt(promptText: string) {
    if (!promptText.trim()) return;
    setError("");
    setLoading(true);
    setDraft(null);
    setLogEntries([]);
    setShowLog(true);
    setRefinement(null);

    const token = api.getToken();

    try {
      const res = await fetch("/api/ads/prompt/generate-stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ prompt: promptText }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Generation failed" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event: LogEntry = JSON.parse(jsonStr);
            setLogEntries((prev) => [...prev, event]);

            if (event.step === "complete" && event.detail) {
              setDraft(event.detail);
            }
            if (event.step === "error") {
              setError(event.message);
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch (err: any) {
      setError(err.message || "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    handleGenerateWithPrompt(prompt);
  }

  async function handleSave() {
    if (!draft) return;
    try {
      await api.post("/api/ads/prompt/save-draft", { draft });
      alert("Draft saved successfully!");
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleLaunch() {
    if (!draft) return;
    try {
      const result = await api.post("/api/ads/prompt/approve-launch", { draft });
      alert(`Campaign approved and launching! (ID: ${result.id})`);
    } catch (err: any) {
      setError(err.message);
    }
  }

  function toggleGroup(idx: number) {
    const next = new Set(expandedGroups);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setExpandedGroups(next);
  }

  const doneSteps = logEntries.filter((e) => e.status === "done" && e.step !== "ai_copy_result");
  const isComplete = logEntries.some((e) => e.step === "complete");

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Command Console</h1>
          <p className="text-muted-foreground">Describe what you want and let AI build your campaign</p>
        </div>

        {/* Prompt Input */}
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Example: Launch an emergency locksmith campaign targeting Dallas, Fort Worth, and Arlington. Focus on lockout services with a $50/day budget. Include our $20 off offer."
                className="w-full min-h-[120px] rounded-lg border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  onClick={handleRefine}
                  disabled={loading || refining || !prompt.trim()}
                >
                  {refining ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" /> Refining...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4" /> Refine with AI
                    </span>
                  )}
                </Button>
                <Button onClick={handleGenerate} disabled={loading || refining || !prompt.trim()}>
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" /> Generating...
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Wand2 className="w-4 h-4" /> Generate Campaign
                    </span>
                  )}
                </Button>
                <span className="text-xs text-muted-foreground">
                  Refine first to let AI expand your idea, or generate directly
                </span>
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </CardContent>
        </Card>

        {/* AI Refinement Panel */}
        {refinement && (
          <Card className="border-blue-200 bg-gradient-to-br from-blue-50/50 to-indigo-50/30">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-blue-600" />
                  <CardTitle className="text-base text-blue-900">AI Refined Campaign Brief</CardTitle>
                  {refinement.ai_powered && (
                    <Badge className="text-xs bg-blue-100 text-blue-700 border-blue-200">
                      AI Powered
                    </Badge>
                  )}
                </div>
                <Button variant="ghost" size="sm" onClick={handleDismissRefinement}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <p className="text-sm text-blue-700 mt-1">
                Review and edit the expanded prompt below. When you're happy, confirm to generate.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Editable refined prompt */}
              <div>
                <label className="text-xs font-semibold text-blue-800 uppercase tracking-wide mb-1 block">
                  Campaign Brief (editable)
                </label>
                <textarea
                  value={refinedPrompt}
                  onChange={(e) => setRefinedPrompt(e.target.value)}
                  className="w-full min-h-[100px] rounded-lg border border-blue-200 bg-white px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
                />
              </div>

              {/* Detected metadata */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {refinement.detected_services && refinement.detected_services.length > 0 && (
                  <div className="bg-white rounded-lg border p-2.5">
                    <div className="flex items-center gap-1.5 mb-1">
                      <Tag className="w-3.5 h-3.5 text-slate-500" />
                      <span className="text-[11px] font-semibold text-slate-500 uppercase">Services</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {refinement.detected_services.map((s, i) => (
                        <span key={i} className="text-xs bg-slate-100 rounded px-1.5 py-0.5">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                {refinement.detected_locations && refinement.detected_locations.length > 0 && (
                  <div className="bg-white rounded-lg border p-2.5">
                    <div className="flex items-center gap-1.5 mb-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-500" />
                      <span className="text-[11px] font-semibold text-slate-500 uppercase">Locations</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {refinement.detected_locations.map((l, i) => (
                        <span key={i} className="text-xs bg-slate-100 rounded px-1.5 py-0.5">{l}</span>
                      ))}
                    </div>
                  </div>
                )}
                {refinement.detected_goal && (
                  <div className="bg-white rounded-lg border p-2.5">
                    <div className="flex items-center gap-1.5 mb-1">
                      <Target className="w-3.5 h-3.5 text-slate-500" />
                      <span className="text-[11px] font-semibold text-slate-500 uppercase">Goal</span>
                    </div>
                    <span className="text-xs font-medium capitalize">{refinement.detected_goal}</span>
                  </div>
                )}
                {refinement.suggested_budget && (
                  <div className="bg-white rounded-lg border p-2.5">
                    <div className="flex items-center gap-1.5 mb-1">
                      <DollarSign className="w-3.5 h-3.5 text-slate-500" />
                      <span className="text-[11px] font-semibold text-slate-500 uppercase">Budget</span>
                    </div>
                    <span className="text-xs font-medium">{refinement.suggested_budget}</span>
                  </div>
                )}
              </div>

              {/* Overlap warning */}
              {refinement.overlap_warning && (
                <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-amber-800">{refinement.overlap_warning}</p>
                </div>
              )}

              {/* Suggestions */}
              {refinement.suggestions && refinement.suggestions.length > 0 && (
                <div className="bg-white border rounded-lg p-3">
                  <div className="flex items-center gap-1.5 mb-2">
                    <Lightbulb className="w-4 h-4 text-amber-500" />
                    <span className="text-xs font-semibold text-slate-600 uppercase">Suggestions</span>
                  </div>
                  <ul className="space-y-1">
                    {refinement.suggestions.map((s, i) => (
                      <li key={i} className="text-sm text-slate-700 flex items-start gap-2">
                        <span className="text-blue-400 mt-1">-</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex items-center gap-3 pt-2">
                <Button onClick={handleConfirmAndGenerate} disabled={loading || !refinedPrompt.trim()}>
                  <span className="flex items-center gap-2">
                    <Wand2 className="w-4 h-4" /> Confirm & Generate
                  </span>
                </Button>
                <Button variant="outline" onClick={handleUseRefined}>
                  <span className="flex items-center gap-2">
                    <ArrowRight className="w-4 h-4" /> Use as Prompt
                  </span>
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => { setRefinedPrompt(refinedPrompt); handleRefine(); }}
                  disabled={refining}
                >
                  <span className="flex items-center gap-2">
                    <RotateCcw className="w-4 h-4" /> Re-refine
                  </span>
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Process Log */}
        {logEntries.length > 0 && (
          <Card className="overflow-hidden">
            <CardHeader className="pb-3 cursor-pointer" onClick={() => setShowLog(!showLog)}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">Generation Process</CardTitle>
                  {loading && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
                  {isComplete && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                  <span className="text-xs text-muted-foreground">
                    {doneSteps.length} steps completed
                  </span>
                </div>
                {showLog ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </div>
            </CardHeader>
            {showLog && (
              <CardContent className="pt-0">
                <div className="space-y-1 max-h-[400px] overflow-y-auto pr-2">
                  {logEntries.map((entry, i) => {
                    const Icon = STEP_ICONS[entry.step] || CheckCircle2;
                    const isRunning = entry.status === "running";
                    const isDone = entry.status === "done";
                    const isError = entry.status === "error";
                    const isAiResult = entry.step === "ai_copy_result";
                    const hasAiPrompt = isAiResult && entry.detail?.ai_prompt;
                    const promptKey = `${i}`;

                    return (
                      <div key={i}>
                        <div
                          className={`flex items-start gap-3 py-2 px-3 rounded-lg text-sm transition-colors ${
                            isRunning ? "bg-blue-50 border border-blue-100" :
                            isError ? "bg-red-50 border border-red-100" :
                            isAiResult ? "bg-purple-50/50 border border-purple-100 ml-6" :
                            isDone ? "bg-slate-50" : ""
                          }`}
                        >
                          <div className="mt-0.5 flex-shrink-0">
                            {isRunning ? (
                              <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                            ) : isError ? (
                              <AlertCircle className="w-4 h-4 text-red-500" />
                            ) : (
                              <Icon className={`w-4 h-4 ${isAiResult ? "text-purple-500" : "text-green-500"}`} />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={`${isRunning ? "text-blue-700 font-medium" : isError ? "text-red-700" : "text-slate-700"}`}>
                              {entry.message}
                            </p>
                            {entry.detail && !isAiResult && entry.step !== "complete" && (
                              <p className="text-xs text-muted-foreground mt-0.5 truncate">
                                {typeof entry.detail === "object" ? JSON.stringify(entry.detail) : entry.detail}
                              </p>
                            )}
                          </div>
                          {hasAiPrompt && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="flex-shrink-0 h-7 px-2 text-xs text-purple-600 hover:text-purple-800"
                              onClick={(e) => {
                                e.stopPropagation();
                                setAiPromptExpanded(aiPromptExpanded === promptKey ? null : promptKey);
                              }}
                            >
                              {aiPromptExpanded === promptKey ? (
                                <><EyeOff className="w-3 h-3 mr-1" /> Hide AI</>
                              ) : (
                                <><Eye className="w-3 h-3 mr-1" /> View AI</>
                              )}
                            </Button>
                          )}
                        </div>

                        {/* Expanded AI Prompt / Response */}
                        {hasAiPrompt && aiPromptExpanded === promptKey && (
                          <div className="ml-6 mt-1 mb-2 rounded-lg border border-purple-200 bg-purple-50/30 overflow-hidden">
                            <div className="p-3 border-b border-purple-100">
                              <div className="flex items-center gap-2 mb-2">
                                <Brain className="w-4 h-4 text-purple-600" />
                                <span className="text-xs font-semibold text-purple-700 uppercase tracking-wide">
                                  Prompt sent to OpenAI
                                </span>
                              </div>
                              <pre className="text-xs text-slate-700 whitespace-pre-wrap font-mono bg-white rounded p-3 border max-h-[300px] overflow-y-auto">
                                {entry.detail.ai_prompt}
                              </pre>
                            </div>
                            {entry.detail.ai_raw_response && (
                              <div className="p-3">
                                <div className="flex items-center gap-2 mb-2">
                                  <Sparkles className="w-4 h-4 text-purple-600" />
                                  <span className="text-xs font-semibold text-purple-700 uppercase tracking-wide">
                                    Raw AI Response
                                  </span>
                                </div>
                                <pre className="text-xs text-slate-700 whitespace-pre-wrap font-mono bg-white rounded p-3 border max-h-[200px] overflow-y-auto">
                                  {typeof entry.detail.ai_raw_response === "string"
                                    ? entry.detail.ai_raw_response
                                    : JSON.stringify(entry.detail.ai_raw_response, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <div ref={logEndRef} />
                </div>
              </CardContent>
            )}
          </Card>
        )}

        {/* Campaign Preview */}
        {draft && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Campaign Preview</h2>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleSave}>
                  <Save className="w-4 h-4 mr-2" /> Save Draft
                </Button>
                <Button onClick={handleLaunch}>
                  <Rocket className="w-4 h-4 mr-2" /> Approve & Launch
                </Button>
              </div>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">{draft.campaign?.name}</CardTitle>
                <CardDescription className="flex items-center gap-2">
                  <Badge variant="secondary">{draft.campaign?.type}</Badge>
                  <Badge variant="outline">{draft.campaign?.bidding_strategy}</Badge>
                  <span>${draft.campaign?.budget_daily_usd}/day</span>
                </CardDescription>
              </CardHeader>
              <CardContent>
                {draft.reasoning && (
                  <div className="mb-4 p-3 rounded-lg bg-blue-50 border border-blue-100 text-sm">
                    <strong>AI Reasoning:</strong> {draft.reasoning.campaign_type}
                    {draft.reasoning.learnings_applied > 0 && (
                      <span className="ml-2 text-blue-600">
                        ({draft.reasoning.learnings_applied} cross-tenant learnings applied)
                      </span>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {draft.ad_groups?.map((ag: any, idx: number) => (
              <Card key={idx}>
                <CardHeader className="cursor-pointer" onClick={() => toggleGroup(idx)}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-base">{ag.name}</CardTitle>
                      {ag.ads?.[0]?.generated_by === "openai" && (
                        <Badge variant="secondary" className="text-xs bg-purple-100 text-purple-700">
                          <Sparkles className="w-3 h-3 mr-1" /> AI Generated
                        </Badge>
                      )}
                    </div>
                    {expandedGroups.has(idx) ? (
                      <ChevronUp className="w-5 h-5 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>
                {expandedGroups.has(idx) && (
                  <CardContent className="space-y-4">
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Keywords ({ag.keywords?.length || 0})</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {ag.keywords?.map((kw: any, ki: number) => (
                          <Badge key={ki} variant={kw.match_type === "EXACT" ? "default" : "secondary"}>
                            {kw.match_type === "EXACT" ? `[${kw.text}]` : kw.match_type === "PHRASE" ? `"${kw.text}"` : kw.text}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {ag.negatives && ag.negatives.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold mb-2">Negatives ({ag.negatives.length})</h4>
                        <div className="flex flex-wrap gap-1.5">
                          {ag.negatives.slice(0, 15).map((n: any, ni: number) => (
                            <Badge key={ni} variant="destructive" className="text-xs">
                              -{n.text}
                            </Badge>
                          ))}
                          {ag.negatives.length > 15 && (
                            <span className="text-xs text-muted-foreground">+{ag.negatives.length - 15} more</span>
                          )}
                        </div>
                      </div>
                    )}

                    {ag.ads?.map((ad: any, ai: number) => {
                      const hPins = ad.pinning?.headline_pins || {};
                      const dPins = ad.pinning?.description_pins || {};
                      const pinnedHIdxs = new Set(Object.values(hPins).map(Number));
                      const pinnedDIdxs = new Set(Object.values(dPins).map(Number));

                      return (
                        <div key={ai} className="border rounded-lg p-4 bg-slate-50 space-y-3">
                          <div className="flex items-center justify-between">
                            <h4 className="text-sm font-semibold">Responsive Search Ad</h4>
                            {ad.generated_by === "openai" && (
                              <span className="text-xs text-purple-600 font-medium">Powered by OpenAI</span>
                            )}
                          </div>

                          {ad.ai_rationale && (
                            <div className="text-xs bg-purple-50 border border-purple-100 rounded p-2 text-purple-800">
                              <strong>AI Strategy:</strong> {ad.ai_rationale}
                            </div>
                          )}

                          <div>
                            <span className="text-xs text-muted-foreground">Headlines ({ad.headlines?.length || 0}):</span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {ad.headlines?.map((h: string, hi: number) => {
                                const overLimit = h.length > 30;
                                const isPinned = pinnedHIdxs.has(hi);
                                const pinPos = Object.entries(hPins).find(([, v]) => Number(v) === hi);
                                return (
                                  <span
                                    key={hi}
                                    className={`text-sm border rounded px-2 py-0.5 ${
                                      overLimit ? "bg-red-50 border-red-300" :
                                      isPinned ? "bg-blue-50 border-blue-300" : "bg-white"
                                    }`}
                                  >
                                    {isPinned && pinPos && (
                                      <span className="text-[10px] font-bold text-blue-600 mr-1">📌P{pinPos[0]}</span>
                                    )}
                                    {h}
                                    <span className={`text-[10px] ml-1 ${overLimit ? "text-red-600 font-bold" : "text-muted-foreground"}`}>
                                      {h.length}/30
                                    </span>
                                  </span>
                                );
                              })}
                            </div>
                          </div>

                          <div>
                            <span className="text-xs text-muted-foreground">Descriptions ({ad.descriptions?.length || 0}):</span>
                            {ad.descriptions?.map((d: string, di: number) => {
                              const overLimit = d.length > 90;
                              const isPinned = pinnedDIdxs.has(di);
                              const pinPos = Object.entries(dPins).find(([, v]) => Number(v) === di);
                              return (
                                <p
                                  key={di}
                                  className={`text-sm mt-1 border rounded px-2 py-1 ${
                                    overLimit ? "bg-red-50 border-red-300" :
                                    isPinned ? "bg-blue-50 border-blue-300" : "bg-white"
                                  }`}
                                >
                                  {isPinned && pinPos && (
                                    <span className="text-[10px] font-bold text-blue-600 mr-1">📌D{pinPos[0]}</span>
                                  )}
                                  {d}
                                  <span className={`text-[10px] ml-1 ${overLimit ? "text-red-600 font-bold" : "text-muted-foreground"}`}>
                                    ({d.length}/90)
                                  </span>
                                </p>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}

                    {(ag.llm_sitelinks?.length > 0 || ag.llm_callouts?.length > 0) && (
                      <div className="border rounded-lg p-4 bg-green-50/50 space-y-3">
                        <h4 className="text-sm font-semibold text-green-800">AI-Generated Extensions</h4>
                        {ag.llm_sitelinks?.length > 0 && (
                          <div>
                            <span className="text-xs text-muted-foreground">Sitelinks ({ag.llm_sitelinks.length}):</span>
                            <div className="grid grid-cols-2 gap-2 mt-1">
                              {ag.llm_sitelinks.map((sl: any, si: number) => (
                                <div key={si} className="text-sm bg-white border rounded p-2">
                                  <div className="font-medium text-blue-600">{sl.text} <span className="text-[10px] text-muted-foreground">{sl.text?.length}/25</span></div>
                                  <div className="text-xs text-muted-foreground">{sl.desc1 || sl.description}</div>
                                  {sl.desc2 && <div className="text-xs text-muted-foreground">{sl.desc2}</div>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {ag.llm_callouts?.length > 0 && (
                          <div>
                            <span className="text-xs text-muted-foreground">Callouts ({ag.llm_callouts.length}):</span>
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {ag.llm_callouts.map((c: string, ci: number) => (
                                <Badge key={ci} variant="outline" className="bg-white">
                                  {c} <span className="text-[10px] text-muted-foreground ml-1">{c.length}/25</span>
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                )}
              </Card>
            ))}

            {draft.extensions && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Extensions (Template)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {draft.extensions.sitelinks && (
                    <div>
                      <h4 className="text-sm font-semibold mb-1">Sitelinks</h4>
                      <div className="grid grid-cols-2 gap-2">
                        {draft.extensions.sitelinks.map((sl: any, i: number) => (
                          <div key={i} className="text-sm border rounded p-2">
                            <div className="font-medium text-blue-600">{sl.text}</div>
                            <div className="text-xs text-muted-foreground">{sl.description || sl.desc1}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {draft.extensions.callouts && (
                    <div>
                      <h4 className="text-sm font-semibold mb-1">Callouts</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {draft.extensions.callouts.map((c: string, i: number) => (
                          <Badge key={i} variant="outline">{c}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
