"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Phone, PhoneIncoming, PhoneOff, Clock, DollarSign,
  TrendingUp, Search, RefreshCw, Loader2, ChevronDown,
  ChevronUp, User, Bot, Play, ExternalLink, Filter,
  BarChart3, Target, Zap, AlertTriangle,
} from "lucide-react";

/* ── Types ─────────────────────────────────────────────── */

interface CallFluxCall {
  id: number;
  twilio_call_sid: string;
  from_number: string;
  to_number: string;
  forwarded_to: string | null;
  direction: string;
  status: string;
  duration_seconds: number | null;
  recording_url: string | null;
  campaign_name: string | null;
  campaign_channel: string | null;
  tracking_source: string | null;
  is_qualified: boolean;
  tags: string[] | null;
  attribution_source: string | null;
  google_ad_cost: number | null;
  lsa_lead_id: string | null;
  start_time: string | null;
  created_at: string;
}

interface LSALead {
  id: string;
  google_lead_id: string;
  lead_type: string;
  lead_status: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  lead_charged: boolean;
  credit_state: string | null;
  ai_summary: string | null;
  ai_sentiment: string | null;
  ai_lead_quality_score: number | null;
  ai_qualified_lead: boolean | null;
  lead_creation_datetime: string | null;
  conversations: {
    id: string;
    channel: string;
    call_duration_ms: number | null;
    call_recording_url: string | null;
    message_text: string | null;
    transcription_status: string | null;
  }[];
}

interface UnifiedCall {
  id: string;
  source: "callflux" | "lsa";
  caller: string;
  callee: string;
  status: string;
  duration_seconds: number | null;
  recording_url: string | null;
  campaign: string | null;
  cost: number | null;
  qualified: boolean;
  ai_summary: string | null;
  ai_score: number | null;
  sentiment: string | null;
  timestamp: string;
  raw: CallFluxCall | LSALead;
}

interface SummaryStats {
  total_calls: number;
  lsa_calls: number;
  callflux_calls: number;
  total_cost: number;
  avg_duration: number;
  qualified_rate: number;
}

/* ── Helpers ───────────────────────────────────────────── */

