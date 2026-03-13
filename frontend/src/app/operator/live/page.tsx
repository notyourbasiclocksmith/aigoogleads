"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { AppLayout } from "@/components/layout/sidebar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Brain, Zap, Play, Loader2, CheckCircle2, XCircle, AlertTriangle,
  ChevronDown, ChevronRight, DollarSign, TrendingUp, TrendingDown,
  Target, Shield, Clock, RotateCcw, Activity, Eye, RefreshCw,
  ArrowUpRight, ArrowDownRight, Minus, BookOpen, BarChart3,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────

interface LiveStatus {
  autonomy_mode: string;
  risk_tolerance: string;
  latest_cycle: CycleSummary | null;
  week_stats: {
    total_cycles: number;
    total_actions_executed: number;
    total_actions_blocked: number;
    projected_monthly_savings: number;
  };
}

interface CycleSummary {
  id: string;
  trigger: string;
  status: string;
  problems_detected: number;
  actions_generated?: number;
  actions_approved?: number;
  actions_executed: number;
  actions_blocked: number;
  projected_monthly_savings: number;
  projected_conversion_lift?: number;
  feedback_status: string | null;
  started_at: string | null;
  completed_at: string | null;
}

interface CycleDetail extends CycleSummary {
  snapshot: any;
  problems: any[];
  actions: any[];
  feedback: any;
  feedback_evaluated_at: string | null;
  scan_id: string | null;
  change_set_id: string | null;
  error_message: string | null;
}

interface Learning {
  id: string;
  pattern: string;
  action_type: string;
  result: string | null;
  confidence_score: number;
  observation_count: number;
  pattern_detail: any;
  result_detail: any;
  updated_at: string | null;
}

// ── Status colors and labels ──────────────────────────────────────────────

const CYCLE_STATUS: Record<string, { label: string; color: string; bg: string }> = {
  running: { label: "Running", color: "text-blue-600", bg: "bg-blue-50 border-blue-200" },
  completed: { label: "Completed", color: "text-emerald-600", bg: "bg-emerald-50 border-emerald-200" },
  completed_no_actions: { label: "No Actions Needed", color: "text-slate-500", bg: "bg-slate-50 border-slate-200" },
  failed: { label: "Failed", color: "text-red-600", bg: "bg-red-50 border-red-200" },
  skipped: { label: "Skipped", color: "text-amber-600", bg: "bg-amber-50 border-amber-200" },
};

const FEEDBACK_STATUS: Record<string, { label: string; color: string; icon: any }> = {
  pending_review: { label: "Pending Review", color: "text-amber-600", icon: Clock },
  improved: { label: "Improved", color: "text-emerald-600", icon: TrendingUp },
  degraded: { label: "Degraded", color: "text-red-600", icon: TrendingDown },
  neutral: { label: "Neutral", color: "text-slate-500", icon: Minus },
  rolled_back: { label: "Rolled Back", color: "text-red-500", icon: RotateCcw },
};

const AUTONOMY_LABELS: Record<string, { label: string; color: string; desc: string }> = {
  suggest: { label: "Suggest Only", color: "text-slate-600", desc: "AI suggests changes but takes no action" },
  semi_auto: { label: "Semi-Auto", color: "text-amber-600", desc: "AI auto-applies low-risk changes only" },
  full_auto: { label: "Full Auto", color: "text-emerald-600", desc: "AI auto-applies low + medium risk changes" },
};

// ═══════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════

