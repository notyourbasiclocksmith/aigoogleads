"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { AppLayout } from "@/components/layout/sidebar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Brain, Play, Loader2, CheckCircle2, XCircle, AlertTriangle,
  ChevronDown, ChevronRight, DollarSign, TrendingUp, TrendingDown,
  Target, Shield, Zap, BarChart3, Palette, Clock, MapPin,
  Megaphone, Search, Users, FileText, ArrowRight, RotateCcw,
  Sparkles, Eye, Download, Filter, Check, X,
} from "lucide-react";

// ── Types ───────────────────────────────────────────────────────────────────

interface Account {
  id: string;
  customer_id: string;
  account_name: string;
}

interface ScanSummary {
  spend_analyzed: number;
  conversions_analyzed: number;
  wasted_spend_estimate: number;
  missed_opportunity_estimate: number;
  projected_conversion_lift_low: number;
  projected_conversion_lift_high: number;
  projected_cpa_improvement_pct: number;
  confidence_score: number;
  risk_score: number;
  safe_change_count: number;
  moderate_change_count: number;
  high_risk_change_count: number;
  total_recommendations: number;
}

interface Recommendation {
  id: string;
  type: string;
  group: string;
  entity_type: string;
  entity_id: string;
  entity_name: string;
  title: string;
  rationale: string;
  evidence: any;
  current_state: any;
  proposed_state: any;
  confidence: number;
  risk_level: string;
  impact: any;
  generated_by: string;
  status: string;
  priority: number;
}

interface ScanResult {
  scan_id: string;
  status: string;
  date_range: { start: string; end: string };
  scan_goal: string;
  summary: ScanSummary;
  narrative: string;
  metrics_snapshot: any;
  recommendation_groups: Record<string, Recommendation[]>;
  total_recommendations: number;
  creative_audits: any[];
  created_at: string;
  completed_at: string;
  error_message: string;
}

// ── Group metadata ──────────────────────────────────────────────────────────

const GROUP_META: Record<string, { label: string; icon: any; color: string }> = {
  budget_bidding: { label: "Budget & Bidding", icon: DollarSign, color: "text-emerald-400" },
  keywords_search_terms: { label: "Keywords & Search Terms", icon: Search, color: "text-blue-400" },
  negative_keywords: { label: "Negative Keywords", icon: Shield, color: "text-red-400" },
  campaign_structure: { label: "Campaign Structure", icon: BarChart3, color: "text-purple-400" },
  ad_groups: { label: "Ad Groups", icon: Target, color: "text-indigo-400" },
  ad_copy: { label: "Ad Copy", icon: FileText, color: "text-orange-400" },
  creative_assets: { label: "Creative Assets", icon: Palette, color: "text-pink-400" },
  device_modifiers: { label: "Device Modifiers", icon: Zap, color: "text-yellow-400" },
  geo_targeting: { label: "Geo Targeting", icon: MapPin, color: "text-teal-400" },
  ad_schedule: { label: "Ad Schedule", icon: Clock, color: "text-cyan-400" },
  audience_signals: { label: "Audience Signals", icon: Users, color: "text-violet-400" },
  extensions_assets: { label: "Extensions & Assets", icon: Megaphone, color: "text-lime-400" },
  new_campaigns: { label: "New Campaign Opportunities", icon: Sparkles, color: "text-amber-400" },
  policy_compliance: { label: "Policy & Compliance", icon: AlertTriangle, color: "text-rose-400" },
};

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  high: "bg-red-500/15 text-red-400 border-red-500/30",
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  queued: { label: "Queued", color: "text-slate-400" },
  collecting_data: { label: "Collecting Data...", color: "text-blue-400" },
  analyzing: { label: "Analyzing...", color: "text-purple-400" },
  generating_recommendations: { label: "Generating Recommendations...", color: "text-orange-400" },
  building_projections: { label: "Building Projections...", color: "text-emerald-400" },
  running_creative_audit: { label: "Running Creative Audit...", color: "text-pink-400" },
  ready: { label: "Complete", color: "text-emerald-400" },
  failed: { label: "Failed", color: "text-red-400" },
};

// ═════════════════════════════════════════════════════════════════════════════
// MAIN PAGE COMPONENT
// ═════════════════════════════════════════════════════════════════════════════