function formatDuration(seconds: number | null): string {
  if (!seconds) return "0s";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatPhone(num: string | null): string {
  if (!num) return "—";
  return num.replace(/(\+1)(\d{3})(\d{3})(\d{4})/, "$1 ($2) $3-$4");
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-gray-400";
  if (score >= 70) return "text-green-500";
  if (score >= 40) return "text-yellow-500";
  return "text-red-500";
}

function sentimentBadge(s: string | null) {
  if (!s) return null;
  const colors: Record<string, string> = {
    positive: "bg-green-100 text-green-800",
    neutral: "bg-gray-100 text-gray-700",
    negative: "bg-red-100 text-red-800",
  };
  return <span className={`text-xs px-2 py-0.5 rounded-full ${colors[s] || colors.neutral}`}>{s}</span>;
}

/* ── Page ──────────────────────────────────────────────── */

export default function UnifiedCallDashboard() {
  const [calls, setCalls] = useState<UnifiedCall[]>([]);
  const [stats, setStats] = useState<SummaryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<"all" | "callflux" | "lsa">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch both data sources in parallel
      const [lsaRes, cfRes] = await Promise.allSettled([
        api.get(`/api/lsa/leads?days=${days}&limit=200`),
        api.get(`/api/bridge/callflux/calls?days=${days}&page_size=200&tenant_id=1`),
      ]);

      const unified: UnifiedCall[] = [];
      let totalCost = 0;
      let totalDuration = 0;
      let durationCount = 0;
      let qualifiedCount = 0;

      // Process LSA leads
      if (lsaRes.status === "fulfilled") {
        const lsaLeads: LSALead[] = lsaRes.value.leads || lsaRes.value || [];
        for (const lead of lsaLeads) {
          const conv = lead.conversations?.[0];
          const durMs = conv?.call_duration_ms || 0;
          const durS = Math.round(durMs / 1000);
          const cost = lead.lead_charged ? (lead as any).lead_charge_micros ? (lead as any).lead_charge_micros / 1_000_000 : 0 : 0;
          totalCost += cost;
          if (durS > 0) { totalDuration += durS; durationCount++; }
          if (lead.ai_qualified_lead) qualifiedCount++;

          unified.push({
            id: `lsa-${lead.id}`,
            source: "lsa",
            caller: lead.contact_phone || lead.contact_name || "Unknown",
            callee: "Business Line (LSA)",
            status: lead.lead_status || "ACTIVE",
            duration_seconds: durS || null,
            recording_url: conv?.call_recording_url || null,
            campaign: "Local Services Ads",
            cost: cost || null,
            qualified: lead.ai_qualified_lead || false,
            ai_summary: lead.ai_summary,
            ai_score: lead.ai_lead_quality_score,
            sentiment: lead.ai_sentiment,
            timestamp: lead.lead_creation_datetime || "",
            raw: lead,
          });
        }
      }

      // Process CallFlux calls
      if (cfRes.status === "fulfilled") {
        const cfCalls: CallFluxCall[] = cfRes.value.items || cfRes.value || [];
        for (const call of cfCalls) {
          const cost = call.google_ad_cost || 0;
          totalCost += cost;
          if (call.duration_seconds) { totalDuration += call.duration_seconds; durationCount++; }
          if (call.is_qualified) qualifiedCount++;

          unified.push({
            id: `cf-${call.id}`,
            source: "callflux",
            caller: call.from_number,
            callee: call.to_number,
            status: call.status,
            duration_seconds: call.duration_seconds,
            recording_url: call.recording_url,
            campaign: call.campaign_name || call.tracking_source || null,
            cost: cost || null,
            qualified: call.is_qualified,
            ai_summary: null,
            ai_score: null,
            sentiment: null,
            timestamp: call.start_time || call.created_at,
            raw: call,
          });
        }
      }

      // Sort by timestamp desc
      unified.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

      const total = unified.length;
      const lsaCount = unified.filter(c => c.source === "lsa").length;
      const cfCount = unified.filter(c => c.source === "callflux").length;

      setCalls(unified);
      setStats({
        total_calls: total,
        lsa_calls: lsaCount,
        callflux_calls: cfCount,
        total_cost: totalCost,
        avg_duration: durationCount > 0 ? Math.round(totalDuration / durationCount) : 0,
        qualified_rate: total > 0 ? Math.round((qualifiedCount / total) * 100) : 0,
      });
    } catch (err) {
      console.error("Failed to load unified calls:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [days]);

  // Filter
  const filtered = calls.filter((c) => {
    if (sourceFilter !== "all" && c.source !== sourceFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        c.caller.toLowerCase().includes(q) ||
        c.callee.toLowerCase().includes(q) ||
        (c.campaign || "").toLowerCase().includes(q) ||
        (c.ai_summary || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <AppLayout>
      <div className="space-y-6 p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Unified Call Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              All calls across Google LSA and CallFlux in one view
            </p>
          </div>
          <div className="flex gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="border rounded-md px-3 py-2 text-sm"
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
              <option value={60}>Last 60 days</option>
              <option value={90}>Last 90 days</option>
            </select>
            <Button onClick={fetchData} variant="outline" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Phone className="h-4 w-4" /> Total Calls
                </div>
                <p className="text-2xl font-bold mt-1">{stats.total_calls}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Zap className="h-4 w-4 text-blue-500" /> LSA Leads
                </div>
                <p className="text-2xl font-bold mt-1">{stats.lsa_calls}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <PhoneIncoming className="h-4 w-4 text-green-500" /> CallFlux
                </div>
                <p className="text-2xl font-bold mt-1">{stats.callflux_calls}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <DollarSign className="h-4 w-4 text-yellow-500" /> Total Cost
                </div>
                <p className="text-2xl font-bold mt-1">${stats.total_cost.toFixed(2)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" /> Avg Duration
                </div>
                <p className="text-2xl font-bold mt-1">{formatDuration(stats.avg_duration)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4 pb-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Target className="h-4 w-4 text-purple-500" /> Qualified
                </div>
                <p className="text-2xl font-bold mt-1">{stats.qualified_rate}%</p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-3 items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search calls..."
              value={search}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="flex gap-1">
            {(["all", "lsa", "callflux"] as const).map((f) => (
              <Button
                key={f}
                variant={sourceFilter === f ? "default" : "outline"}
                size="sm"
                onClick={() => setSourceFilter(f)}
              >
                {f === "all" ? "All" : f === "lsa" ? "LSA" : "CallFlux"}
              </Button>
            ))}
          </div>
        </div>

        {/* Call List */}
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              <PhoneOff className="h-10 w-10 mx-auto mb-3 opacity-40" />
              <p>No calls found for the selected period and filters.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {filtered.map((call) => {
              const isExpanded = expandedId === call.id;
              return (
                <Card key={call.id} className="overflow-hidden">
                  <div
                    className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-muted/50"
                    onClick={() => setExpandedId(isExpanded ? null : call.id)}
                  >
                    {/* Source badge */}
                    <span className={`text-xs font-semibold px-2 py-1 rounded ${
                      call.source === "lsa"
                        ? "bg-blue-100 text-blue-700"
                        : "bg-green-100 text-green-700"
                    }`}>
                      {call.source === "lsa" ? "LSA" : "CF"}
                    </span>

                    {/* Caller */}
                    <div className="min-w-[140px]">
                      <p className="text-sm font-medium truncate">{formatPhone(call.caller)}</p>
                      <p className="text-xs text-muted-foreground truncate">{call.callee}</p>
                    </div>

                    {/* Campaign */}
                    <div className="flex-1 min-w-0 hidden md:block">
                      <p className="text-sm truncate">{call.campaign || "—"}</p>
                    </div>

                    {/* Duration */}
                    <div className="text-sm text-right w-16">
                      {formatDuration(call.duration_seconds)}
                    </div>

                    {/* Cost */}
                    <div className="text-sm text-right w-16">
                      {call.cost ? `$${call.cost.toFixed(2)}` : "—"}
                    </div>

                    {/* AI Score */}
                    <div className={`text-sm font-bold w-10 text-center ${scoreColor(call.ai_score)}`}>
                      {call.ai_score !== null ? call.ai_score : "—"}
                    </div>

                    {/* Qualified */}
                    <div className="w-8">
                      {call.qualified ? (
                        <span className="text-green-500" title="Qualified">✓</span>
                      ) : (
                        <span className="text-gray-300" title="Not qualified">✗</span>
                      )}
                    </div>

                    {/* Time */}
                    <div className="text-xs text-muted-foreground w-24 text-right">
                      {call.timestamp ? new Date(call.timestamp).toLocaleDateString() : "—"}
                    </div>

                    {/* Expand */}
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="border-t px-6 py-4 bg-muted/30 space-y-3">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <p className="text-xs font-semibold uppercase text-muted-foreground">Call Info</p>
                          <div className="text-sm space-y-1">
                            <p><span className="text-muted-foreground">From:</span> {formatPhone(call.caller)}</p>
                            <p><span className="text-muted-foreground">To:</span> {call.callee}</p>
                            <p><span className="text-muted-foreground">Status:</span> {call.status}</p>
                            <p><span className="text-muted-foreground">Duration:</span> {formatDuration(call.duration_seconds)}</p>
                            <p><span className="text-muted-foreground">Campaign:</span> {call.campaign || "—"}</p>
                            {call.cost && <p><span className="text-muted-foreground">Cost:</span> ${call.cost.toFixed(2)}</p>}
                            <p><span className="text-muted-foreground">Time:</span> {call.timestamp ? new Date(call.timestamp).toLocaleString() : "—"}</p>
                          </div>
                        </div>

                        <div className="space-y-2">
                          <p className="text-xs font-semibold uppercase text-muted-foreground">AI Analysis</p>
                          {call.ai_summary ? (
                            <div className="text-sm space-y-1">
                              <p>{call.ai_summary}</p>
                              <div className="flex gap-2 mt-2">
                                {sentimentBadge(call.sentiment)}
                                {call.ai_score !== null && (
                                  <span className={`text-xs font-bold ${scoreColor(call.ai_score)}`}>
                                    Score: {call.ai_score}/100
                                  </span>
                                )}
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm text-muted-foreground italic">No AI analysis available</p>
                          )}
                        </div>
                      </div>

                      {/* Recording */}
                      {call.recording_url && (
                        <div className="pt-2">
                          <p className="text-xs font-semibold uppercase text-muted-foreground mb-1">Recording</p>
                          <audio controls src={call.recording_url} className="w-full max-w-md" />
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