export default function OperatorLivePage() {
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [cycles, setCycles] = useState<CycleSummary[]>([]);
  const [learnings, setLearnings] = useState<Learning[]>([]);
  const [selectedCycle, setSelectedCycle] = useState<CycleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [rollingBack, setRollingBack] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"cycles" | "learnings">("cycles");
  const [expandedCycle, setExpandedCycle] = useState<string | null>(null);

  // ── Load data ─────────────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    try {
      const [s, c, l] = await Promise.all([
        api.get("/api/v2/operator/live/status"),
        api.get("/api/v2/operator/live/cycles?limit=20"),
        api.get("/api/v2/operator/live/learnings?limit=30"),
      ]);
      setStatus(s);
      setCycles(c);
      setLearnings(l);
      setError("");
    } catch (e: any) {
      setError(e.message || "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // ── Trigger manual cycle ──────────────────────────────────────────────
  const triggerCycle = async () => {
    setTriggering(true);
    setError("");
    try {
      await api.post("/api/v2/operator/live/trigger");
      setTimeout(loadData, 3000);
    } catch (e: any) {
      setError(e.message || "Failed to trigger cycle");
    }
    setTriggering(false);
  };

  // ── Rollback ──────────────────────────────────────────────────────────
  const rollbackCycle = async (cycleId: string) => {
    if (!confirm("Are you sure you want to rollback all changes from this cycle?")) return;
    setRollingBack(cycleId);
    try {
      await api.post(`/api/v2/operator/live/cycle/${cycleId}/rollback`);
      setTimeout(loadData, 2000);
    } catch (e: any) {
      setError(e.message || "Failed to rollback");
    }
    setRollingBack(null);
  };

  // ── Load cycle detail ─────────────────────────────────────────────────
  const loadCycleDetail = async (cycleId: string) => {
    if (expandedCycle === cycleId) {
      setExpandedCycle(null);
      setSelectedCycle(null);
      return;
    }
    try {
      const detail = await api.get(`/api/v2/operator/live/cycle/${cycleId}`);
      setSelectedCycle(detail);
      setExpandedCycle(cycleId);
    } catch {
      // ignore
    }
  };

  // ── Helpers ───────────────────────────────────────────────────────────
  const formatTime = (iso: string | null) => {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  const formatTimeAgo = (iso: string | null) => {
    if (!iso) return "never";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  // ═════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════════════════════════════

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-5 h-5 animate-spin text-slate-300" />
        </div>
      </AppLayout>
    );
  }

  const autonomy = AUTONOMY_LABELS[status?.autonomy_mode || "suggest"];

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto space-y-8">

        {/* ── Header ───────────────────────────────────────────────────── */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight text-slate-900 flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center">
                <Activity className="w-5 h-5 text-emerald-600" />
              </div>
              Autonomous Optimizer
            </h1>
            <p className="text-[13px] text-slate-400 mt-1 ml-[46px]">
              AI-powered optimization running every 4 hours
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              onClick={loadData}
              variant="outline"
              size="sm"
              className="rounded-xl text-[13px] h-9"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
            </Button>
            <Button
              onClick={triggerCycle}
              disabled={triggering || status?.autonomy_mode === "suggest"}
              className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-[13px] h-9 font-semibold"
            >
              {triggering ? (
                <><Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" /> Triggering...</>
              ) : (
                <><Play className="w-3.5 h-3.5 mr-2" /> Run Now</>
              )}
            </Button>
          </div>
        </div>

        {/* ── Error ────────────────────────────────────────────────────── */}
        {error && (
          <div className="px-4 py-3 rounded-2xl bg-red-50/70 border border-red-100/60 flex items-start gap-3">
            <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-[13px] text-red-600">{error}</p>
          </div>
        )}

        {/* ── Autonomy Mode Banner ─────────────────────────────────────── */}
        <Card className="border-0 px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              status?.autonomy_mode === "full_auto" ? "bg-emerald-50" :
              status?.autonomy_mode === "semi_auto" ? "bg-amber-50" : "bg-slate-50"
            }`}>
              <Shield className={`w-5 h-5 ${autonomy.color}`} />
            </div>
            <div>
              <p className={`text-[14px] font-semibold ${autonomy.color}`}>{autonomy.label}</p>
              <p className="text-[12px] text-slate-400">{autonomy.desc}</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-[12px] text-slate-400">
            <span>Risk: <strong className="text-slate-600">{status?.risk_tolerance || "low"}</strong></span>
            {status?.latest_cycle && (
              <span>Last: <strong className="text-slate-600">{formatTimeAgo(status.latest_cycle.completed_at || status.latest_cycle.started_at)}</strong></span>
            )}
          </div>
        </Card>

        {/* ── Stats Cards ──────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
          <StatCard
            label="Cycles (7d)"
            value={status?.week_stats.total_cycles || 0}
            icon={Activity}
            color="blue"
          />
          <StatCard
            label="Actions Executed"
            value={status?.week_stats.total_actions_executed || 0}
            icon={Zap}
            color="emerald"
          />
          <StatCard
            label="Actions Blocked"
            value={status?.week_stats.total_actions_blocked || 0}
            icon={Shield}
            color="amber"
          />
          <StatCard
            label="Projected Savings"
            value={`$${(status?.week_stats.projected_monthly_savings || 0).toLocaleString()}`}
            icon={DollarSign}
            color="purple"
            subtitle="/month"
          />
        </div>

        {/* ── Latest Cycle Summary ─────────────────────────────────────── */}
        {status?.latest_cycle && (
          <Card className="border-0 px-5 py-5 bg-gradient-to-br from-slate-50/60 to-blue-50/20">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
                  <Brain className="w-5 h-5 text-blue-600" />
                </div>
                <div>
                  <h3 className="text-[14px] font-semibold text-slate-900">Latest Optimization Cycle</h3>
                  <p className="text-[12px] text-slate-400 mt-0.5">
                    {formatTime(status.latest_cycle.started_at)} · {status.latest_cycle.trigger}
                  </p>
                </div>
              </div>
              <CycleStatusBadge status={status.latest_cycle.status} />
            </div>

            <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-3">
              <MiniStat label="Problems Found" value={status.latest_cycle.problems_detected} />
              <MiniStat label="Actions Executed" value={status.latest_cycle.actions_executed} color="emerald" />
              <MiniStat label="Blocked by Guards" value={status.latest_cycle.actions_blocked} color="amber" />
              <MiniStat label="Projected Savings" value={`$${status.latest_cycle.projected_monthly_savings}`} color="purple" />
              <div>
                <p className="text-[11px] text-slate-400 font-medium">Feedback</p>
                {status.latest_cycle.feedback_status ? (
                  <FeedbackBadge status={status.latest_cycle.feedback_status} />
                ) : (
                  <p className="text-[13px] font-medium text-slate-300">—</p>
                )}
              </div>
            </div>
          </Card>
        )}

        {/* ── Tab Switcher ─────────────────────────────────────────────── */}
        <div className="flex gap-1 bg-slate-100/80 rounded-xl p-1 w-fit">
          <button
            onClick={() => setActiveTab("cycles")}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all duration-200 ${
              activeTab === "cycles"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            <Activity className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />
            Optimization Cycles
          </button>
          <button
            onClick={() => setActiveTab("learnings")}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all duration-200 ${
              activeTab === "learnings"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-400 hover:text-slate-600"
            }`}
          >
            <BookOpen className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />
            Learnings
          </button>
        </div>

        {/* ── Cycles Tab ───────────────────────────────────────────────── */}
        {activeTab === "cycles" && (
          <div className="space-y-3">
            {cycles.length === 0 ? (
              <Card className="border-0 p-12 text-center">
                <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <Activity className="w-6 h-6 text-slate-300" />
                </div>
                <p className="text-[13px] text-slate-500">No optimization cycles yet</p>
                <p className="text-[12px] text-slate-400 mt-1">
                  {status?.autonomy_mode === "suggest"
                    ? "Switch to semi-auto or full-auto mode to enable autonomous optimization"
                    : "The optimizer runs every 4 hours, or click \"Run Now\" to start one"}
                </p>
              </Card>
            ) : (
              cycles.map(cycle => (
                <Card key={cycle.id} className="border-0 overflow-hidden">
                  {/* Cycle row */}
                  <button
                    onClick={() => loadCycleDetail(cycle.id)}
                    className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50/50 transition-colors text-left"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <CycleStatusDot status={cycle.status} />
                      <div className="min-w-0">
                        <p className="text-[13px] font-medium text-slate-900 truncate">
                          {cycle.trigger === "scheduled" ? "Scheduled" : "Manual"} Cycle
                          <span className="text-slate-400 font-normal ml-2 text-[12px]">
                            {formatTime(cycle.started_at)}
                          </span>
                        </p>
                        <div className="flex items-center gap-3 mt-0.5 text-[11px] text-slate-400">
                          <span>{cycle.problems_detected} problems</span>
                          <span className="text-emerald-500">{cycle.actions_executed} executed</span>
                          {cycle.actions_blocked > 0 && (
                            <span className="text-amber-500">{cycle.actions_blocked} blocked</span>
                          )}
                          {cycle.projected_monthly_savings > 0 && (
                            <span className="text-purple-500">${cycle.projected_monthly_savings}/mo savings</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {cycle.feedback_status && <FeedbackBadge status={cycle.feedback_status} />}
                      <CycleStatusBadge status={cycle.status} />
                      {expandedCycle === cycle.id ? (
                        <ChevronDown className="w-4 h-4 text-slate-300" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-300" />
                      )}
                    </div>
                  </button>

                  {/* Expanded detail */}
                  {expandedCycle === cycle.id && selectedCycle && (
                    <div className="border-t border-slate-100/60 px-5 py-5 space-y-5 bg-slate-50/30">
                      {/* Snapshot metrics */}
                      {selectedCycle.snapshot && Object.keys(selectedCycle.snapshot).length > 0 && (
                        <div>
                          <h4 className="text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-2.5">Account Snapshot</h4>
                          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                            {Object.entries(selectedCycle.snapshot).map(([key, val]) => (
                              <div key={key} className="p-2.5 rounded-xl bg-white border border-slate-100/60 text-center">
                                <p className="text-[11px] text-slate-400">{key.replace(/_/g, " ")}</p>
                                <p className="text-[13px] font-semibold text-slate-800 mt-0.5">
                                  {typeof val === "number"
                                    ? key.includes("spend") || key.includes("cost")
                                      ? `$${val.toLocaleString()}`
                                      : val.toLocaleString()
                                    : String(val)}
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Actions taken */}
                      {selectedCycle.actions && selectedCycle.actions.length > 0 && (
                        <div>
                          <h4 className="text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-2.5">Actions Taken</h4>
                          <div className="space-y-1.5">
                            {selectedCycle.actions.map((action: any, i: number) => (
                              <div key={i} className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white border border-slate-100/60 text-[13px]">
                                <ActionIcon type={action.action_type} />
                                <div className="flex-1 min-w-0">
                                  <span className="font-medium text-slate-800">{action.action_type?.replace(/_/g, " ")}</span>
                                  {action.entity_name && (
                                    <span className="text-slate-400 ml-2 truncate">{action.entity_name}</span>
                                  )}
                                </div>
                                <RiskBadge level={action.risk_level} />
                                <span className={`text-[11px] font-medium ${
                                  action.status === "executed" ? "text-emerald-500" :
                                  action.status === "blocked" ? "text-amber-500" : "text-slate-400"
                                }`}>{action.status}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Feedback detail */}
                      {selectedCycle.feedback && Object.keys(selectedCycle.feedback).length > 0 && (
                        <div>
                          <h4 className="text-[11px] font-medium text-slate-400 uppercase tracking-wider mb-2.5">Feedback (24h)</h4>
                          <div className="p-4 rounded-xl bg-white border border-slate-100/60">
                            {selectedCycle.feedback.delta && (
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[13px]">
                                {selectedCycle.feedback.delta.cost_pct !== undefined && (
                                  <DeltaStat label="Cost" value={selectedCycle.feedback.delta.cost_pct} invert />
                                )}
                                {selectedCycle.feedback.delta.conversions_pct !== undefined && (
                                  <DeltaStat label="Conversions" value={selectedCycle.feedback.delta.conversions_pct} />
                                )}
                                {selectedCycle.feedback.delta.cpa_pct !== undefined && (
                                  <DeltaStat label="CPA" value={selectedCycle.feedback.delta.cpa_pct} invert />
                                )}
                                {selectedCycle.feedback.delta.clicks_pct !== undefined && (
                                  <DeltaStat label="Clicks" value={selectedCycle.feedback.delta.clicks_pct} />
                                )}
                              </div>
                            )}
                            {selectedCycle.feedback.verdict && (
                              <p className="text-[12px] text-slate-400 mt-3">
                                Verdict: <strong className="text-slate-600">{selectedCycle.feedback.verdict}</strong>
                                {selectedCycle.feedback.auto_rollback && (
                                  <span className="text-red-500 ml-2">Auto-rollback triggered</span>
                                )}
                              </p>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Error */}
                      {selectedCycle.error_message && (
                        <div className="px-4 py-3 rounded-xl bg-red-50/70 border border-red-100/60 text-[13px] text-red-600">
                          {selectedCycle.error_message}
                        </div>
                      )}

                      {/* Rollback button */}
                      {cycle.status === "completed" && cycle.feedback_status !== "rolled_back" && (
                        <div className="flex justify-end">
                          <Button
                            onClick={() => rollbackCycle(cycle.id)}
                            disabled={rollingBack === cycle.id}
                            variant="outline"
                            size="sm"
                            className="text-red-500 border-red-200 hover:bg-red-50 rounded-xl text-[12px]"
                          >
                            {rollingBack === cycle.id ? (
                              <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Rolling back...</>
                            ) : (
                              <><RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Rollback Changes</>
                            )}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              ))
            )}
          </div>
        )}

        {/* ── Learnings Tab ──────────────────────────────────────────── */}
        {activeTab === "learnings" && (
          <div className="space-y-3">
            {learnings.length === 0 ? (
              <Card className="border-0 p-12 text-center">
                <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <BookOpen className="w-6 h-6 text-slate-300" />
                </div>
                <p className="text-[13px] text-slate-500">No learnings recorded yet</p>
                <p className="text-[12px] text-slate-400 mt-1">
                  Learnings are recorded after optimization cycles complete and feedback is evaluated
                </p>
              </Card>
            ) : (
              <Card className="border-0 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="px-4 py-3 text-left text-[11px] font-medium text-slate-400 uppercase tracking-wider">Pattern</th>
                        <th className="px-4 py-3 text-left text-[11px] font-medium text-slate-400 uppercase tracking-wider">Action</th>
                        <th className="px-4 py-3 text-center text-[11px] font-medium text-slate-400 uppercase tracking-wider">Result</th>
                        <th className="px-4 py-3 text-center text-[11px] font-medium text-slate-400 uppercase tracking-wider">Confidence</th>
                        <th className="px-4 py-3 text-center text-[11px] font-medium text-slate-400 uppercase tracking-wider">Observations</th>
                        <th className="px-4 py-3 text-right text-[11px] font-medium text-slate-400 uppercase tracking-wider">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {learnings.map(l => (
                        <tr key={l.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/50 transition-colors">
                          <td className="px-4 py-3">
                            <span className="font-medium text-slate-800">{l.pattern.replace(/_/g, " ")}</span>
                          </td>
                          <td className="px-4 py-3 text-slate-500">
                            {l.action_type.replace(/_/g, " ")}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {l.result ? <FeedbackBadge status={l.result} /> : <span className="text-slate-300">—</span>}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <ConfidenceBar score={l.confidence_score} />
                          </td>
                          <td className="px-4 py-3 text-center text-slate-500">
                            {l.observation_count}
                          </td>
                          <td className="px-4 py-3 text-right text-[11px] text-slate-400">
                            {formatTimeAgo(l.updated_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </AppLayout>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════

function StatCard({ label, value, icon: Icon, color, subtitle }: {
  label: string; value: number | string; icon: any; color: string; subtitle?: string;
}) {
  const colors: Record<string, string> = {
    blue: "bg-blue-50 text-blue-600",
    emerald: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    purple: "bg-purple-50 text-purple-600",
    red: "bg-red-50 text-red-600",
  };
  return (
    <Card className="border-0 p-5">
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${colors[color]}`}>
          <Icon className="w-[18px] h-[18px]" />
        </div>
        <div>
          <p className="text-[12px] text-slate-400 font-medium">{label}</p>
          <p className="text-[18px] font-semibold tracking-tight text-slate-900">
            {value}
            {subtitle && <span className="text-[11px] font-normal text-slate-400 ml-1">{subtitle}</span>}
          </p>
        </div>
      </div>
    </Card>
  );
}

function MiniStat({ label, value, color }: { label: string; value: number | string; color?: string }) {
  const c = color === "emerald" ? "text-emerald-600" : color === "amber" ? "text-amber-600" : color === "purple" ? "text-purple-600" : "text-slate-800";
  return (
    <div>
      <p className="text-[11px] text-slate-400 font-medium">{label}</p>
      <p className={`text-[13px] font-semibold ${c}`}>{value}</p>
    </div>
  );
}

function CycleStatusBadge({ status }: { status: string }) {
  const s = CYCLE_STATUS[status] || CYCLE_STATUS.running;
  return (
    <span className={`px-2.5 py-1 rounded-lg text-[11px] font-medium border ${s.bg} ${s.color}`}>
      {s.label}
    </span>
  );
}

function CycleStatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-blue-500 animate-pulse",
    completed: "bg-emerald-500",
    completed_no_actions: "bg-slate-400",
    failed: "bg-red-500",
    skipped: "bg-amber-400",
  };
  return <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${colors[status] || "bg-slate-400"}`} />;
}

function FeedbackBadge({ status }: { status: string }) {
  const f = FEEDBACK_STATUS[status];
  if (!f) return <span className="text-[11px] text-slate-400">{status}</span>;
  const Icon = f.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-medium ${f.color}`}>
      <Icon className="w-3 h-3" />
      {f.label}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    LOW: "bg-emerald-50 text-emerald-600",
    MEDIUM: "bg-amber-50 text-amber-600",
    HIGH: "bg-red-50 text-red-600",
    low: "bg-emerald-50 text-emerald-600",
    medium: "bg-amber-50 text-amber-600",
    high: "bg-red-50 text-red-600",
  };
  return (
    <span className={`px-2 py-0.5 rounded-lg text-[11px] font-medium ${colors[level] || "bg-slate-100 text-slate-500"}`}>
      {level}
    </span>
  );
}

function ActionIcon({ type }: { type: string }) {
  if (!type) return <Zap className="w-4 h-4 text-slate-400" />;
  if (type.includes("PAUSE")) return <XCircle className="w-4 h-4 text-red-400" />;
  if (type.includes("BID")) return <DollarSign className="w-4 h-4 text-emerald-400" />;
  if (type.includes("NEGATIVE")) return <Shield className="w-4 h-4 text-blue-400" />;
  if (type.includes("BUDGET")) return <BarChart3 className="w-4 h-4 text-purple-400" />;
  if (type.includes("DEVICE")) return <Target className="w-4 h-4 text-amber-400" />;
  return <Zap className="w-4 h-4 text-slate-400" />;
}

function DeltaStat({ label, value, invert }: { label: string; value: number; invert?: boolean }) {
  const positive = invert ? value < 0 : value > 0;
  const negative = invert ? value > 0 : value < 0;
  return (
    <div className="text-center">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className={`text-[13px] font-semibold flex items-center justify-center gap-1 ${
        positive ? "text-emerald-600" : negative ? "text-red-500" : "text-slate-500"
      }`}>
        {positive ? <ArrowUpRight className="w-3 h-3" /> : negative ? <ArrowDownRight className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
        {value > 0 ? "+" : ""}{value.toFixed(1)}%
      </p>
    </div>
  );
}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] text-slate-500">{pct}%</span>
    </div>
  );
}