export default function OperatorPage() {
  // ── State ───────────────────────────────────────────────────────────────
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>("");
  const [dateRange, setDateRange] = useState("30d");
  const [scanGoal, setScanGoal] = useState("full_review");
  const [scanning, setScanning] = useState(false);
  const [scanId, setScanId] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<string>("");
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState("");
  const [selectedRecs, setSelectedRecs] = useState<Set<string>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [expandedRecs, setExpandedRecs] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState<any>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // ── Load accounts on mount ──────────────────────────────────────────────
  useEffect(() => {
    api.get("/api/ads/accounts").then((accts: any) => {
      const valid = (Array.isArray(accts) ? accts : []).filter(
        (a: any) => a.customer_id && a.customer_id !== "pending"
      );
      setAccounts(valid);
      if (valid.length === 1) setSelectedAccount(valid[0].id);
    }).catch(() => {});
  }, []);

  // ── Poll scan status ──────────────────────────────────────────────────
  const pollStatus = useCallback(async (id: string) => {
    try {
      const s = await api.get(`/api/v2/operator/scan/${id}/status`);
      setScanStatus(s.status);
      if (s.status === "ready") {
        if (pollingRef.current) clearInterval(pollingRef.current);
        const result = await api.get(`/api/v2/operator/scan/${id}`);
        setScanResult(result);
        setScanning(false);
        // Auto-expand all groups
        if (result.recommendation_groups) {
          setExpandedGroups(new Set(Object.keys(result.recommendation_groups)));
        }
      } else if (s.status === "failed") {
        if (pollingRef.current) clearInterval(pollingRef.current);
        setError(s.error_message || "Scan failed");
        setScanning(false);
      }
    } catch {
      // silently retry on network blip
    }
  }, []);

  // ── Start scan ────────────────────────────────────────────────────────
  const startScan = async () => {
    if (!selectedAccount) { setError("Select an account first"); return; }
    setError("");
    setScanning(true);
    setScanResult(null);
    setSelectedRecs(new Set());
    setApplyResult(null);

    try {
      const res = await api.post("/api/v2/operator/scan", {
        account_id: selectedAccount,
        date_range: dateRange,
        scan_goal: scanGoal,
      });
      setScanId(res.scan_id);
      setScanStatus("queued");

      // Start polling
      pollingRef.current = setInterval(() => pollStatus(res.scan_id), 2000);
    } catch (e: any) {
      setError(e.message || "Failed to start scan");
      setScanning(false);
    }
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollingRef.current) clearInterval(pollingRef.current); };
  }, []);

  // ── Selection helpers ─────────────────────────────────────────────────
  const toggleRec = (id: string) => {
    setSelectedRecs(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAllSafe = () => {
    if (!scanResult) return;
    const safe = new Set<string>();
    Object.values(scanResult.recommendation_groups).flat().forEach(r => {
      if (r.risk_level === "low") safe.add(r.id);
    });
    setSelectedRecs(safe);
  };

  const selectAll = () => {
    if (!scanResult) return;
    const all = new Set<string>();
    Object.values(scanResult.recommendation_groups).flat().forEach(r => all.add(r.id));
    setSelectedRecs(all);
  };

  const clearSelection = () => setSelectedRecs(new Set());

  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      next.has(group) ? next.delete(group) : next.add(group);
      return next;
    });
  };

  const toggleRecDetail = (id: string) => {
    setExpandedRecs(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // ── Apply changes ─────────────────────────────────────────────────────
  const applyChanges = async () => {
    if (selectedRecs.size === 0 || !scanId) return;
    setApplying(true);
    setError("");
    try {
      const cs = await api.post("/api/v2/operator/change-set", {
        scan_id: scanId,
        selected_recommendation_ids: Array.from(selectedRecs),
      });
      // Validate
      await api.post(`/api/v2/operator/change-set/${cs.change_set_id}/validate`);
      // Apply
      await api.post(`/api/v2/operator/change-set/${cs.change_set_id}/apply`);
      setApplyResult(cs);
      setShowApplyModal(false);
    } catch (e: any) {
      setError(e.message || "Failed to apply changes");
    }
    setApplying(false);
  };

  // ── Computed values ───────────────────────────────────────────────────
  const allRecs = scanResult
    ? Object.values(scanResult.recommendation_groups).flat()
    : [];
  const selectedList = allRecs.filter(r => selectedRecs.has(r.id));

  // ═════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════════════════════════════

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto space-y-6">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Brain className="w-7 h-7 text-blue-600" />
              AI Campaign Operator
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Deep-scan your Google Ads account and get expert-level recommendations with projected impact
            </p>
          </div>
        </div>

        {/* ── Control Bar ────────────────────────────────────────────── */}
        <Card className="p-4">
          <div className="flex flex-wrap items-end gap-4">
            {/* Account selector */}
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs font-medium text-slate-500 mb-1">Account</label>
              <select
                value={selectedAccount}
                onChange={e => setSelectedAccount(e.target.value)}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Select account...</option>
                {accounts.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.account_name || a.customer_id}
                  </option>
                ))}
              </select>
            </div>

            {/* Date range */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Date Range</label>
              <select
                value={dateRange}
                onChange={e => setDateRange(e.target.value)}
                className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500"
              >
                <option value="7d">Last 7 days</option>
                <option value="14d">Last 14 days</option>
                <option value="30d">Last 30 days</option>
                <option value="60d">Last 60 days</option>
                <option value="90d">Last 90 days</option>
              </select>
            </div>

            {/* Scan goal */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Scan Goal</label>
              <select
                value={scanGoal}
                onChange={e => setScanGoal(e.target.value)}
                className="px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:ring-2 focus:ring-blue-500"
              >
                <option value="full_review">Full Strategic Review</option>
                <option value="reduce_waste">Reduce Wasted Spend</option>
                <option value="increase_conversions">Increase Conversions</option>
                <option value="improve_cpa">Improve CPA</option>
                <option value="scale_winners">Scale Winners</option>
              </select>
            </div>

            {/* Run button */}
            <Button
              onClick={startScan}
              disabled={scanning || !selectedAccount}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 h-[38px]"
            >
              {scanning ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Scanning...</>
              ) : (
                <><Play className="w-4 h-4 mr-2" /> Run AI Review</>
              )}
            </Button>
          </div>
        </Card>

        {/* ── Error ──────────────────────────────────────────────────── */}
        {error && (
          <div className="p-4 rounded-lg bg-red-50 border border-red-200 flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-800">Error</p>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* ── Scan Progress ──────────────────────────────────────────── */}
        {scanning && scanStatus && (
          <Card className="p-6">
            <div className="flex items-center gap-4">
              <div className="relative">
                <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
                </div>
              </div>
              <div>
                <p className={`text-sm font-semibold ${STATUS_LABELS[scanStatus]?.color || "text-slate-600"}`}>
                  {STATUS_LABELS[scanStatus]?.label || scanStatus}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">This typically takes 30-60 seconds</p>
              </div>
            </div>
            {/* Progress bar */}
            <div className="mt-4 h-2 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full transition-all duration-700"
                style={{
                  width: `${
                    scanStatus === "queued" ? 5 :
                    scanStatus === "collecting_data" ? 20 :
                    scanStatus === "analyzing" ? 40 :
                    scanStatus === "generating_recommendations" ? 60 :
                    scanStatus === "building_projections" ? 80 :
                    scanStatus === "running_creative_audit" ? 90 :
                    100
                  }%`,
                }}
              />
            </div>
          </Card>
        )}

        {/* ═══════════════════════════════════════════════════════════════ */}
        {/* RESULTS */}
        {/* ═══════════════════════════════════════════════════════════════ */}

        {scanResult && scanResult.status === "ready" && (
          <>
            {/* ── Executive Summary Cards ──────────────────────────────── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <SummaryCard
                label="Spend Analyzed"
                value={`$${scanResult.summary.spend_analyzed.toLocaleString()}`}
                icon={DollarSign}
                color="blue"
              />
              <SummaryCard
                label="Wasted Spend"
                value={`$${scanResult.summary.wasted_spend_estimate.toLocaleString()}`}
                icon={TrendingDown}
                color="red"
                subtitle="estimated recoverable"
              />
              <SummaryCard
                label="Conv. Lift Potential"
                value={`+${scanResult.summary.projected_conversion_lift_low}-${scanResult.summary.projected_conversion_lift_high}`}
                icon={TrendingUp}
                color="emerald"
                subtitle="additional conversions"
              />
              <SummaryCard
                label="CPA Improvement"
                value={`${scanResult.summary.projected_cpa_improvement_pct > 0 ? "-" : ""}${Math.abs(scanResult.summary.projected_cpa_improvement_pct)}%`}
                icon={Target}
                color="purple"
                subtitle="projected"
              />
            </div>

            {/* ── Confidence & Risk badges ─────────────────────────────── */}
            <div className="flex flex-wrap gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm">
                <CheckCircle2 className="w-4 h-4" />
                {scanResult.summary.safe_change_count} Safe Changes
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-sm">
                <AlertTriangle className="w-4 h-4" />
                {scanResult.summary.moderate_change_count} Moderate Risk
              </div>
              {scanResult.summary.high_risk_change_count > 0 && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-50 border border-red-200 text-red-700 text-sm">
                  <XCircle className="w-4 h-4" />
                  {scanResult.summary.high_risk_change_count} High Risk
                </div>
              )}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-blue-700 text-sm">
                <Brain className="w-4 h-4" />
                Confidence: {Math.round(scanResult.summary.confidence_score * 100)}%
              </div>
            </div>

            {/* ── AI Narrative ─────────────────────────────────────────── */}
            {scanResult.narrative && (
              <Card className="p-6 bg-gradient-to-br from-slate-50 to-blue-50/30 border-blue-100">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center flex-shrink-0">
                    <Brain className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900 mb-2">AI Analysis</h3>
                    <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
                      {scanResult.narrative}
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* ── Selection Actions ───────────────────────────────────── */}
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={selectAllSafe} variant="outline" size="sm">
                <Shield className="w-4 h-4 mr-1 text-emerald-500" /> Select All Safe
              </Button>
              <Button onClick={selectAll} variant="outline" size="sm">
                <Check className="w-4 h-4 mr-1" /> Select All
              </Button>
              <Button onClick={clearSelection} variant="outline" size="sm">
                <X className="w-4 h-4 mr-1" /> Clear
              </Button>
              <span className="text-sm text-slate-500">
                {selectedRecs.size} of {allRecs.length} selected
              </span>
            </div>

            {/* ── Recommendation Groups ───────────────────────────────── */}
            <div className="space-y-3">
              {Object.entries(scanResult.recommendation_groups).map(([group, recs]) => {
                const meta = GROUP_META[group] || { label: group, icon: Zap, color: "text-slate-400" };
                const Icon = meta.icon;
                const isExpanded = expandedGroups.has(group);
                const groupSelected = recs.filter(r => selectedRecs.has(r.id)).length;

                return (
                  <Card key={group} className="overflow-hidden">
                    {/* Group header */}
                    <button
                      onClick={() => toggleGroup(group)}
                      className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <Icon className={`w-5 h-5 ${meta.color}`} />
                        <span className="font-semibold text-sm text-slate-900">{meta.label}</span>
                        <Badge variant="secondary" className="text-xs">
                          {recs.length} {recs.length === 1 ? "change" : "changes"}
                        </Badge>
                        {groupSelected > 0 && (
                          <Badge className="bg-blue-100 text-blue-700 text-xs">
                            {groupSelected} selected
                          </Badge>
                        )}
                      </div>
                      {isExpanded ? (
                        <ChevronDown className="w-5 h-5 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-5 h-5 text-slate-400" />
                      )}
                    </button>

                    {/* Recommendation rows */}
                    {isExpanded && (
                      <div className="border-t border-slate-100">
                        {recs.map(rec => (
                          <div key={rec.id} className="border-b border-slate-50 last:border-0">
                            {/* Row */}
                            <div className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50/50">
                              {/* Checkbox */}
                              <button
                                onClick={() => toggleRec(rec.id)}
                                className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                                  selectedRecs.has(rec.id)
                                    ? "bg-blue-600 border-blue-600"
                                    : "border-slate-300 hover:border-blue-400"
                                }`}
                              >
                                {selectedRecs.has(rec.id) && <Check className="w-3 h-3 text-white" />}
                              </button>

                              {/* Content */}
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-slate-900 truncate">{rec.title}</p>
                                {rec.entity_name && (
                                  <p className="text-xs text-slate-500 truncate">{rec.entity_name}</p>
                                )}
                              </div>

                              {/* Risk badge */}
                              <span className={`px-2 py-0.5 rounded text-xs font-medium border ${RISK_COLORS[rec.risk_level] || RISK_COLORS.medium}`}>
                                {rec.risk_level}
                              </span>

                              {/* Confidence */}
                              <span className="text-xs text-slate-500 w-12 text-right">
                                {Math.round(rec.confidence * 100)}%
                              </span>

                              {/* Expand */}
                              <button
                                onClick={() => toggleRecDetail(rec.id)}
                                className="text-slate-400 hover:text-slate-600 p-1"
                              >
                                <Eye className="w-4 h-4" />
                              </button>
                            </div>

                            {/* Expanded detail */}
                            {expandedRecs.has(rec.id) && (
                              <div className="px-5 pb-4 ml-8 space-y-3">
                                <div className="p-3 rounded-lg bg-slate-50 text-sm text-slate-700 leading-relaxed">
                                  {rec.rationale}
                                </div>
                                <div className="grid grid-cols-2 gap-3 text-xs">
                                  {rec.current_state && Object.keys(rec.current_state).length > 0 && (
                                    <div className="p-2 rounded bg-red-50 border border-red-100">
                                      <span className="font-semibold text-red-700">Current State</span>
                                      <pre className="mt-1 text-red-600 whitespace-pre-wrap">
                                        {JSON.stringify(rec.current_state, null, 2)}
                                      </pre>
                                    </div>
                                  )}
                                  {rec.proposed_state && Object.keys(rec.proposed_state).length > 0 && (
                                    <div className="p-2 rounded bg-emerald-50 border border-emerald-100">
                                      <span className="font-semibold text-emerald-700">Proposed State</span>
                                      <pre className="mt-1 text-emerald-600 whitespace-pre-wrap">
                                        {JSON.stringify(rec.proposed_state, null, 2)}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                                {rec.impact && (
                                  <div className="flex flex-wrap gap-3 text-xs">
                                    {rec.impact.spend_delta !== 0 && (
                                      <span className={`px-2 py-1 rounded ${rec.impact.spend_delta < 0 ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                                        Spend: {rec.impact.spend_delta < 0 ? "-" : "+"}${Math.abs(rec.impact.spend_delta).toFixed(0)}
                                      </span>
                                    )}
                                    {rec.impact.conversion_delta !== 0 && (
                                      <span className="px-2 py-1 rounded bg-blue-50 text-blue-700">
                                        Conv: +{rec.impact.conversion_delta.toFixed(1)}
                                      </span>
                                    )}
                                    {rec.impact.cpa_delta !== 0 && (
                                      <span className="px-2 py-1 rounded bg-purple-50 text-purple-700">
                                        CPA: {rec.impact.cpa_delta < 0 ? "" : "+"}${rec.impact.cpa_delta.toFixed(0)}
                                      </span>
                                    )}
                                  </div>
                                )}
                                {rec.impact?.assumptions && rec.impact.assumptions.length > 0 && (
                                  <div className="text-xs text-slate-500">
                                    <span className="font-medium">Assumptions:</span>{" "}
                                    {rec.impact.assumptions.join("; ")}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>

            {/* ── Creative Audit Section ──────────────────────────────── */}
            {scanResult.creative_audits && scanResult.creative_audits.length > 0 && (
              <Card className="p-6">
                <h3 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
                  <Palette className="w-5 h-5 text-pink-500" />
                  Creative Intelligence
                </h3>
                <div className="space-y-4">
                  {scanResult.creative_audits.map((audit: any, i: number) => (
                    <div key={i} className="p-4 rounded-lg bg-slate-50 border border-slate-100">
                      <p className="text-sm font-medium text-slate-800 mb-2">{audit.entity_name}</p>
                      {audit.copy_audit?.missing_angles && audit.copy_audit.missing_angles.length > 0 && (
                        <div className="mb-2">
                          <span className="text-xs font-medium text-slate-600">Missing angles: </span>
                          <span className="text-xs text-slate-500">
                            {audit.copy_audit.missing_angles.join(", ")}
                          </span>
                        </div>
                      )}
                      {audit.copy_audit?.weak_patterns && audit.copy_audit.weak_patterns.length > 0 && (
                        <div className="mb-2">
                          <span className="text-xs font-medium text-red-600">Weak patterns: </span>
                          <span className="text-xs text-red-500">
                            {audit.copy_audit.weak_patterns.join("; ")}
                          </span>
                        </div>
                      )}
                      {audit.copy_audit?.recommendations && (
                        <div className="mt-2 space-y-1">
                          {audit.copy_audit.recommendations.map((cr: any, j: number) => (
                            <div key={j} className="text-xs text-slate-600">
                              <span className="font-medium">{cr.description}</span>
                              {cr.examples && (
                                <span className="text-slate-400 ml-1">
                                  — e.g. {cr.examples.slice(0, 2).join(", ")}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* ── Apply Result ────────────────────────────────────────── */}
            {applyResult && (
              <Card className="p-6 bg-emerald-50 border-emerald-200">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-6 h-6 text-emerald-600 flex-shrink-0" />
                  <div>
                    <h3 className="text-sm font-semibold text-emerald-800">Changes Applied</h3>
                    <p className="text-sm text-emerald-700 mt-1">
                      {applyResult.selected_count} changes have been queued for application.
                      Changes will be applied to your Google Ads account shortly.
                    </p>
                  </div>
                </div>
              </Card>
            )}
          </>
        )}

        {/* ── Sticky Action Footer ───────────────────────────────────── */}
        {scanResult && scanResult.status === "ready" && selectedRecs.size > 0 && !applyResult && (
          <div className="fixed bottom-0 left-64 right-0 bg-white border-t border-slate-200 shadow-lg px-8 py-4 z-40">
            <div className="max-w-7xl mx-auto flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className="text-sm font-semibold text-slate-900">
                  {selectedRecs.size} changes selected
                </span>
                <span className="text-xs text-slate-500">
                  {selectedList.filter(r => r.risk_level === "low").length} safe,{" "}
                  {selectedList.filter(r => r.risk_level === "medium").length} moderate,{" "}
                  {selectedList.filter(r => r.risk_level === "high").length} high risk
                </span>
              </div>
              <div className="flex items-center gap-3">
                <Button variant="outline" size="sm" onClick={clearSelection}>
                  Clear
                </Button>
                <Button
                  onClick={() => setShowApplyModal(true)}
                  className="bg-blue-600 hover:bg-blue-700 text-white"
                  disabled={applying}
                >
                  {applying ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Applying...</>
                  ) : (
                    <><ArrowRight className="w-4 h-4 mr-2" /> Apply {selectedRecs.size} Changes</>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* ── Apply Modal ────────────────────────────────────────────── */}
        {showApplyModal && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-900">Confirm Apply Changes</h3>
              <div className="space-y-2 text-sm text-slate-700">
                <p>You are about to apply <strong>{selectedRecs.size} changes</strong> to your Google Ads account.</p>
                <div className="flex gap-3">
                  <span className="px-2 py-1 rounded bg-emerald-50 text-emerald-700 text-xs">
                    {selectedList.filter(r => r.risk_level === "low").length} safe
                  </span>
                  <span className="px-2 py-1 rounded bg-amber-50 text-amber-700 text-xs">
                    {selectedList.filter(r => r.risk_level === "medium").length} moderate
                  </span>
                  {selectedList.filter(r => r.risk_level === "high").length > 0 && (
                    <span className="px-2 py-1 rounded bg-red-50 text-red-700 text-xs">
                      {selectedList.filter(r => r.risk_level === "high").length} high risk
                    </span>
                  )}
                </div>
              </div>
              {selectedList.some(r => r.risk_level === "high") && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-red-700">
                    You have selected high-risk changes. These may significantly affect campaign performance. Review carefully before applying.
                  </p>
                </div>
              )}
              <p className="text-xs text-slate-500">
                Rollback is available for most changes after application.
              </p>
              <div className="flex justify-end gap-3 pt-2">
                <Button variant="outline" onClick={() => setShowApplyModal(false)}>Cancel</Button>
                <Button
                  onClick={applyChanges}
                  className="bg-blue-600 hover:bg-blue-700 text-white"
                  disabled={applying}
                >
                  {applying ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Applying...</>
                  ) : (
                    "Confirm & Apply"
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Bottom spacer for sticky footer */}
        {scanResult && selectedRecs.size > 0 && !applyResult && <div className="h-20" />}
      </div>
    </AppLayout>
  );
}

// ── Summary Card Component ──────────────────────────────────────────────────

function SummaryCard({
  label, value, icon: Icon, color, subtitle,
}: {
  label: string;
  value: string;
  icon: any;
  color: string;
  subtitle?: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 text-blue-600",
    red: "bg-red-50 text-red-600",
    emerald: "bg-emerald-50 text-emerald-600",
    purple: "bg-purple-50 text-purple-600",
    amber: "bg-amber-50 text-amber-600",
  };
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${colorMap[color] || colorMap.blue}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs text-slate-500">{label}</p>
          <p className="text-lg font-bold text-slate-900">{value}</p>
          {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
        </div>
      </div>
    </Card>
  );
}
