"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Palette, Wand2, Image, Copy, Rocket, Loader2, CheckCircle2, ImagePlus, Download, Upload, Eye, Sparkles } from "lucide-react";

type TabType = "copy" | "images";

export default function CreativePage() {
  const [activeTab, setActiveTab] = useState<TabType>("copy");

  // ── Ad Copy State ──
  const [service, setService] = useState("");
  const [location, setLocation] = useState("");
  const [offer, setOffer] = useState("");
  const [tone, setTone] = useState("urgent");
  const [generatedCopy, setGeneratedCopy] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // ── Image Generator State ──
  const [imgPrompt, setImgPrompt] = useState("");
  const [imgEngine, setImgEngine] = useState("dalle");
  const [imgStyle, setImgStyle] = useState("photorealistic");
  const [imgSize, setImgSize] = useState("1024x1024");
  const [imgAdType, setImgAdType] = useState("responsive_display");
  const [imgAutoUpload, setImgAutoUpload] = useState(false);
  const [imgCampaignId, setImgCampaignId] = useState("");
  const [imgGenerating, setImgGenerating] = useState(false);
  const [imgResults, setImgResults] = useState<any[]>([]);
  const [imgError, setImgError] = useState("");
  const [googleAssets, setGoogleAssets] = useState<any[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [showAssets, setShowAssets] = useState(false);

  // ── Deploy State ──
  const [accounts, setAccounts] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [adGroups, setAdGroups] = useState<any[]>([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [selectedAdGroup, setSelectedAdGroup] = useState("");
  const [finalUrl, setFinalUrl] = useState("");
  const [deploying, setDeploying] = useState(false);
  const [deployResult, setDeployResult] = useState<any>(null);
  const [showDeploy, setShowDeploy] = useState(false);

  useEffect(() => {
    api.get("/api/ads/accounts").then((data: any) => {
      const valid = (Array.isArray(data) ? data : []).filter(
        (a: any) => a.customer_id && a.customer_id !== "pending"
      );
      setAccounts(valid);
      if (valid.length === 1) setSelectedAccount(valid[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedAccount) { setCampaigns([]); return; }
    api.get("/api/dashboard/campaigns").then((data: any) => {
      const camps = (Array.isArray(data) ? data : []).filter((c: any) => c.status === "ENABLED");
      setCampaigns(camps);
    }).catch(() => {});
  }, [selectedAccount]);

  useEffect(() => {
    if (!selectedCampaign) { setAdGroups([]); return; }
    const camp = campaigns.find((c: any) => c.campaign_id === selectedCampaign || c.id === selectedCampaign);
    if (camp) {
      api.get(`/api/ads/campaigns/${camp.id || camp.campaign_id}/ad-groups`).then((data: any) => {
        setAdGroups(Array.isArray(data) ? data : []);
      }).catch(() => setAdGroups([]));
    }
  }, [selectedCampaign, campaigns]);

  // ── Copy Generation ──
  async function handleGenerateCopy() {
    setLoading(true);
    try {
      const data = await api.post("/api/creative/copy/generate", { service, location, offer, tone });
      setGeneratedCopy(data);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  // ── Deploy Ad Copy ──
  async function handleDeploy() {
    if (!selectedAccount || !selectedAdGroup || !finalUrl || !generatedCopy) return;
    setDeploying(true);
    setDeployResult(null);
    try {
      const result = await api.post("/api/creative/copy/deploy", {
        account_id: selectedAccount,
        ad_group_id: selectedAdGroup,
        campaign_id: selectedCampaign,
        headlines: generatedCopy.headlines || [],
        descriptions: generatedCopy.descriptions || [],
        final_url: finalUrl,
      });
      setDeployResult(result);
    } catch (e: any) {
      setDeployResult({ status: "error", error: e.message || "Deploy failed" });
    } finally {
      setDeploying(false);
    }
  }

  // ── Image Generation ──
  async function handleGenerateImage() {
    setImgGenerating(true);
    setImgError("");
    setImgResults([]);
    try {
      const data = await api.post("/api/creative/image/generate-for-ad", {
        prompt: imgPrompt || undefined,
        engine: imgEngine,
        style: imgStyle,
        ad_type: imgAdType,
        campaign_id: imgCampaignId || undefined,
        auto_upload_to_google: imgAutoUpload,
      });
      setImgResults(data.images || []);
      if (data.prompt_used && !imgPrompt) {
        setImgPrompt(data.prompt_used);
      }
    } catch (e: any) {
      setImgError(e.message || "Image generation failed");
    } finally {
      setImgGenerating(false);
    }
  }

  // ── Load Google Ads Assets ──
  async function handleLoadGoogleAssets() {
    setLoadingAssets(true);
    try {
      const data = await api.get("/api/creative/google-ads-assets?asset_type=IMAGE");
      setGoogleAssets(data.assets || []);
      setShowAssets(true);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoadingAssets(false);
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
  }

  const selectClass = "flex h-10 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-600 cursor-pointer hover:border-slate-300 transition-colors";
  const labelClass = "text-[12px] font-medium text-slate-500";

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Creative Studio</h1>
          <p className="text-[13px] text-slate-400 mt-0.5">Generate ad copy and images powered by AI</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-100/80 rounded-xl p-1 w-fit">
          <button
            onClick={() => setActiveTab("copy")}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all ${activeTab === "copy" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
          >
            <Palette className="w-4 h-4 inline mr-1.5 -mt-0.5" />
            Ad Copy
          </button>
          <button
            onClick={() => setActiveTab("images")}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-all ${activeTab === "images" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
          >
            <ImagePlus className="w-4 h-4 inline mr-1.5 -mt-0.5" />
            Image Generator
          </button>
        </div>

        {/* ═══════ AD COPY TAB ═══════ */}
        {activeTab === "copy" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-1 border-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-[15px] tracking-tight">Generate Ad Copy</CardTitle>
                <CardDescription className="text-[12px]">Fill in details to generate headlines, descriptions, and extensions</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5">
                  <label className={labelClass}>Service</label>
                  <Input value={service} onChange={(e: any) => setService(e.target.value)} placeholder="Emergency Lockout" className="rounded-xl border-slate-200 text-[13px] h-10" />
                </div>
                <div className="space-y-1.5">
                  <label className={labelClass}>Location</label>
                  <Input value={location} onChange={(e: any) => setLocation(e.target.value)} placeholder="Dallas, TX" className="rounded-xl border-slate-200 text-[13px] h-10" />
                </div>
                <div className="space-y-1.5">
                  <label className={labelClass}>Offer (optional)</label>
                  <Input value={offer} onChange={(e: any) => setOffer(e.target.value)} placeholder="$20 Off Any Service" className="rounded-xl border-slate-200 text-[13px] h-10" />
                </div>
                <div className="space-y-1.5">
                  <label className={labelClass}>Tone</label>
                  <select value={tone} onChange={(e: any) => setTone(e.target.value)} className={selectClass}>
                    <option value="urgent">Urgent</option>
                    <option value="professional">Professional</option>
                    <option value="friendly">Friendly</option>
                    <option value="authoritative">Authoritative</option>
                  </select>
                </div>
                <Button onClick={handleGenerateCopy} disabled={loading || !service} className="w-full h-11 text-[13px] font-semibold rounded-xl">
                  <Wand2 className="w-4 h-4 mr-2" />
                  {loading ? "Generating..." : "Generate Copy"}
                </Button>
              </CardContent>
            </Card>

            <div className="lg:col-span-2 space-y-5">
              {generatedCopy ? (
                <>
                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] tracking-tight flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center">
                          <Palette className="w-4 h-4 text-blue-500" />
                        </div>
                        Headlines
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {generatedCopy.headlines?.map((h: string, i: number) => (
                          <div key={i} className="flex items-center justify-between px-4 py-3 rounded-xl bg-slate-50/80 border border-slate-100/60 group hover:bg-slate-50 transition-colors">
                            <span className="text-[13px] font-medium text-slate-800">{h}</span>
                            <button onClick={() => copyToClipboard(h)} className="text-slate-300 hover:text-blue-500 transition-colors opacity-0 group-hover:opacity-100">
                              <Copy className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="border-0">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] tracking-tight">Descriptions</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {generatedCopy.descriptions?.map((d: string, i: number) => (
                          <div key={i} className="flex items-start justify-between px-4 py-3 rounded-xl bg-slate-50/80 border border-slate-100/60 group hover:bg-slate-50 transition-colors">
                            <span className="text-[13px] text-slate-700 leading-relaxed">{d}</span>
                            <button onClick={() => copyToClipboard(d)} className="text-slate-300 hover:text-blue-500 transition-colors opacity-0 group-hover:opacity-100 ml-3 mt-0.5 flex-shrink-0">
                              <Copy className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>

                  {generatedCopy.callouts && (
                    <Card className="border-0">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-[15px] tracking-tight">Callout Extensions</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="flex flex-wrap gap-2">
                          {generatedCopy.callouts.map((c: string, i: number) => (
                            <span key={i} className="inline-flex px-3 py-1.5 rounded-xl text-[12px] font-medium bg-slate-100/80 text-slate-600 border border-slate-100/60">{c}</span>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {generatedCopy.sitelinks && (
                    <Card className="border-0">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-[15px] tracking-tight">Sitelink Extensions</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-2 gap-3">
                          {generatedCopy.sitelinks.map((sl: any, i: number) => (
                            <div key={i} className="border border-slate-100/60 rounded-2xl p-4 hover:shadow-md transition-all duration-200">
                              <div className="font-medium text-blue-600 text-[13px]">{sl.text}</div>
                              <div className="text-[12px] text-slate-400 mt-1">{sl.description}</div>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {/* Deploy to Google Ads */}
                  <Card className="border-0 bg-gradient-to-br from-emerald-50/60 to-green-50/30">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-[15px] tracking-tight flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-emerald-100 flex items-center justify-center">
                          <Rocket className="w-4 h-4 text-emerald-600" />
                        </div>
                        Deploy to Google Ads
                      </CardTitle>
                      <CardDescription className="text-[12px]">Push this ad copy live as a Responsive Search Ad</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {!showDeploy ? (
                        <Button onClick={() => setShowDeploy(true)} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white h-11 text-[13px] font-semibold rounded-xl">
                          <Rocket className="w-4 h-4 mr-2" /> Use Ads — Deploy to Google
                        </Button>
                      ) : (
                        <>
                          {accounts.length > 1 && (
                            <div className="space-y-1.5">
                              <label className={labelClass}>Account</label>
                              <select className={selectClass} value={selectedAccount} onChange={(e: any) => setSelectedAccount(e.target.value)}>
                                <option value="">Select account...</option>
                                {accounts.map((a: any) => (
                                  <option key={a.id} value={a.id}>{a.name || a.customer_id}</option>
                                ))}
                              </select>
                            </div>
                          )}
                          <div className="space-y-1.5">
                            <label className={labelClass}>Campaign</label>
                            <select className={selectClass} value={selectedCampaign} onChange={(e: any) => setSelectedCampaign(e.target.value)}>
                              <option value="">Select campaign...</option>
                              {campaigns.map((c: any) => (
                                <option key={c.campaign_id || c.id} value={c.campaign_id || c.id}>{c.name}</option>
                              ))}
                            </select>
                          </div>
                          {adGroups.length > 0 && (
                            <div className="space-y-1.5">
                              <label className={labelClass}>Ad Group</label>
                              <select className={selectClass} value={selectedAdGroup} onChange={(e: any) => setSelectedAdGroup(e.target.value)}>
                                <option value="">Select ad group...</option>
                                {adGroups.map((ag: any) => (
                                  <option key={ag.ad_group_id || ag.id} value={ag.ad_group_id || ag.id}>{ag.name}</option>
                                ))}
                              </select>
                            </div>
                          )}
                          <div className="space-y-1.5">
                            <label className={labelClass}>Landing Page URL</label>
                            <Input value={finalUrl} onChange={(e: any) => setFinalUrl(e.target.value)} placeholder="https://yourbusiness.com" className="h-10 rounded-xl border-slate-200 text-[13px]" />
                          </div>
                          {deployResult?.status === "deployed" && (
                            <div className="flex items-center gap-2 text-[13px] text-emerald-700 bg-emerald-100/80 rounded-xl px-3.5 py-2.5">
                              <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> Ad deployed! {deployResult.headlines_count} headlines, {deployResult.descriptions_count} descriptions.
                            </div>
                          )}
                          {deployResult?.status === "error" && (
                            <div className="text-[13px] text-red-600 bg-red-50 rounded-xl px-3.5 py-2.5">{deployResult.error}</div>
                          )}
                          <Button
                            onClick={handleDeploy}
                            disabled={deploying || !selectedAdGroup || !finalUrl}
                            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white h-11 text-[13px] font-semibold rounded-xl"
                          >
                            {deploying ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Deploying...</> : <><Rocket className="w-4 h-4 mr-2" /> Deploy Ad Now</>}
                          </Button>
                        </>
                      )}
                    </CardContent>
                  </Card>
                </>
              ) : (
                <Card className="border-0">
                  <CardContent className="p-16 text-center">
                    <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
                      <Palette className="w-7 h-7 text-slate-300" />
                    </div>
                    <p className="text-[13px] text-slate-400">Fill in the details on the left and click Generate to create ad copy</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}

        {/* ═══════ IMAGE GENERATOR TAB ═══════ */}
        {activeTab === "images" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Panel — Controls */}
            <Card className="lg:col-span-1 border-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-[15px] tracking-tight flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-purple-500" />
                  AI Image Generator
                </CardTitle>
                <CardDescription className="text-[12px]">Generate professional images for your Google Ads</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Prompt */}
                <div className="space-y-1.5">
                  <label className={labelClass}>Image Prompt</label>
                  <textarea
                    value={imgPrompt}
                    onChange={(e) => setImgPrompt(e.target.value)}
                    placeholder="Professional locksmith technician programming a car key fob next to a modern vehicle, clean uniform, specialized equipment..."
                    rows={4}
                    className="flex w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-[13px] text-slate-600 placeholder:text-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400 transition-colors"
                  />
                  <p className="text-[11px] text-slate-400">Leave empty to auto-generate from your business profile</p>
                </div>

                {/* Engine */}
                <div className="space-y-1.5">
                  <label className={labelClass}>AI Engine</label>
                  <select value={imgEngine} onChange={(e) => setImgEngine(e.target.value)} className={selectClass}>
                    <option value="dalle">DALL-E 3 — Best quality</option>
                    <option value="stability">Stability AI — Photorealistic</option>
                    <option value="flux">Flux.1 — Artistic control</option>
                    <option value="google">Google Gemini — Clean visuals</option>
                  </select>
                </div>

                {/* Style */}
                <div className="space-y-1.5">
                  <label className={labelClass}>Style</label>
                  <select value={imgStyle} onChange={(e) => setImgStyle(e.target.value)} className={selectClass}>
                    <option value="photorealistic">Photorealistic — Best for Ads</option>
                    <option value="cartoon">Cartoon</option>
                    <option value="artistic">Artistic</option>
                    <option value="none">No Enhancement</option>
                  </select>
                </div>

                {/* Ad Type → Auto-sizes */}
                <div className="space-y-1.5">
                  <label className={labelClass}>Ad Type <span className="text-slate-300">(auto-detects sizes)</span></label>
                  <select value={imgAdType} onChange={(e) => setImgAdType(e.target.value)} className={selectClass}>
                    <option value="responsive_display">Responsive Display — 1200x628 + 1024x1024</option>
                    <option value="performance_max">Performance Max — All 3 sizes</option>
                    <option value="discovery">Discovery / Demand Gen</option>
                    <option value="search_companion">Search Companion — Square only</option>
                  </select>
                </div>

                {/* Campaign (optional) */}
                {campaigns.length > 0 && (
                  <div className="space-y-1.5">
                    <label className={labelClass}>Link to Campaign <span className="text-slate-300">(optional)</span></label>
                    <select value={imgCampaignId} onChange={(e) => setImgCampaignId(e.target.value)} className={selectClass}>
                      <option value="">None — just generate</option>
                      {campaigns.map((c: any) => (
                        <option key={c.campaign_id || c.id} value={c.campaign_id || c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Auto-upload toggle */}
                <label className="flex items-center gap-2.5 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={imgAutoUpload}
                    onChange={(e) => setImgAutoUpload(e.target.checked)}
                    className="w-4 h-4 rounded border-slate-300 text-purple-600 focus:ring-purple-500/30"
                  />
                  <span className="text-[12px] text-slate-600 group-hover:text-slate-800 transition-colors">
                    Auto-upload to Google Ads
                  </span>
                </label>

                {/* Generate Button */}
                <Button
                  onClick={handleGenerateImage}
                  disabled={imgGenerating}
                  className="w-full h-11 text-[13px] font-semibold rounded-xl bg-purple-600 hover:bg-purple-700 text-white"
                >
                  {imgGenerating ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Generating...</>
                  ) : (
                    <><Sparkles className="w-4 h-4 mr-2" /> Generate Images</>
                  )}
                </Button>

                {/* View Google Ads Assets */}
                <Button
                  variant="outline"
                  onClick={handleLoadGoogleAssets}
                  disabled={loadingAssets}
                  className="w-full h-10 text-[13px] rounded-xl"
                >
                  {loadingAssets ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Loading...</>
                  ) : (
                    <><Eye className="w-4 h-4 mr-2" /> View Google Ads Assets</>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Right Panel — Results */}
            <div className="lg:col-span-2 space-y-5">
              {/* Error */}
              {imgError && (
                <div className="text-[13px] text-red-600 bg-red-50 rounded-xl px-4 py-3">{imgError}</div>
              )}

              {/* Generated Images */}
              {imgResults.length > 0 && (
                <Card className="border-0">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-[15px] tracking-tight flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-purple-50 flex items-center justify-center">
                        <ImagePlus className="w-4 h-4 text-purple-500" />
                      </div>
                      Generated Images
                      <Badge variant="secondary" className="text-[11px] ml-auto">{imgResults.filter(r => r.status === "complete").length} of {imgResults.length}</Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {imgResults.map((img, i) => (
                        <div key={i} className="relative group rounded-2xl overflow-hidden border border-slate-100 bg-slate-50">
                          {img.status === "complete" && img.image_url ? (
                            <>
                              <img
                                src={img.image_url}
                                alt={`Generated ad image ${i + 1}`}
                                className="w-full aspect-video object-cover"
                              />
                              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all duration-200 flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                                <a
                                  href={img.image_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="bg-white/90 hover:bg-white text-slate-800 rounded-lg px-3 py-1.5 text-[12px] font-medium flex items-center gap-1.5 transition-colors"
                                >
                                  <Download className="w-3.5 h-3.5" /> Download
                                </a>
                              </div>
                              <div className="p-3 space-y-1.5">
                                <div className="flex items-center justify-between">
                                  <span className="text-[12px] font-medium text-slate-700">{img.size}</span>
                                  {img.google_asset_resource && (
                                    <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">
                                      <Upload className="w-3 h-3 mr-1" /> In Google Ads
                                    </Badge>
                                  )}
                                </div>
                                {img.google_upload_error && (
                                  <p className="text-[11px] text-amber-600">Upload error: {img.google_upload_error}</p>
                                )}
                              </div>
                            </>
                          ) : (
                            <div className="p-8 text-center">
                              <p className="text-[12px] text-red-500">Failed: {img.error || "Unknown error"}</p>
                              <p className="text-[11px] text-slate-400 mt-1">Size: {img.size}</p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Google Ads Assets Gallery */}
              {showAssets && (
                <Card className="border-0">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-[15px] tracking-tight flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center">
                        <Image className="w-4 h-4 text-blue-500" />
                      </div>
                      Google Ads Assets
                      <Badge variant="secondary" className="text-[11px] ml-auto">{googleAssets.length} assets</Badge>
                    </CardTitle>
                    <CardDescription className="text-[12px]">Existing image assets in your Google Ads account</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {googleAssets.length === 0 ? (
                      <p className="text-[13px] text-slate-400 text-center py-8">No image assets found in your Google Ads account</p>
                    ) : (
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        {googleAssets.map((asset, i) => (
                          <div key={i} className="rounded-xl border border-slate-100 overflow-hidden bg-slate-50 hover:shadow-md transition-all">
                            {asset.image_url ? (
                              <img src={asset.image_url} alt={asset.name || "Asset"} className="w-full aspect-square object-cover" />
                            ) : (
                              <div className="w-full aspect-square flex items-center justify-center bg-slate-100">
                                <Image className="w-8 h-8 text-slate-300" />
                              </div>
                            )}
                            <div className="p-2.5">
                              <p className="text-[11px] font-medium text-slate-700 truncate">{asset.name || "Untitled"}</p>
                              <p className="text-[10px] text-slate-400">{asset.type} · {asset.resource_name?.split("/").pop()}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Empty State */}
              {imgResults.length === 0 && !showAssets && !imgError && (
                <Card className="border-0">
                  <CardContent className="p-16 text-center">
                    <div className="w-14 h-14 rounded-2xl bg-purple-50 flex items-center justify-center mx-auto mb-4">
                      <ImagePlus className="w-7 h-7 text-purple-300" />
                    </div>
                    <p className="text-[14px] font-medium text-slate-700 mb-1">AI Image Generator</p>
                    <p className="text-[13px] text-slate-400 max-w-sm mx-auto">
                      Write a prompt or leave it empty for auto-generation. Choose your AI engine, ad type, and hit Generate.
                      Images are automatically sized for your selected ad format.
                    </p>
                    <div className="flex flex-wrap justify-center gap-2 mt-4">
                      <Badge variant="secondary" className="text-[11px]">DALL-E 3</Badge>
                      <Badge variant="secondary" className="text-[11px]">Stability AI</Badge>
                      <Badge variant="secondary" className="text-[11px]">Flux.1</Badge>
                      <Badge variant="secondary" className="text-[11px]">Google Gemini</Badge>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
