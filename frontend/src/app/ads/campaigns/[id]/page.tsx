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
} from "lucide-react";
import { HelpTip } from "@/components/ui/help-tip";

export default function CampaignDetailPage() {
  const params = useParams();
  const campaignId = params.id as string;
  const [campaign, setCampaign] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [editing, setEditing] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

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

  useEffect(() => {
    api.get(`/api/campaigns/${campaignId}`)
      .then((data) => {
        setCampaign(data);
        populateEditFields(data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [campaignId]);

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
                              <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                  <thead>
                                    <tr className="border-b text-left text-muted-foreground">
                                      <th className="pb-2 font-medium">Keyword</th>
                                      <th className="pb-2 font-medium"><span className="flex items-center gap-1">Match Type <HelpTip term="match_type" /></span></th>
                                      <th className="pb-2 font-medium">Status</th>
                                      <th className="pb-2 font-medium text-right"><span className="flex items-center gap-1 justify-end">Quality Score <HelpTip term="quality_score" /></span></th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {ag.keywords.map((kw: any) => (
                                      <tr key={kw.id} className="border-b last:border-0 hover:bg-white/60 transition-colors">
                                        <td className="py-2.5 font-medium">
                                          {kw.match_type === "EXACT"
                                            ? `[${kw.text}]`
                                            : kw.match_type === "PHRASE"
                                              ? `"${kw.text}"`
                                              : kw.text}
                                        </td>
                                        <td className="py-2.5">
                                          <span className="inline-flex items-center gap-1">
                                            <Badge variant="outline" className={`text-xs ${
                                              kw.match_type === "EXACT" ? "bg-blue-50 text-blue-700 border-blue-200" :
                                              kw.match_type === "PHRASE" ? "bg-purple-50 text-purple-700 border-purple-200" :
                                              "bg-amber-50 text-amber-700 border-amber-200"
                                            }`}>{kw.match_type}</Badge>
                                            <HelpTip term={kw.match_type === "EXACT" ? "match_exact" : kw.match_type === "PHRASE" ? "match_phrase" : "match_broad"} />
                                          </span>
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
      </div>
    </AppLayout>
  );
}
