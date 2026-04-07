"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import {
  ArrowLeft, Pause, Play, Target, Layers, Type,
  MousePointerClick, DollarSign, Eye, TrendingUp,
  Hash, Star, ExternalLink, Save, Loader2, Settings,
  Globe, Calendar, Link, Search, Monitor, Users,
  BarChart3, Pencil, Check, X, ChevronDown, ChevronRight,
  ArrowUpDown, MoreHorizontal, Image as ImageIcon,
  Phone, Clock, MapPin, Smartphone, Tablet, MonitorSmartphone,
  PhoneCall, PhoneOff, Activity,
} from "lucide-react";
import { HelpTip } from "@/components/ui/help-tip";
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export default function CampaignDetailPage() {
  const params = useParams();
  const campaignId = params.id as string;
  const [campaign, setCampaign] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [editing, setEditing] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [kwSort, setKwSort] = useState<{ field: string; dir: "asc" | "desc" }>({ field: "text", dir: "asc" });
  const [kwActionLoading, setKwActionLoading] = useState<string | null>(null);
  const [editingKw, setEditingKw] = useState<string | null>(null);
  const [editKwText, setEditKwText] = useState("");
  const [editKwMatchType, setEditKwMatchType] = useState("");
  const [kwMsg, setKwMsg] = useState("");

  // Editable fields
  const [editName, setEditName] = useState("");
  const [editBudget, setEditBudget] = useState("");
  const [editBidding, setEditBidding] = useState("");
  const [editTargetCpa, setEditTargetCpa] = useState("");
  const [editTargetRoas, setEditTargetRoas] = useState("");
  const [editSearchNet, setEditSearchNet] = useState(true);
  const [editDisplayNet, setEditDisplayNet] = useState(false);
  const [editPartnerNet, setEditPartnerNet] = useState(false);
  const [editAdRotation, setEditAdRotation] = useState("OPTIMIZE");
  const [editTrackingTemplate, setEditTrackingTemplate] = useState("");
  const [editFinalUrlSuffix, setEditFinalUrlSuffix] = useState("");
  const [editNegativeKws, setEditNegativeKws] = useState("");
  const [editGeoTargets, setEditGeoTargets] = useState("");
  const [editLanguages, setEditLanguages] = useState("");
  const [editStartDate, setEditStartDate] = useState("");
  const [editEndDate, setEditEndDate] = useState("");

  // Campaign images
  const [campaignImages, setCampaignImages] = useState<any[]>([]);
  const [imagesLoading, setImagesLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<any>(null);

  // Tab system
  const [activeTab, setActiveTab] = useState<"overview" | "tracking" | "search-terms" | "calls" | "insights">("overview");

  // Tracking data (loaded on-demand per tab)
  const [trackingData, setTrackingData] = useState<any>(null);
  const [trackingLoading, setTrackingLoading] = useState(false);
  const [searchTerms, setSearchTerms] = useState<any[]>([]);
  const [searchTermsLoading, setSearchTermsLoading] = useState(false);
  const [callData, setCallData] = useState<any>(null);
  const [callsLoading, setCallsLoading] = useState(false);
  const [insightsData, setInsightsData] = useState<any>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [trackingDays, setTrackingDays] = useState(30);

  useEffect(() => {
    api.get(`/api/campaigns/${campaignId}`)
      .then((data) => {
        setCampaign(data);
        populateEditFields(data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));

    // Fetch campaign images
    setImagesLoading(true);
    api.get(`/api/creative/assets?asset_type=IMAGE&campaign_id=${campaignId}&limit=50`)
      .then((data) => {
        const items = Array.isArray(data) ? data : data.items || [];
        setCampaignImages(items.filter((a: any) => a.url));
      })
      .catch(() => {})
      .finally(() => setImagesLoading(false));
  }, [campaignId]);

  // Fetch tab-specific data on demand
  useEffect(() => {
    if (!campaign?.campaign_id) return;
    const gId = campaign.campaign_id;

    if (activeTab === "tracking" && !trackingData && !trackingLoading) {
      setTrackingLoading(true);
      api.get(`/api/analytics/campaign/${gId}?days=${trackingDays}`)
        .then(setTrackingData)
        .catch(() => {})
        .finally(() => setTrackingLoading(false));
    }
    if (activeTab === "search-terms" && searchTerms.length === 0 && !searchTermsLoading) {
      setSearchTermsLoading(true);
      api.get(`/api/ads/search-terms?days=${trackingDays}&campaign_id=${gId}&limit=100`)
        .then((data) => setSearchTerms(Array.isArray(data) ? data : data.items || []))
        .catch(() => {})
        .finally(() => setSearchTermsLoading(false));
    }
    if (activeTab === "calls" && !callData && !callsLoading) {
      setCallsLoading(true);
      api.get(`/api/analytics/calls?days=${trackingDays}`)
        .then(setCallData)
        .catch(() => {})
        .finally(() => setCallsLoading(false));
    }
    if (activeTab === "insights" && !insightsData && !insightsLoading) {
      setInsightsLoading(true);
      Promise.all([
        api.get(`/api/analytics/device?days=${trackingDays}&campaign_id=${gId}`).catch(() => null),
        api.get(`/api/analytics/hourly?days=${trackingDays}&campaign_id=${gId}`).catch(() => null),
        api.get(`/api/analytics/day-of-week?days=${trackingDays}&campaign_id=${gId}`).catch(() => null),
        api.get(`/api/analytics/geo?days=${trackingDays}&campaign_id=${gId}`).catch(() => null),
      ]).then(([device, hourly, dow, geo]) => {
        setInsightsData({ device, hourly, dow, geo });
      }).finally(() => setInsightsLoading(false));
    }
  }, [activeTab, campaign, trackingDays]);

  function populateEditFields(c: any) {
    setEditName(c.name || "");
    setEditBudget(String(c.budget || 0));
    setEditBidding(c.bidding_strategy || "");
    setEditTargetCpa(c.target_cpa_micros ? String(c.target_cpa_micros / 1_000_000) : "");
    setEditTargetRoas(c.target_roas ? String(c.target_roas) : "");
    setEditSearchNet(c.networks?.search ?? true);
    setEditDisplayNet(c.networks?.display ?? false);
    setEditPartnerNet(c.networks?.partner ?? false);
    setEditAdRotation(c.ad_rotation || "OPTIMIZE");
    setEditTrackingTemplate(c.url_options?.tracking_template || "");
    setEditFinalUrlSuffix(c.url_options?.final_url_suffix || "");
    setEditNegativeKws((c.negative_keywords || []).join(", "));
    setEditGeoTargets((c.geo_targets || []).join(", "));
    setEditLanguages((c.language_targets || []).join(", "));
    setEditStartDate(c.start_date || "");
    setEditEndDate(c.end_date || "");
  }

  async function toggleStatus() {
    if (!campaign) return;
    try {
      if (campaign.status === "ENABLED") {
        await api.post(`/api/campaigns/${campaignId}/pause`);
      } else {
        await api.post(`/api/campaigns/${campaignId}/enable`);
      }
      const updated = await api.get(`/api/campaigns/${campaignId}`);
      setCampaign(updated);
      populateEditFields(updated);
    } catch (e) {
      console.error(e);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveMsg("");
    try {
      const body: any = {};
      if (editName !== campaign.name) body.name = editName;
      if (parseFloat(editBudget) !== campaign.budget) body.budget = parseFloat(editBudget);
      if (editBidding !== (campaign.bidding_strategy || "")) body.bidding_strategy = editBidding;
      if (editTargetCpa) body.target_cpa = parseFloat(editTargetCpa);
      if (editTargetRoas) body.target_roas = parseFloat(editTargetRoas);
      body.search_network = editSearchNet;
      body.display_network = editDisplayNet;
      body.partner_network = editPartnerNet;
      body.ad_rotation = editAdRotation;
      body.tracking_template = editTrackingTemplate;
      body.final_url_suffix = editFinalUrlSuffix;
      body.negative_keywords = editNegativeKws ? editNegativeKws.split(",").map((s: string) => s.trim()).filter(Boolean) : [];
      body.geo_targets = editGeoTargets ? editGeoTargets.split(",").map((s: string) => s.trim()).filter(Boolean) : [];
      body.language_targets = editLanguages ? editLanguages.split(",").map((s: string) => s.trim()).filter(Boolean) : [];
      if (editStartDate) body.start_date = editStartDate;
      if (editEndDate) body.end_date = editEndDate;

      await api.patch(`/api/campaigns/${campaignId}`, body);
      const updated = await api.get(`/api/campaigns/${campaignId}`);
      setCampaign(updated);
      populateEditFields(updated);
      setEditing(false);
      setSaveMsg("Changes saved successfully");
      setTimeout(() => setSaveMsg(""), 3000);
    } catch (e: any) {
      setSaveMsg(`Error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  function toggleGroup(id: string) {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleKwSort(field: string) {
    setKwSort((prev) => ({
      field,
      dir: prev.field === field && prev.dir === "asc" ? "desc" : "asc",
    }));
  }

  function sortKeywords(keywords: any[]) {
    const { field, dir } = kwSort;
    return [...keywords].sort((a, b) => {
      let av: any, bv: any;
      if (field === "text") {
        av = (a.text || "").toLowerCase();
        bv = (b.text || "").toLowerCase();
      } else if (field === "match_type") {
        av = a.match_type || "";
        bv = b.match_type || "";
      } else if (field === "status") {
        av = a.status || "";
        bv = b.status || "";
      } else if (field === "quality_score") {
        av = a.quality_score ?? -1;
        bv = b.quality_score ?? -1;
      } else {
        av = a[field];
        bv = b[field];
      }
      if (av < bv) return dir === "asc" ? -1 : 1;
      if (av > bv) return dir === "asc" ? 1 : -1;
      return 0;
    });
  }

  async function toggleKwStatus(kw: any) {
    if (!kw.keyword_id) {
      setKwMsg("Cannot change status: keyword not synced to Google Ads");
      setTimeout(() => setKwMsg(""), 3000);
      return;
    }
    setKwActionLoading(kw.id);
    try {
      const newStatus = kw.status === "ENABLED" ? "PAUSED" : "ENABLED";
      await api.patch(`/api/ads/keywords/${kw.keyword_id}/status`, { status: newStatus });
      const updated = await api.get(`/api/campaigns/${campaignId}`);
      setCampaign(updated);
      populateEditFields(updated);
    } catch (e: any) {
      setKwMsg(`Error: ${e?.message || "Failed to update keyword"}`);
      setTimeout(() => setKwMsg(""), 3000);
    } finally {
      setKwActionLoading(null);
    }
  }

  function startEditKw(kw: any) {
    setEditingKw(kw.id);
    setEditKwText(kw.text);
    setEditKwMatchType(kw.match_type);
  }

  function cancelEditKw() {
    setEditingKw(null);
    setEditKwText("");
    setEditKwMatchType("");
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
        </div>
      </AppLayout>
    );
  }

  if (!campaign) {
    return (
      <AppLayout>
        <div className="text-center py-12">
          <p className="text-muted-foreground">Campaign not found</p>
          <Button className="mt-4" variant="outline" onClick={() => window.location.href = "/ads/campaigns"}>
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Campaigns
          </Button>
        </div>
      </AppLayout>
    );
  }

  const perf = campaign.performance || {};

  return (
    <AppLayout>
      <div className="space-y-6 max-w-6xl">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <Button variant="ghost" size="sm" className="mb-2 -ml-2" onClick={() => window.location.href = "/ads/campaigns"}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <h1 className="text-2xl font-bold text-slate-900">{campaign.name}</h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <Badge variant={campaign.status === "ENABLED" ? "success" : campaign.status === "PAUSED" ? "warning" : "secondary"}>
                {campaign.status}
              </Badge>
              <Badge variant="outline">{campaign.type}</Badge>
              {campaign.bidding_strategy && <Badge variant="outline">{campaign.bidding_strategy}</Badge>}
              {campaign.is_draft && <Badge variant="destructive">Draft</Badge>}
              {campaign.campaign_id && (
                <span className="text-xs text-slate-400">Google ID: {campaign.campaign_id}</span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            {!editing ? (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <Pencil className="w-4 h-4 mr-1" /> Edit
              </Button>
            ) : (
              <>
                <Button variant="outline" size="sm" onClick={() => { setEditing(false); populateEditFields(campaign); }}>
                  <X className="w-4 h-4 mr-1" /> Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white">
                  {saving ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
                  Save Changes
                </Button>
              </>
            )}
            <Button variant="outline" size="sm" onClick={toggleStatus}>
              {campaign.status === "ENABLED" ? <Pause className="w-4 h-4 mr-1" /> : <Play className="w-4 h-4 mr-1" />}
              {campaign.status === "ENABLED" ? "Pause" : "Enable"}
            </Button>
          </div>
        </div>

        {saveMsg && (
          <div className={`px-4 py-2 rounded-lg text-sm ${saveMsg.startsWith("Error") ? "bg-red-50 text-red-700 border border-red-200" : "bg-emerald-50 text-emerald-700 border border-emerald-200"}`}>
            {saveMsg}
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-slate-200 overflow-x-auto">
          {([
            { id: "overview", label: "Overview", icon: <BarChart3 className="w-3.5 h-3.5" /> },
            { id: "tracking", label: "Tracking", icon: <Activity className="w-3.5 h-3.5" /> },
            { id: "search-terms", label: "Search Terms", icon: <Search className="w-3.5 h-3.5" /> },
            { id: "calls", label: "Calls", icon: <Phone className="w-3.5 h-3.5" /> },
            { id: "insights", label: "Insights", icon: <TrendingUp className="w-3.5 h-3.5" /> },
          ] as const).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-400 hover:text-slate-600"
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* ═══ OVERVIEW TAB ═══ */}
        {activeTab === "overview" && (<>

        {/* Performance Stats (30d) */}
        <Card className="border-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-[15px] flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Performance (Last 30 Days)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-7 gap-4">
              {[
                { label: "Impressions", value: formatNumber(perf.impressions || 0), helpTerm: "impressions" },
                { label: "Clicks", value: formatNumber(perf.clicks || 0), helpTerm: "clicks" },
                { label: "CTR", value: formatPercent(perf.ctr || 0), helpTerm: "ctr" },
                { label: "Cost", value: formatCurrency(perf.cost || 0), helpTerm: "cost" },
                { label: "Conversions", value: String((perf.conversions || 0).toFixed(1)), helpTerm: "conversions" },
                { label: "CPA", value: formatCurrency(perf.cpa || 0), helpTerm: "cpa" },
                { label: "ROAS", value: `${(perf.roas || 0).toFixed(2)}x`, helpTerm: "roas" },
              ].map((m) => (
                <div key={m.label} className="text-center p-3 bg-slate-50 rounded-xl">
                  <p className="text-[11px] text-slate-400 mb-1 flex items-center justify-center gap-1">
                    {m.label} <HelpTip term={m.helpTerm} />
                  </p>
                  <p className="text-lg font-semibold text-slate-800">{m.value}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Campaign Configuration */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Budget & Bidding */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px] flex items-center gap-2">
                <DollarSign className="w-4 h-4" /> Budget & Bidding
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-500 font-medium">Daily Budget</label>
                  {editing ? (
                    <div className="flex items-center mt-1">
                      <span className="text-sm text-slate-400 mr-1">$</span>
                      <input type="number" step="0.01" className="w-full border rounded-md px-2 py-1.5 text-sm" value={editBudget} onChange={(e) => setEditBudget(e.target.value)} />
                    </div>
                  ) : (
                    <p className="text-sm font-medium mt-1">{formatCurrency(campaign.budget || 0)}</p>
                  )}
                </div>
                <div>
                  <label className="text-xs text-slate-500 font-medium flex items-center gap-1">Bidding Strategy <HelpTip term="bidding_strategy" /></label>
                  {editing ? (
                    <select className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editBidding} onChange={(e) => setEditBidding(e.target.value)}>
                      <option value="">Select...</option>
                      <option value="MAXIMIZE_CLICKS">Maximize Clicks</option>
                      <option value="MAXIMIZE_CONVERSIONS">Maximize Conversions</option>
                      <option value="TARGET_CPA">Target CPA</option>
                      <option value="TARGET_ROAS">Target ROAS</option>
                      <option value="MANUAL_CPC">Manual CPC</option>
                      <option value="MAXIMIZE_CONVERSION_VALUE">Maximize Conversion Value</option>
                    </select>
                  ) : (
                    <p className="text-sm font-medium mt-1">{campaign.bidding_strategy || "Not set"}</p>
                  )}
                </div>
              </div>
              {(editBidding === "TARGET_CPA" || campaign.bidding_strategy === "TARGET_CPA") && (
                <div>
                  <label className="text-xs text-slate-500 font-medium flex items-center gap-1">Target CPA <HelpTip term="cpa" /></label>
                  {editing ? (
                    <div className="flex items-center mt-1">
                      <span className="text-sm text-slate-400 mr-1">$</span>
                      <input type="number" step="0.01" className="w-full border rounded-md px-2 py-1.5 text-sm" value={editTargetCpa} onChange={(e) => setEditTargetCpa(e.target.value)} />
                    </div>
                  ) : (
                    <p className="text-sm font-medium mt-1">{campaign.target_cpa_micros ? formatCurrency(campaign.target_cpa_micros / 1_000_000) : "Not set"}</p>
                  )}
                </div>
              )}
              {(editBidding === "TARGET_ROAS" || campaign.bidding_strategy === "TARGET_ROAS") && (
                <div>
                  <label className="text-xs text-slate-500 font-medium flex items-center gap-1">Target ROAS <HelpTip term="roas" /></label>
                  {editing ? (
                    <input type="number" step="0.01" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editTargetRoas} onChange={(e) => setEditTargetRoas(e.target.value)} placeholder="e.g. 4.0" />
                  ) : (
                    <p className="text-sm font-medium mt-1">{campaign.target_roas ? `${campaign.target_roas}x` : "Not set"}</p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Networks & Delivery */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px] flex items-center gap-2">
                <Monitor className="w-4 h-4" /> Networks & Delivery
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs text-slate-500 font-medium">Campaign Name</label>
                {editing ? (
                  <input type="text" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editName} onChange={(e) => setEditName(e.target.value)} />
                ) : (
                  <p className="text-sm font-medium mt-1">{campaign.name}</p>
                )}
              </div>
              <div className="space-y-2">
                <label className="text-xs text-slate-500 font-medium">Networks</label>
                {editing ? (
                  <div className="space-y-2 mt-1">
                    {[
                      { label: "Google Search", val: editSearchNet, set: setEditSearchNet },
                      { label: "Display Network", val: editDisplayNet, set: setEditDisplayNet },
                      { label: "Search Partners", val: editPartnerNet, set: setEditPartnerNet },
                    ].map((n) => (
                      <label key={n.label} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input type="checkbox" checked={n.val} onChange={(e) => n.set(e.target.checked)} className="rounded" />
                        {n.label}
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2 mt-1">
                    {campaign.networks?.search && <Badge variant="outline" className="text-xs">Search</Badge>}
                    {campaign.networks?.display && <Badge variant="outline" className="text-xs">Display</Badge>}
                    {campaign.networks?.partner && <Badge variant="outline" className="text-xs">Partners</Badge>}
                    {!campaign.networks?.search && !campaign.networks?.display && !campaign.networks?.partner && (
                      <span className="text-sm text-slate-400">Default</span>
                    )}
                  </div>
                )}
              </div>
              <div>
                <label className="text-xs text-slate-500 font-medium">Ad Rotation</label>
                {editing ? (
                  <select className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editAdRotation} onChange={(e) => setEditAdRotation(e.target.value)}>
                    <option value="OPTIMIZE">Optimize: Prefer best performing ads</option>
                    <option value="ROTATE_INDEFINITELY">Rotate indefinitely</option>
                  </select>
                ) : (
                  <p className="text-sm font-medium mt-1">{campaign.ad_rotation === "ROTATE_INDEFINITELY" ? "Rotate indefinitely" : "Optimize"}</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Targeting */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px] flex items-center gap-2">
                <Globe className="w-4 h-4" /> Targeting
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs text-slate-500 font-medium">Locations (comma-separated)</label>
                {editing ? (
                  <input type="text" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editGeoTargets} onChange={(e) => setEditGeoTargets(e.target.value)} placeholder="e.g. United States, Fort Worth TX" />
                ) : (
                  <p className="text-sm font-medium mt-1">{(campaign.geo_targets || []).length > 0 ? campaign.geo_targets.join(", ") : "All locations"}</p>
                )}
              </div>
              <div>
                <label className="text-xs text-slate-500 font-medium">Languages (comma-separated)</label>
                {editing ? (
                  <input type="text" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editLanguages} onChange={(e) => setEditLanguages(e.target.value)} placeholder="e.g. English, Spanish" />
                ) : (
                  <p className="text-sm font-medium mt-1">{(campaign.language_targets || []).length > 0 ? campaign.language_targets.join(", ") : "All languages"}</p>
                )}
              </div>
              <div>
                <label className="text-xs text-slate-500 font-medium flex items-center gap-1">Negative Keywords <HelpTip term="negative_keyword" /></label>
                {editing ? (
                  <textarea className="w-full border rounded-md px-2 py-1.5 text-sm mt-1 min-h-[60px]" value={editNegativeKws} onChange={(e) => setEditNegativeKws(e.target.value)} placeholder="e.g. free, cheap, diy" />
                ) : (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(campaign.negative_keywords || []).length > 0 ? (
                      campaign.negative_keywords.map((kw: string, i: number) => (
                        <Badge key={i} variant="outline" className="text-xs bg-red-50 text-red-600 border-red-200">-{kw}</Badge>
                      ))
                    ) : (
                      <span className="text-sm text-slate-400">None</span>
                    )}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Schedule & URLs */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px] flex items-center gap-2">
                <Link className="w-4 h-4" /> Schedule & URLs
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-500 font-medium">Start Date</label>
                  {editing ? (
                    <input type="date" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editStartDate} onChange={(e) => setEditStartDate(e.target.value)} />
                  ) : (
                    <p className="text-sm font-medium mt-1">{campaign.start_date || "No start date"}</p>
                  )}
                </div>
                <div>
                  <label className="text-xs text-slate-500 font-medium">End Date</label>
                  {editing ? (
                    <input type="date" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1" value={editEndDate} onChange={(e) => setEditEndDate(e.target.value)} />
                  ) : (
                    <p className="text-sm font-medium mt-1">{campaign.end_date || "No end date"}</p>
                  )}
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-500 font-medium">Tracking Template</label>
                {editing ? (
                  <input type="text" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1 font-mono text-xs" value={editTrackingTemplate} onChange={(e) => setEditTrackingTemplate(e.target.value)} placeholder="{lpurl}?utm_source=google&utm_medium=cpc" />
                ) : (
                  <p className="text-sm font-medium mt-1 font-mono text-xs break-all">{campaign.url_options?.tracking_template || "None"}</p>
                )}
              </div>
              <div>
                <label className="text-xs text-slate-500 font-medium">Final URL Suffix</label>
                {editing ? (
                  <input type="text" className="w-full border rounded-md px-2 py-1.5 text-sm mt-1 font-mono text-xs" value={editFinalUrlSuffix} onChange={(e) => setEditFinalUrlSuffix(e.target.value)} placeholder="utm_campaign={campaignid}" />
                ) : (
                  <p className="text-sm font-medium mt-1 font-mono text-xs break-all">{campaign.url_options?.final_url_suffix || "None"}</p>
                )}
              </div>
              <div className="pt-2 border-t">
                <div className="grid grid-cols-2 gap-4 text-xs text-slate-400">
                  <div>Created: {campaign.created_at ? new Date(campaign.created_at).toLocaleDateString() : "—"}</div>
                  <div>Updated: {campaign.updated_at ? new Date(campaign.updated_at).toLocaleDateString() : "—"}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Ad Groups */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-[15px] flex items-center gap-2">
              <Layers className="w-4 h-4" /> Ad Groups ({campaign.ad_groups?.length || 0})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {campaign.ad_groups && campaign.ad_groups.length > 0 ? (
              <div className="space-y-2">
                {campaign.ad_groups.map((ag: any) => {
                  const isOpen = expandedGroups.has(ag.id);
                  return (
                    <div key={ag.id} className="border rounded-lg overflow-hidden">
                      <button
                        className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors text-left"
                        onClick={() => toggleGroup(ag.id)}
                      >
                        <div className="flex items-center gap-3">
                          {isOpen ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                          <Target className="w-4 h-4 text-blue-500" />
                          <span className="font-medium text-sm">{ag.name}</span>
                          <Badge variant={ag.status === "ENABLED" ? "success" : "secondary"} className="text-xs">
                            {ag.status}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-slate-400">
                          <span>{ag.keywords?.length || 0} keywords</span>
                          <span>{ag.ads?.length || 0} ads</span>
                        </div>
                      </button>
                      {isOpen && (
                        <div className="border-t p-4 space-y-4 bg-slate-50/50">
                          {/* Keywords */}
                          {ag.keywords && ag.keywords.length > 0 && (
                            <div>
                              <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
                                <Hash className="w-3.5 h-3.5" /> Keywords ({ag.keywords.length})
                              </h4>
                              {kwMsg && (
                                <div className={`mb-2 px-3 py-1.5 rounded text-xs ${kwMsg.startsWith("Error") ? "bg-red-50 text-red-700 border border-red-200" : "bg-amber-50 text-amber-700 border border-amber-200"}`}>{kwMsg}</div>
                              )}
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b text-left text-muted-foreground">
                                      <th className="pb-2 font-medium">
                                        <button className="flex items-center gap-1 hover:text-slate-900 transition-colors" onClick={() => toggleKwSort("text")}>
                                          Keyword <ArrowUpDown className={`w-3 h-3 ${kwSort.field === "text" ? "text-blue-600" : ""}`} />
                                        </button>
                                      </th>
                                      <th className="pb-2 font-medium">
                                        <button className="flex items-center gap-1 hover:text-slate-900 transition-colors" onClick={() => toggleKwSort("match_type")}>
                                          Match Type <ArrowUpDown className={`w-3 h-3 ${kwSort.field === "match_type" ? "text-blue-600" : ""}`} />
                                          <HelpTip term="match_type" />
                                        </button>
                                      </th>
                                      <th className="pb-2 font-medium">
                                        <button className="flex items-center gap-1 hover:text-slate-900 transition-colors" onClick={() => toggleKwSort("status")}>
                                          Status <ArrowUpDown className={`w-3 h-3 ${kwSort.field === "status" ? "text-blue-600" : ""}`} />
                                        </button>
                                      </th>
                                      <th className="pb-2 font-medium text-right">
                                        <button className="flex items-center gap-1 justify-end hover:text-slate-900 transition-colors ml-auto" onClick={() => toggleKwSort("quality_score")}>
                                          Quality Score <ArrowUpDown className={`w-3 h-3 ${kwSort.field === "quality_score" ? "text-blue-600" : ""}`} />
                                          <HelpTip term="quality_score" />
                                        </button>
                                      </th>
                                      <th className="pb-2 font-medium text-right">Actions</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {sortKeywords(ag.keywords).map((kw: any) => (
                                      <tr key={kw.id} className="border-b last:border-0 hover:bg-white/60 transition-colors">
                                        <td className="py-2.5 font-medium">
                                          {editingKw === kw.id ? (
                                            <input type="text" className="border rounded px-2 py-1 text-sm w-full max-w-[200px]" value={editKwText} onChange={(e) => setEditKwText(e.target.value)} />
                                          ) : (
                                            kw.match_type === "EXACT"
                                              ? `[${kw.text}]`
                                              : kw.match_type === "PHRASE"
                                                ? `"${kw.text}"`
                                                : kw.text
                                          )}
                                        </td>
                                        <td className="py-2.5">
                                          {editingKw === kw.id ? (
                                            <select className="border rounded px-2 py-1 text-xs" value={editKwMatchType} onChange={(e) => setEditKwMatchType(e.target.value)}>
                                              <option value="BROAD">BROAD</option>
                                              <option value="PHRASE">PHRASE</option>
                                              <option value="EXACT">EXACT</option>
                                            </select>
                                          ) : (
                                            <span className="inline-flex items-center gap-1">
                                              <Badge variant="outline" className={`text-xs ${
                                                kw.match_type === "EXACT" ? "bg-blue-50 text-blue-700 border-blue-200" :
                                                kw.match_type === "PHRASE" ? "bg-purple-50 text-purple-700 border-purple-200" :
                                                "bg-amber-50 text-amber-700 border-amber-200"
                                              }`}>{kw.match_type}</Badge>
                                              <HelpTip term={kw.match_type === "EXACT" ? "match_exact" : kw.match_type === "PHRASE" ? "match_phrase" : "match_broad"} />
                                            </span>
                                          )}
                                        </td>
                                        <td className="py-2.5">
                                          <Badge variant={kw.status === "ENABLED" ? "success" : "secondary"} className="text-xs">
                                            {kw.status}
                                          </Badge>
                                        </td>
                                        <td className="py-2.5 text-right">
                                          {kw.quality_score ? (
                                            <span className="inline-flex items-center gap-1 justify-end">
                                              <span className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-semibold ${
                                                kw.quality_score >= 7 ? "bg-green-50 text-green-700" :
                                                kw.quality_score >= 4 ? "bg-yellow-50 text-yellow-700" :
                                                "bg-red-50 text-red-700"
                                              }`}>
                                                <Star className={`w-3 h-3 ${kw.quality_score >= 7 ? "text-green-500" : kw.quality_score >= 4 ? "text-yellow-500" : "text-red-500"}`} />
                                                {kw.quality_score}/10
                                              </span>
                                            </span>
                                          ) : (
                                            <span className="text-xs text-slate-400 italic">Not available</span>
                                          )}
                                        </td>
                                        <td className="py-2.5 text-right">
                                          <div className="flex items-center gap-1 justify-end">
                                            {editingKw === kw.id ? (
                                              <>
                                                <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-green-600 hover:text-green-700 hover:bg-green-50" onClick={cancelEditKw}>
                                                  <X className="w-3.5 h-3.5" />
                                                </Button>
                                              </>
                                            ) : (
                                              <>
                                                <Button
                                                  size="sm" variant="ghost"
                                                  className={`h-7 w-7 p-0 ${kw.status === "ENABLED" ? "text-amber-600 hover:text-amber-700 hover:bg-amber-50" : "text-green-600 hover:text-green-700 hover:bg-green-50"}`}
                                                  onClick={() => toggleKwStatus(kw)}
                                                  disabled={kwActionLoading === kw.id}
                                                  title={kw.status === "ENABLED" ? "Pause keyword" : "Enable keyword"}
                                                >
                                                  {kwActionLoading === kw.id ? (
                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                  ) : kw.status === "ENABLED" ? (
                                                    <Pause className="w-3.5 h-3.5" />
                                                  ) : (
                                                    <Play className="w-3.5 h-3.5" />
                                                  )}
                                                </Button>
                                                <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-slate-500 hover:text-slate-700 hover:bg-slate-100" onClick={() => startEditKw(kw)} title="Edit keyword">
                                                  <Pencil className="w-3.5 h-3.5" />
                                                </Button>
                                              </>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Ads */}
                          {ag.ads && ag.ads.length > 0 && (
                            <div>
                              <h4 className="text-sm font-semibold mb-2 flex items-center gap-1">
                                <Type className="w-3.5 h-3.5" /> Ads ({ag.ads.length})
                              </h4>
                              <div className="space-y-3">
                                {ag.ads.map((ad: any) => (
                                  <div key={ad.id} className="border rounded-lg p-4 bg-white">
                                    <div className="flex items-center justify-between mb-2">
                                      <Badge variant="outline" className="text-xs">{ad.type}</Badge>
                                      <Badge variant={ad.status === "ENABLED" ? "success" : "secondary"} className="text-xs">
                                        {ad.status}
                                      </Badge>
                                    </div>
                                    {ad.headlines && ad.headlines.length > 0 && (
                                      <div className="mb-2">
                                        <span className="text-xs text-muted-foreground">Headlines:</span>
                                        <div className="flex flex-wrap gap-1 mt-1">
                                          {(Array.isArray(ad.headlines) ? ad.headlines : []).map((h: string, hi: number) => (
                                            <span key={hi} className="text-sm bg-slate-50 border rounded px-2 py-0.5">{h}</span>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                    {ad.descriptions && ad.descriptions.length > 0 && (
                                      <div className="mb-2">
                                        <span className="text-xs text-muted-foreground">Descriptions:</span>
                                        {(Array.isArray(ad.descriptions) ? ad.descriptions : []).map((d: string, di: number) => (
                                          <p key={di} className="text-sm mt-1 bg-slate-50 border rounded px-2 py-1">{d}</p>
                                        ))}
                                      </div>
                                    )}
                                    {ad.final_urls && ad.final_urls.length > 0 && (
                                      <div>
                                        <span className="text-xs text-muted-foreground">Final URLs:</span>
                                        <div className="flex flex-wrap gap-1 mt-1">
                                          {(Array.isArray(ad.final_urls) ? ad.final_urls : []).map((url: string, ui: number) => (
                                            <a key={ui} href={url} target="_blank" rel="noopener noreferrer"
                                               className="text-xs text-blue-600 hover:underline flex items-center gap-0.5">
                                              {url} <ExternalLink className="w-3 h-3" />
                                            </a>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-slate-400 text-center py-6">
                No ad groups found. Sync your Google Ads account from Settings to pull ad group data.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Campaign Images */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-[15px] flex items-center gap-2">
              <ImageIcon className="w-4 h-4" /> Campaign Images
              {campaignImages.length > 0 && (
                <Badge variant="outline" className="ml-1 text-[10px]">{campaignImages.length}</Badge>
              )}
            </CardTitle>
            <CardDescription className="text-xs">
              AI-generated images linked to this campaign
            </CardDescription>
          </CardHeader>
          <CardContent>
            {imagesLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : campaignImages.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No images generated for this campaign yet. Use IntelliDrive Operator to generate campaign images.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                  {campaignImages.map((img: any) => (
                    <div
                      key={img.id}
                      className="group relative rounded-lg overflow-hidden border bg-muted/30 cursor-pointer hover:border-primary/30 transition-all"
                      onClick={() => setSelectedImage(img)}
                    >
                      <div className="aspect-square relative">
                        <img
                          src={img.url}
                          alt={img.metadata?.prompt || "Campaign image"}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                        <div className="absolute bottom-0 left-0 right-0 p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <p className="text-[10px] text-white line-clamp-2">{img.metadata?.prompt || "—"}</p>
                        </div>
                        <a
                          href={img.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="absolute top-1.5 right-1.5 w-6 h-6 bg-black/50 rounded-md flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <ExternalLink className="w-3 h-3 text-white/70" />
                        </a>
                      </div>
                      <div className="p-2">
                        <p className="text-[10px] text-muted-foreground truncate">
                          {img.metadata?.engine === "google" ? "Google Imagen" :
                           img.metadata?.engine === "dalle" ? "DALL-E 3" :
                           img.metadata?.engine || "AI Generated"}
                        </p>
                        <p className="text-[9px] text-muted-foreground/60">
                          {img.created_at ? new Date(img.created_at).toLocaleDateString() : "—"}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Image Lightbox */}
                {selectedImage && (
                  <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
                    onClick={() => setSelectedImage(null)}
                  >
                    <div
                      className="relative max-w-2xl w-full mx-4 bg-background border rounded-2xl overflow-hidden"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => setSelectedImage(null)}
                        className="absolute top-3 right-3 z-10 w-8 h-8 bg-black/50 rounded-lg flex items-center justify-center hover:bg-black/70"
                      >
                        <X className="w-4 h-4 text-white/70" />
                      </button>
                      <img
                        src={selectedImage.url}
                        alt={selectedImage.metadata?.prompt || "Campaign image"}
                        className="w-full max-h-[60vh] object-contain bg-black/20"
                      />
                      <div className="p-4 space-y-2">
                        {selectedImage.metadata?.prompt && (
                          <p className="text-sm text-muted-foreground">{selectedImage.metadata.prompt}</p>
                        )}
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[10px]">
                            {selectedImage.metadata?.engine || "AI"}
                          </Badge>
                          {selectedImage.metadata?.size && (
                            <Badge variant="outline" className="text-[10px]">{selectedImage.metadata.size}</Badge>
                          )}
                          {selectedImage.metadata?.style && (
                            <Badge variant="outline" className="text-[10px]">{selectedImage.metadata.style}</Badge>
                          )}
                        </div>
                        <a href={selectedImage.url} target="_blank" rel="noopener noreferrer">
                          <Button variant="outline" size="sm" className="text-xs mt-2">
                            <ExternalLink className="w-3 h-3 mr-1.5" /> Open Full Size
                          </Button>
                        </a>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* Change History */}
        {campaign.changes && campaign.changes.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px] flex items-center gap-2">
                <Calendar className="w-4 h-4" /> Change History
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {campaign.changes.map((ch: any) => (
                  <div key={ch.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border text-sm">
                    <div>
                      <Badge variant="outline" className="text-xs mr-2">{ch.actor_type}</Badge>
                      <span>{ch.reason}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {ch.applied_at ? new Date(ch.applied_at).toLocaleString() : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
        </>)}

        {/* ═══ TRACKING TAB ═══ */}
        {activeTab === "tracking" && (
          <div className="space-y-6">
            {trackingLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                <span className="ml-2 text-sm text-slate-400">Loading tracking data...</span>
              </div>
            ) : trackingData ? (
              <>
                {/* KPI Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  {[
                    { label: "Clicks", value: formatNumber(trackingData.totals?.clicks || 0), color: "bg-green-50 text-green-700" },
                    { label: "Cost", value: formatCurrency(trackingData.totals?.cost || 0), color: "bg-orange-50 text-orange-700" },
                    { label: "Conversions", value: String((trackingData.totals?.conversions || 0).toFixed(1)), color: "bg-purple-50 text-purple-700" },
                    { label: "CPA", value: formatCurrency(trackingData.totals?.cpa || 0), color: "bg-red-50 text-red-700" },
                    { label: "ROAS", value: `${(trackingData.totals?.roas || 0).toFixed(2)}x`, color: "bg-blue-50 text-blue-700" },
                  ].map((m) => (
                    <div key={m.label} className={`rounded-xl p-4 ${m.color}`}>
                      <p className="text-[11px] uppercase tracking-wider opacity-60">{m.label}</p>
                      <p className="text-xl font-bold mt-1">{m.value}</p>
                    </div>
                  ))}
                </div>

                {/* Daily Trend Chart */}
                <Card className="border-0">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-[15px]">Daily Performance</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={280}>
                      <AreaChart data={trackingData.trends || []}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip formatter={(v: number) => v.toFixed(2)} />
                        <Area type="monotone" dataKey="clicks" stroke="#22c55e" fill="#22c55e" fillOpacity={0.1} />
                        <Area type="monotone" dataKey="conversions" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.1} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Device Breakdown */}
                {trackingData.devices?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] flex items-center gap-2">
                        <MonitorSmartphone className="w-4 h-4" /> Device Performance
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {trackingData.devices.map((d: any) => (
                          <div key={d.device} className="p-4 rounded-xl bg-slate-50 border">
                            <div className="flex items-center gap-2 mb-3">
                              {d.device === "MOBILE" ? <Smartphone className="w-5 h-5 text-blue-500" /> :
                               d.device === "TABLET" ? <Tablet className="w-5 h-5 text-purple-500" /> :
                               <Monitor className="w-5 h-5 text-slate-500" />}
                              <span className="font-semibold text-sm">{d.device}</span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div><span className="text-slate-400">Clicks</span><p className="font-semibold">{formatNumber(d.clicks)}</p></div>
                              <div><span className="text-slate-400">Cost</span><p className="font-semibold">{formatCurrency(d.cost)}</p></div>
                              <div><span className="text-slate-400">Conv</span><p className="font-semibold">{(d.conversions || 0).toFixed(1)}</p></div>
                              <div><span className="text-slate-400">CTR</span><p className="font-semibold">{formatPercent(d.ctr)}</p></div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Hourly Heatmap */}
                {trackingData.hourly?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] flex items-center gap-2">
                        <Clock className="w-4 h-4" /> Performance by Hour
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={trackingData.hourly}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="hour" tick={{ fontSize: 9 }} tickFormatter={(h: number) => `${h}:00`} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip formatter={(v: number) => v.toFixed(0)} labelFormatter={(h: number) => `${h}:00 - ${h}:59`} />
                          <Bar dataKey="clicks" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : (
              <div className="text-center py-20 text-slate-400 text-sm">
                No tracking data available. Make sure the campaign has a Google Ads ID.
              </div>
            )}
          </div>
        )}

        {/* ═══ SEARCH TERMS TAB ═══ */}
        {activeTab === "search-terms" && (
          <div className="space-y-4">
            <Card className="border-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-[15px] flex items-center gap-2">
                  <Search className="w-4 h-4" /> Search Terms (Last {trackingDays} Days)
                </CardTitle>
              </CardHeader>
              <CardContent>
                {searchTermsLoading ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                  </div>
                ) : searchTerms.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-xs text-slate-400 uppercase">
                          <th className="pb-2 pr-4">Search Term</th>
                          <th className="pb-2 pr-4 text-right">Clicks</th>
                          <th className="pb-2 pr-4 text-right">Impr</th>
                          <th className="pb-2 pr-4 text-right">CTR</th>
                          <th className="pb-2 pr-4 text-right">Cost</th>
                          <th className="pb-2 pr-4 text-right">Conv</th>
                          <th className="pb-2 text-right">CPA</th>
                        </tr>
                      </thead>
                      <tbody>
                        {searchTerms.slice(0, 50).map((st: any, i: number) => (
                          <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                            <td className="py-2 pr-4 font-medium max-w-[300px] truncate">{st.search_term}</td>
                            <td className="py-2 pr-4 text-right">{formatNumber(st.clicks)}</td>
                            <td className="py-2 pr-4 text-right">{formatNumber(st.impressions)}</td>
                            <td className="py-2 pr-4 text-right">{formatPercent(st.ctr)}</td>
                            <td className="py-2 pr-4 text-right">{formatCurrency(st.cost)}</td>
                            <td className="py-2 pr-4 text-right">{(st.conversions || 0).toFixed(1)}</td>
                            <td className="py-2 text-right">
                              {st.conversions > 0 ? formatCurrency(st.cpa) : (
                                <span className="text-red-400 text-xs">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {searchTerms.length > 50 && (
                      <p className="text-xs text-slate-400 mt-3 text-center">
                        Showing 50 of {searchTerms.length} search terms
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-slate-400 text-center py-10">No search terms found for this period.</p>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* ═══ CALLS TAB ═══ */}
        {activeTab === "calls" && (
          <div className="space-y-6">
            {callsLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                <span className="ml-2 text-sm text-slate-400">Loading call data...</span>
              </div>
            ) : callData?.status === "ok" ? (
              <>
                {/* Call KPIs */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="rounded-xl p-4 bg-emerald-50">
                    <div className="flex items-center gap-2 text-emerald-600">
                      <PhoneCall className="w-4 h-4" />
                      <span className="text-[11px] uppercase tracking-wider">Total Calls</span>
                    </div>
                    <p className="text-2xl font-bold text-emerald-700 mt-1">{callData.summary?.total_calls || 0}</p>
                  </div>
                  <div className="rounded-xl p-4 bg-green-50">
                    <div className="flex items-center gap-2 text-green-600">
                      <Phone className="w-4 h-4" />
                      <span className="text-[11px] uppercase tracking-wider">Answered</span>
                    </div>
                    <p className="text-2xl font-bold text-green-700 mt-1">{callData.summary?.answered || 0}</p>
                    <p className="text-xs text-green-500 mt-0.5">
                      {formatPercent(callData.summary?.answer_rate || 0)} answer rate
                    </p>
                  </div>
                  <div className="rounded-xl p-4 bg-red-50">
                    <div className="flex items-center gap-2 text-red-600">
                      <PhoneOff className="w-4 h-4" />
                      <span className="text-[11px] uppercase tracking-wider">Missed</span>
                    </div>
                    <p className="text-2xl font-bold text-red-700 mt-1">{callData.summary?.missed || 0}</p>
                  </div>
                  <div className="rounded-xl p-4 bg-blue-50">
                    <div className="flex items-center gap-2 text-blue-600">
                      <Clock className="w-4 h-4" />
                      <span className="text-[11px] uppercase tracking-wider">Avg Duration</span>
                    </div>
                    <p className="text-2xl font-bold text-blue-700 mt-1">
                      {Math.floor((callData.summary?.avg_duration_seconds || 0) / 60)}:{String((callData.summary?.avg_duration_seconds || 0) % 60).padStart(2, "0")}
                    </p>
                  </div>
                </div>

                {/* Calls by Hour */}
                {callData.summary?.calls_by_hour && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px]">Calls by Hour</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={callData.summary.calls_by_hour.map((count: number, hour: number) => ({ hour, calls: count }))}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="hour" tick={{ fontSize: 9 }} tickFormatter={(h: number) => `${h}h`} />
                          <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                          <Tooltip labelFormatter={(h: number) => `${h}:00 - ${h}:59`} />
                          <Bar dataKey="calls" fill="#10b981" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}

                {/* Call Log Table */}
                {callData.calls?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px]">Recent Calls</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-left text-xs text-slate-400 uppercase">
                              <th className="pb-2 pr-4">Date/Time</th>
                              <th className="pb-2 pr-4">Caller</th>
                              <th className="pb-2 pr-4">Status</th>
                              <th className="pb-2 pr-4 text-right">Duration</th>
                              <th className="pb-2">Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {callData.calls.slice(0, 30).map((call: any, i: number) => (
                              <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                                <td className="py-2 pr-4 text-xs">{call.date} {call.time || ""}</td>
                                <td className="py-2 pr-4">{call.caller_number || "Unknown"}</td>
                                <td className="py-2 pr-4">
                                  <Badge variant={call.status === "answered" ? "success" : "destructive"} className="text-[10px]">
                                    {call.status}
                                  </Badge>
                                </td>
                                <td className="py-2 pr-4 text-right text-xs">
                                  {call.duration_seconds ? `${Math.floor(call.duration_seconds / 60)}:${String(call.duration_seconds % 60).padStart(2, "0")}` : "—"}
                                </td>
                                <td className="py-2 text-xs text-slate-400">{call.campaign_name || call.source || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : callData?.status === "not_configured" || callData?.status === "not_registered" ? (
              <div className="text-center py-20">
                <Phone className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-sm text-slate-400">Call tracking not configured.</p>
                <p className="text-xs text-slate-300 mt-1">Create a campaign via Claude Operator to auto-provision call tracking.</p>
              </div>
            ) : (
              <div className="text-center py-20 text-slate-400 text-sm">No call data available.</div>
            )}
          </div>
        )}

        {/* ═══ INSIGHTS TAB ═══ */}
        {activeTab === "insights" && (
          <div className="space-y-6">
            {insightsLoading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                <span className="ml-2 text-sm text-slate-400">Loading insights...</span>
              </div>
            ) : insightsData ? (
              <>
                {/* Device Breakdown */}
                {insightsData.device?.devices?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] flex items-center gap-2">
                        <MonitorSmartphone className="w-4 h-4" /> Device Performance
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-left text-xs text-slate-400 uppercase">
                              <th className="pb-2 pr-4">Device</th>
                              <th className="pb-2 pr-4 text-right">Clicks</th>
                              <th className="pb-2 pr-4 text-right">Impr</th>
                              <th className="pb-2 pr-4 text-right">CTR</th>
                              <th className="pb-2 pr-4 text-right">Cost</th>
                              <th className="pb-2 pr-4 text-right">Conv</th>
                              <th className="pb-2 pr-4 text-right">CPA</th>
                              <th className="pb-2 text-right">ROAS</th>
                            </tr>
                          </thead>
                          <tbody>
                            {insightsData.device.devices.map((d: any) => (
                              <tr key={d.device} className="border-b border-slate-50 hover:bg-slate-50/50">
                                <td className="py-2.5 pr-4 font-medium flex items-center gap-2">
                                  {d.device === "MOBILE" ? <Smartphone className="w-4 h-4 text-blue-500" /> :
                                   d.device === "TABLET" ? <Tablet className="w-4 h-4 text-purple-500" /> :
                                   <Monitor className="w-4 h-4 text-slate-500" />}
                                  {d.device}
                                </td>
                                <td className="py-2.5 pr-4 text-right">{formatNumber(d.clicks)}</td>
                                <td className="py-2.5 pr-4 text-right">{formatNumber(d.impressions)}</td>
                                <td className="py-2.5 pr-4 text-right">{formatPercent(d.ctr)}</td>
                                <td className="py-2.5 pr-4 text-right">{formatCurrency(d.cost)}</td>
                                <td className="py-2.5 pr-4 text-right">{(d.conversions || 0).toFixed(1)}</td>
                                <td className="py-2.5 pr-4 text-right">{d.conversions > 0 ? formatCurrency(d.cpa) : "—"}</td>
                                <td className="py-2.5 text-right">{d.roas > 0 ? `${d.roas.toFixed(2)}x` : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Hour of Day Heatmap */}
                {insightsData.hourly?.hours?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] flex items-center gap-2">
                        <Clock className="w-4 h-4" /> Hourly Performance
                      </CardTitle>
                      <p className="text-xs text-slate-400">Clicks by hour — identify peak and off-peak times</p>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={insightsData.hourly.hours}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="hour" tick={{ fontSize: 9 }} tickFormatter={(h: number) => `${h}h`} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip
                            formatter={(v: number, name: string) => [name === "cost" ? `$${v.toFixed(2)}` : v.toFixed(0), name]}
                            labelFormatter={(h: number) => `${h}:00 - ${h}:59`}
                          />
                          <Bar dataKey="clicks" fill="#3b82f6" radius={[2, 2, 0, 0]} name="Clicks" />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}

                {/* Day of Week */}
                {insightsData.dow?.days?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] flex items-center gap-2">
                        <Calendar className="w-4 h-4" /> Day of Week Performance
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={insightsData.dow.days}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="day" tick={{ fontSize: 9 }} tickFormatter={(d: string) => d.slice(0, 3)} />
                          <YAxis tick={{ fontSize: 10 }} />
                          <Tooltip formatter={(v: number, name: string) => [name === "cost" ? `$${v.toFixed(2)}` : v.toFixed(0), name]} />
                          <Bar dataKey="clicks" fill="#8b5cf6" radius={[2, 2, 0, 0]} name="Clicks" />
                          <Bar dataKey="conversions" fill="#10b981" radius={[2, 2, 0, 0]} name="Conversions" />
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}

                {/* Geo Performance */}
                {insightsData.geo?.locations?.length > 0 && (
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] flex items-center gap-2">
                        <MapPin className="w-4 h-4" /> Geographic Performance
                      </CardTitle>
                      <p className="text-xs text-slate-400">Top locations by clicks</p>
                    </CardHeader>
                    <CardContent>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-left text-xs text-slate-400 uppercase">
                              <th className="pb-2 pr-4">Location</th>
                              <th className="pb-2 pr-4 text-right">Clicks</th>
                              <th className="pb-2 pr-4 text-right">Impr</th>
                              <th className="pb-2 pr-4 text-right">Cost</th>
                              <th className="pb-2 pr-4 text-right">Conv</th>
                              <th className="pb-2 text-right">CPA</th>
                            </tr>
                          </thead>
                          <tbody>
                            {insightsData.geo.locations.slice(0, 20).map((loc: any, i: number) => (
                              <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                                <td className="py-2 pr-4 font-medium flex items-center gap-1.5">
                                  <MapPin className="w-3 h-3 text-slate-400" />
                                  {loc.city_criterion_id || loc.metro_criterion_id || loc.region_criterion_id || "Unknown"}
                                </td>
                                <td className="py-2 pr-4 text-right">{formatNumber(loc.clicks)}</td>
                                <td className="py-2 pr-4 text-right">{formatNumber(loc.impressions)}</td>
                                <td className="py-2 pr-4 text-right">{formatCurrency(loc.cost)}</td>
                                <td className="py-2 pr-4 text-right">{(loc.conversions || 0).toFixed(1)}</td>
                                <td className="py-2 text-right">{loc.conversions > 0 ? formatCurrency(loc.cpa) : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : (
              <div className="text-center py-20 text-slate-400 text-sm">No insights data available.</div>
            )}
          </div>
        )}

      </div>
    </AppLayout>
  );
}
