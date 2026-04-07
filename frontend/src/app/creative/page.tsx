"use client";

import { useState, useEffect, useRef } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Loader2, ImagePlus, Download, Upload, Eye, Sparkles, StopCircle, CheckCircle, Image } from "lucide-react";

export default function CreativePage() {
  // ── Image Generator State ──
  const [imgPrompt, setImgPrompt] = useState("");
  const [imgEngine, setImgEngine] = useState("flux");
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
  const [fluxModel, setFluxModel] = useState("flux-pro");
  const [stabilityModel, setStabilityModel] = useState("stable-image-ultra");
  const [googleModel, setGoogleModel] = useState("gemini-2.5-flash-image");
  const [imgLiveLog, setImgLiveLog] = useState<string[]>([]);
  const imgAbortRef = useRef<AbortController | null>(null);
  const imgLogTimerRef = useRef<NodeJS.Timeout | null>(null);

  // ── Campaigns (for optional linking) ──
  const [accounts, setAccounts] = useState<any[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [selectedAccount, setSelectedAccount] = useState("");

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

  // ── Image Generation ──
  function stopImageGeneration() {
    if (imgAbortRef.current) {
      imgAbortRef.current.abort();
      imgAbortRef.current = null;
    }
    if (imgLogTimerRef.current) {
      clearInterval(imgLogTimerRef.current);
      imgLogTimerRef.current = null;
    }
    setImgGenerating(false);
    setImgLiveLog(prev => [...prev, "Cancelled by user"]);
  }

  async function handleGenerateImage() {
    setImgGenerating(true);
    setImgError("");
    setImgResults([]);

    // Live log steps
    const engineName = { dalle: "DALL-E 3", stability: "Stability AI", flux: "Flux.1", google: "Google Gemini" }[imgEngine] || imgEngine;
    const steps = [
      "Loading business profile...",
      `Connecting to ${engineName}...`,
      `Generating image (${imgAdType} sizes)...`,
      "Waiting for AI response...",
      "Processing image...",
      "Uploading to Cloudinary...",
      "Adding SEO metadata & EXIF data...",
      imgAutoUpload ? "Uploading to Google Ads..." : "Finalizing...",
    ];
    setImgLiveLog([steps[0]]);
    let stepIdx = 1;
    imgLogTimerRef.current = setInterval(() => {
      if (stepIdx < steps.length) {
        setImgLiveLog(prev => [...prev, steps[stepIdx]]);
        stepIdx++;
      } else if (imgLogTimerRef.current) {
        clearInterval(imgLogTimerRef.current);
      }
    }, 3000);

    const controller = new AbortController();
    imgAbortRef.current = controller;

    try {
      const data = await api.post("/api/creative/image/generate-for-ad", {
        prompt: imgPrompt || undefined,
        engine: imgEngine,
        style: imgStyle,
        ad_type: imgAdType,
        campaign_id: imgCampaignId || undefined,
        auto_upload_to_google: imgAutoUpload,
        stability_model: imgEngine === "stability" ? stabilityModel : undefined,
        flux_model: imgEngine === "flux" ? fluxModel : undefined,
        google_model: imgEngine === "google" ? googleModel : undefined,
      }, { signal: controller.signal });
      setImgResults(data.images || []);
      if (data.prompt_used && !imgPrompt) {
        setImgPrompt(data.prompt_used);
      }
    } catch (e: any) {
      if (e.name !== "AbortError") {
        setImgError(e.message || "Image generation failed");
      }
    } finally {
      setImgGenerating(false);
      imgAbortRef.current = null;
      if (imgLogTimerRef.current) {
        clearInterval(imgLogTimerRef.current);
        imgLogTimerRef.current = null;
      }
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

  const selectClass = "flex h-10 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-600 cursor-pointer hover:border-slate-300 transition-colors";
  const labelClass = "text-[12px] font-medium text-slate-500";

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">AI Image Generator</h1>
          <p className="text-[13px] text-slate-400 mt-0.5">Generate professional ad images powered by AI</p>
        </div>

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
              <div className="space-y-2">
                <label className={labelClass}>AI Engine</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: "flux", label: "Flux.1", badge: "Recommended", color: "amber" },
                    { id: "dalle", label: "DALL-E 3", color: "indigo" },
                    { id: "stability", label: "Stability AI", color: "violet" },
                    { id: "google", label: "Nano Banana", badge: "New", color: "blue" },
                  ].map((eng) => (
                    <button
                      key={eng.id}
                      onClick={() => setImgEngine(eng.id)}
                      className={`relative px-3 py-2.5 rounded-xl text-[12px] font-medium border transition-all text-left ${
                        imgEngine === eng.id
                          ? "border-purple-400 bg-purple-50 text-purple-700 ring-2 ring-purple-500/20"
                          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                      }`}
                    >
                      {eng.label}
                      {eng.badge && (
                        <span className={`ml-1.5 inline-flex px-1.5 py-0.5 rounded text-[9px] font-semibold ${
                          eng.badge === "Recommended" ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"
                        }`}>{eng.badge}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              {/* Flux Sub-model */}
              {imgEngine === "flux" && (
                <div className="space-y-1.5">
                  <label className={labelClass}>Flux Model</label>
                  <div className="flex gap-2">
                    {[
                      { id: "flux-pro", label: "Pro (Best)" },
                      { id: "flux-dev", label: "Dev (Faster)" },
                    ].map((m) => (
                      <button
                        key={m.id}
                        onClick={() => setFluxModel(m.id)}
                        className={`flex-1 px-3 py-2 rounded-xl text-[12px] font-medium border transition-all ${
                          fluxModel === m.id
                            ? "border-amber-400 bg-amber-50 text-amber-700"
                            : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                        }`}
                      >{m.label}</button>
                    ))}
                  </div>
                </div>
              )}

              {/* Stability Sub-model */}
              {imgEngine === "stability" && (
                <div className="space-y-1.5">
                  <label className={labelClass}>Stability Model</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: "stable-image-ultra", label: "Ultra" },
                      { id: "sd3.5-large", label: "Large" },
                      { id: "sd3.5-large-turbo", label: "Turbo" },
                      { id: "sd3.5-medium", label: "Medium" },
                    ].map((m) => (
                      <button
                        key={m.id}
                        onClick={() => setStabilityModel(m.id)}
                        className={`px-3 py-2 rounded-xl text-[12px] font-medium border transition-all ${
                          stabilityModel === m.id
                            ? "border-violet-400 bg-violet-50 text-violet-700"
                            : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                        }`}
                      >{m.label}</button>
                    ))}
                  </div>
                </div>
              )}

              {/* Google Nano Banana Sub-model */}
              {imgEngine === "google" && (
                <div className="space-y-1.5">
                  <label className={labelClass}>Gemini Model</label>
                  <div className="flex gap-2">
                    {[
                      { id: "gemini-2.5-flash-image", label: "Flash" },
                      { id: "gemini-3.1-flash-image-preview", label: "Flash 2" },
                      { id: "gemini-3-pro-image-preview", label: "Pro" },
                    ].map((m) => (
                      <button
                        key={m.id}
                        onClick={() => setGoogleModel(m.id)}
                        className={`flex-1 px-3 py-2 rounded-xl text-[12px] font-medium border transition-all ${
                          googleModel === m.id
                            ? "border-blue-400 bg-blue-50 text-blue-700"
                            : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
                        }`}
                      >{m.label}</button>
                    ))}
                  </div>
                </div>
              )}

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

              {/* Generate / Stop Buttons */}
              {imgGenerating ? (
                <div className="space-y-3">
                  <Button
                    onClick={stopImageGeneration}
                    className="w-full h-11 text-[13px] font-semibold rounded-xl bg-red-600 hover:bg-red-700 text-white"
                  >
                    <StopCircle className="w-4 h-4 mr-2" /> Stop Generation
                  </Button>
                  {/* Live Log Panel */}
                  <div className="bg-slate-900 rounded-xl p-4 space-y-2 max-h-48 overflow-y-auto">
                    {imgLiveLog.map((step, i) => {
                      const isLast = i === imgLiveLog.length - 1;
                      const isCancelled = step === "Cancelled by user";
                      return (
                        <div key={i} className="flex items-center gap-2 text-[12px]">
                          {isCancelled ? (
                            <StopCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                          ) : isLast ? (
                            <Loader2 className="w-3.5 h-3.5 text-purple-400 animate-spin flex-shrink-0" />
                          ) : (
                            <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                          )}
                          <span className={isCancelled ? "text-red-400" : isLast ? "text-purple-300" : "text-emerald-300"}>
                            {step}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <Button
                    onClick={() => { setImgLiveLog([]); handleGenerateImage(); }}
                    className="w-full h-11 text-[13px] font-semibold rounded-xl bg-purple-600 hover:bg-purple-700 text-white"
                  >
                    <Sparkles className="w-4 h-4 mr-2" /> Generate Images
                  </Button>
                  {/* Show completed/cancelled log */}
                  {imgLiveLog.length > 0 && (
                    <div className="bg-slate-900 rounded-xl p-4 space-y-2 max-h-48 overflow-y-auto">
                      {imgLiveLog.map((step, i) => {
                        const isCancelled = step === "Cancelled by user";
                        return (
                          <div key={i} className="flex items-center gap-2 text-[12px]">
                            {isCancelled ? (
                              <StopCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                            ) : (
                              <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                            )}
                            <span className={isCancelled ? "text-red-400" : "text-emerald-300"}>
                              {step}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

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
      </div>
    </AppLayout>
  );
}
