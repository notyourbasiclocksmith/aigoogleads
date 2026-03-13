"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Phone, MessageSquare, Calendar, RefreshCw, Loader2,
  AlertTriangle, CheckCircle2, XCircle, Play, ShieldAlert,
  TrendingUp, DollarSign, Bot, ChevronDown, ChevronUp,
  Clock, User, Mail, ThumbsDown, Search, Filter,
} from "lucide-react";

interface LSAConversation {
  id: string;
  channel: string;
  participant_type: string;
  event_datetime: string | null;
  call_duration_ms: number | null;
  call_recording_url: string | null;
  message_text: string | null;
  transcription_status: string | null;
  has_transcription: boolean;
}

interface LSALead {
  id: string;
  google_lead_id: string;
  lead_type: string;
  category_id: string | null;
  service_id: string | null;
  lead_status: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  lead_charged: boolean;
  credit_state: string | null;
  feedback_submitted: boolean;
  ai_summary: string | null;
  ai_sentiment: string | null;
  ai_lead_quality_score: number | null;
  ai_qualified_lead: boolean | null;
  lead_creation_datetime: string | null;
  synced_at: string | null;
  conversations: LSAConversation[];
}

interface LSASummary {
  period_days: number;
  total_leads: number;
  phone_calls: number;
  messages: number;
  bookings: number;
  charged_leads: number;
  disputed_leads: number;
  credited_leads: number;
  ai_qualified_leads: number;
  ai_spam_leads: number;
  ai_pending_analysis: number;
  avg_ai_quality_score: number | null;
}

export default function LSAPage() {
  const [leads, setLeads] = useState<LSALead[]>([]);
  const [summary, setSummary] = useState<LSASummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [filter, setFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [expandedLead, setExpandedLead] = useState<string | null>(null);
  const [disputingLead, setDisputingLead] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [leadsRes, summaryRes] = await Promise.all([
        api.get("/api/lsa/leads?limit=200"),
        api.get("/api/lsa/summary?days=30"),
      ]);
      setLeads(leadsRes.leads || []);
      setSummary(summaryRes);
    } catch (e) {
      console.error("Failed to load LSA data", e);
    } finally {
      setLoading(false);
    }
  }

  async function syncLSA() {
    setSyncing(true);
    try {
      const res = await api.post("/api/lsa/sync");
      alert(`Synced ${res.leads} leads, ${res.conversations} conversations`);
      await loadData();
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Sync failed — account may not have LSA");
    } finally {
      setSyncing(false);
    }
  }

  async function disputeLead(leadId: string) {
    if (!confirm("Are you sure you want to dispute this lead and request a credit from Google?")) return;
    setDisputingLead(leadId);
    try {
      await api.post(`/api/lsa/leads/${leadId}/dispute`, { reason: "AI identified as spam/unqualified" });
      alert("Dispute submitted! Google will review and may issue a credit.");
      await loadData();
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Failed to submit dispute");
    } finally {
      setDisputingLead(null);
    }
  }

  const filteredLeads = leads.filter((l) => {
    if (typeFilter !== "all" && l.lead_type !== typeFilter) return false;
    if (filter) {
      const q = filter.toLowerCase();
      return (
        (l.contact_name || "").toLowerCase().includes(q) ||
        (l.contact_phone || "").toLowerCase().includes(q) ||
        (l.contact_email || "").toLowerCase().includes(q) ||
        (l.ai_summary || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  function formatDuration(ms: number | null) {
    if (!ms) return "—";
    const s = Math.floor(ms / 1000);
    return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
  }

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
    });
  }

  function leadTypeIcon(type: string) {
    if (type === "PHONE_CALL") return <Phone className="w-4 h-4" />;
    if (type === "MESSAGE") return <MessageSquare className="w-4 h-4" />;
    return <Calendar className="w-4 h-4" />;
  }

  function leadTypeBadge(type: string) {
    const colors: Record<string, string> = {
      PHONE_CALL: "bg-blue-100 text-blue-700",
      MESSAGE: "bg-purple-100 text-purple-700",
      BOOKING: "bg-green-100 text-green-700",
    };
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colors[type] || "bg-gray-100 text-gray-700"}`}>
        {leadTypeIcon(type)} {type.replace("_", " ")}
      </span>
    );
  }

  function qualityBadge(score: number | null, qualified: boolean | null) {
    if (score === null && qualified === null) {
      return <Badge variant="outline" className="text-xs text-slate-400">Pending AI</Badge>;
    }
    if (qualified === true) {
      return <Badge className="bg-green-100 text-green-700 text-xs">{score ?? "—"} ✓ Qualified</Badge>;
    }
    if (qualified === false) {
      return <Badge className="bg-red-100 text-red-700 text-xs">{score ?? "—"} ✗ Spam/Unqualified</Badge>;
    }
    return <Badge variant="outline" className="text-xs">{score}</Badge>;
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Local Services Ads</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Google LSA leads — calls, messages, recordings, AI analysis, and dispute management
            </p>
          </div>
          <Button onClick={syncLSA} disabled={syncing} variant="outline">
            {syncing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
            {syncing ? "Syncing..." : "Sync LSA"}
          </Button>
        </div>

        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <SummaryCard icon={<Phone className="w-4 h-4 text-blue-500" />} label="Total Leads" value={summary.total_leads} />
            <SummaryCard icon={<Phone className="w-4 h-4 text-blue-600" />} label="Phone Calls" value={summary.phone_calls} />
            <SummaryCard icon={<MessageSquare className="w-4 h-4 text-purple-500" />} label="Messages" value={summary.messages} />
            <SummaryCard icon={<DollarSign className="w-4 h-4 text-amber-500" />} label="Charged" value={summary.charged_leads} />
            <SummaryCard icon={<CheckCircle2 className="w-4 h-4 text-green-500" />} label="AI Qualified" value={summary.ai_qualified_leads} />
            <SummaryCard icon={<ShieldAlert className="w-4 h-4 text-red-500" />} label="AI Spam" value={summary.ai_spam_leads} />
          </div>
        )}

        {/* Dispute Stats */}
        {summary && (summary.disputed_leads > 0 || summary.credited_leads > 0) && (
          <Card className="border-amber-200 bg-amber-50/50">
            <CardContent className="py-3 px-4 flex items-center gap-4 text-sm">
              <ThumbsDown className="w-4 h-4 text-amber-600" />
              <span><strong>{summary.disputed_leads}</strong> leads disputed</span>
              <span className="text-green-700"><strong>{summary.credited_leads}</strong> credits received</span>
              {summary.disputed_leads > summary.credited_leads && (
                <span className="text-slate-500">{summary.disputed_leads - summary.credited_leads} pending review</span>
              )}
            </CardContent>
          </Card>
        )}

        {/* Filters */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search by name, phone, email..."
              className="pl-9"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1">
            {["all", "PHONE_CALL", "MESSAGE", "BOOKING"].map((t) => (
              <Button
                key={t}
                variant={typeFilter === t ? "default" : "outline"}
                size="sm"
                onClick={() => setTypeFilter(t)}
                className="text-xs"
              >
                {t === "all" ? "All" : t.replace("_", " ")}
              </Button>
            ))}
          </div>
        </div>

        {/* Leads List */}
        {filteredLeads.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <Phone className="w-12 h-12 mx-auto text-slate-300 mb-3" />
              <p className="text-slate-500 font-medium">No LSA leads found</p>
              <p className="text-sm text-muted-foreground mt-1">
                Click &quot;Sync LSA&quot; to pull leads from Google, or your account may not have Local Services Ads
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {filteredLeads.map((lead) => {
              const isExpanded = expandedLead === lead.id;
              const callConvo = lead.conversations?.find((c) => c.channel === "PHONE_CALL");
              return (
                <Card key={lead.id} className="overflow-hidden">
                  {/* Lead Row */}
                  <div
                    className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-slate-50 transition-colors"
                    onClick={() => setExpandedLead(isExpanded ? null : lead.id)}
                  >
                    {/* Type */}
                    <div className="shrink-0">{leadTypeBadge(lead.lead_type)}</div>

                    {/* Contact */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">
                          {lead.contact_name || lead.contact_phone || "Unknown"}
                        </span>
                        {lead.contact_phone && (
                          <span className="text-xs text-slate-400">{lead.contact_phone}</span>
                        )}
                      </div>
                      {lead.ai_summary && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">{lead.ai_summary}</p>
                      )}
                    </div>

                    {/* Duration (for calls) */}
                    {callConvo && (
                      <div className="flex items-center gap-1 text-xs text-slate-500 shrink-0">
                        <Clock className="w-3 h-3" />
                        {formatDuration(callConvo.call_duration_ms)}
                      </div>
                    )}

                    {/* AI Quality */}
                    <div className="shrink-0">{qualityBadge(lead.ai_lead_quality_score, lead.ai_qualified_lead)}</div>

                    {/* Charge status */}
                    {lead.lead_charged && (
                      <Badge variant="outline" className="text-xs shrink-0">
                        <DollarSign className="w-3 h-3 mr-0.5" /> Charged
                      </Badge>
                    )}

                    {/* Credit state */}
                    {lead.credit_state === "CREDITED" && (
                      <Badge className="bg-green-100 text-green-700 text-xs shrink-0">Credited</Badge>
                    )}
                    {lead.feedback_submitted && lead.credit_state !== "CREDITED" && (
                      <Badge className="bg-amber-100 text-amber-700 text-xs shrink-0">Disputed</Badge>
                    )}

                    {/* Date */}
                    <span className="text-xs text-slate-400 shrink-0 w-32 text-right">
                      {formatDate(lead.lead_creation_datetime)}
                    </span>

                    {/* Expand */}
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                  </div>

                  {/* Expanded Detail */}
                  {isExpanded && (
                    <div className="border-t bg-slate-50/50 px-4 py-4 space-y-4">
                      {/* Contact Info Row */}
                      <div className="flex items-center gap-6 text-sm">
                        {lead.contact_name && (
                          <span className="flex items-center gap-1.5">
                            <User className="w-3.5 h-3.5 text-slate-400" /> {lead.contact_name}
                          </span>
                        )}
                        {lead.contact_phone && (
                          <a href={`tel:${lead.contact_phone}`} className="flex items-center gap-1.5 text-blue-600 hover:underline">
                            <Phone className="w-3.5 h-3.5" /> {lead.contact_phone}
                          </a>
                        )}
                        {lead.contact_email && (
                          <a href={`mailto:${lead.contact_email}`} className="flex items-center gap-1.5 text-blue-600 hover:underline">
                            <Mail className="w-3.5 h-3.5" /> {lead.contact_email}
                          </a>
                        )}
                        <span className="text-slate-400">Status: <strong className="text-slate-600">{lead.lead_status}</strong></span>
                      </div>

                      {/* AI Insights */}
                      {lead.ai_summary && (
                        <div className="bg-white rounded-lg border p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <Bot className="w-4 h-4 text-indigo-500" />
                            <span className="text-xs font-semibold text-indigo-600">AI Analysis</span>
                            {lead.ai_sentiment && (
                              <Badge variant="outline" className="text-xs">{lead.ai_sentiment}</Badge>
                            )}
                          </div>
                          <p className="text-sm text-slate-700">{lead.ai_summary}</p>
                        </div>
                      )}

                      {/* Conversations (calls/messages) */}
                      {lead.conversations.length > 0 && (
                        <div className="space-y-2">
                          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                            Conversations ({lead.conversations.length})
                          </span>
                          {lead.conversations.map((conv) => (
                            <div key={conv.id} className="bg-white rounded-lg border p-3 flex items-center gap-4">
                              <div className="shrink-0">
                                {conv.channel === "PHONE_CALL" ? (
                                  <Phone className="w-5 h-5 text-blue-500" />
                                ) : (
                                  <MessageSquare className="w-5 h-5 text-purple-500" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 text-sm">
                                  <span className="font-medium">{conv.channel.replace("_", " ")}</span>
                                  {conv.call_duration_ms && (
                                    <span className="text-xs text-slate-400">
                                      {formatDuration(conv.call_duration_ms)}
                                    </span>
                                  )}
                                  <span className="text-xs text-slate-400">{formatDate(conv.event_datetime)}</span>
                                </div>
                                {conv.message_text && (
                                  <p className="text-xs text-slate-600 mt-1 truncate">{conv.message_text}</p>
                                )}
                                {conv.has_transcription && (
                                  <Badge variant="outline" className="text-xs mt-1">
                                    <CheckCircle2 className="w-3 h-3 mr-1 text-green-500" /> Transcribed
                                  </Badge>
                                )}
                                {conv.transcription_status === "processing" && (
                                  <Badge variant="outline" className="text-xs mt-1">
                                    <Loader2 className="w-3 h-3 mr-1 animate-spin" /> Transcribing...
                                  </Badge>
                                )}
                              </div>
                              {conv.call_recording_url && (
                                <a
                                  href={conv.call_recording_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="shrink-0"
                                >
                                  <Button size="sm" variant="outline" className="text-xs">
                                    <Play className="w-3 h-3 mr-1" /> Recording
                                  </Button>
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex items-center gap-2 pt-1">
                        {lead.lead_charged && !lead.feedback_submitted && (
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={(e) => { e.stopPropagation(); disputeLead(lead.id); }}
                            disabled={disputingLead === lead.id}
                          >
                            {disputingLead === lead.id ? (
                              <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                            ) : (
                              <ThumbsDown className="w-3 h-3 mr-1" />
                            )}
                            Dispute Lead
                          </Button>
                        )}
                        {lead.feedback_submitted && (
                          <span className="text-xs text-amber-600 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            Dispute submitted {lead.credit_state === "CREDITED" ? "— Credit received!" : "— Under review"}
                          </span>
                        )}
                      </div>
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

function SummaryCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <Card>
      <CardContent className="py-3 px-4">
        <div className="flex items-center gap-2 mb-1">
          {icon}
          <span className="text-xs text-muted-foreground">{label}</span>
        </div>
        <span className="text-xl font-bold text-slate-900">{value}</span>
      </CardContent>
    </Card>
  );
}
