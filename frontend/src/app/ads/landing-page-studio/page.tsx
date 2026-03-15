"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Globe, Sparkles, Loader2, Send, Plus, Copy, Trash2,
  Eye, Pencil, CheckCircle2, AlertCircle, ChevronRight,
  Smartphone, Monitor, FolderOpen, Clock, Wand2, RotateCcw,
  Phone, Star, Shield, ArrowRight, MapPin, MessageSquare,
  Zap, FileText, ExternalLink,
} from "lucide-react";

interface LandingPageItem {
  id: string;
  name: string;
  slug: string;
  service: string;
  location: string;
  status: string;
  page_type: string;
  is_ai_generated: boolean;
  audit_score: number | null;
  variant_count: number;
  created_at: string | null;
  published_at: string | null;
}

interface Variant {
  id: string;
  key: string;
  name: string;
  content: any;
  is_active: boolean;
  is_winner: boolean;
  visits: number;
  conversions: number;
  conversion_rate: number;
}

interface LandingPageDetail {
  id: string;
  name: string;
  slug: string;
  service: string;
  location: string;
  status: string;
  strategy: any;
  content: any;
  style: any;
  seo: any;
  audit_score: number | null;
  variants: Variant[];
  created_at: string | null;
}

export default function LandingPageStudioPage() {
  // Page list state
  const [pages, setPages] = useState<LandingPageItem[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  // Active page state
  const [activePage, setActivePage] = useState<LandingPageDetail | null>(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const [activeVariantIdx, setActiveVariantIdx] = useState(0);

  // AI prompt state
  const [prompt, setPrompt] = useState("");
  const [editing, setEditing] = useState(false);
  const [editHistory, setEditHistory] = useState<string[]>([]);

  // Generate new LP state
  const [showGenerate, setShowGenerate] = useState(false);
  const [genService, setGenService] = useState("");
  const [genLocation, setGenLocation] = useState("");
  const [generating, setGenerating] = useState(false);

  // Clone state
  const [showClone, setShowClone] = useState(false);
  const [cloneService, setCloneService] = useState("");
  const [cloneLocation, setCloneLocation] = useState("");
  const [cloneAdapt, setCloneAdapt] = useState("");
  const [cloning, setCloning] = useState(false);

  // Image generation state
  const [generatingImage, setGeneratingImage] = useState(false);

  // Preview mode
  const [previewMode, setPreviewMode] = useState<"desktop" | "mobile">("desktop");

  // Error
  const [error, setError] = useState("");

  const promptRef = useRef<HTMLTextAreaElement>(null);

  // Load all landing pages
  const loadPages = useCallback(async () => {
    try {
      const data = await api.get("/api/v2/strategist/landing-pages");
      setPages(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to load landing pages", e);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => { loadPages(); }, [loadPages]);

  // Load a specific page with full details
  async function loadPage(id: string) {
    setLoadingPage(true);
    setError("");
    try {
      const data = await api.get(`/api/v2/strategist/landing-pages/${id}`);
      setActivePage(data);
      setActiveVariantIdx(0);
      setEditHistory([]);
    } catch (e: any) {
      setError(e.message || "Failed to load page");
    } finally {
      setLoadingPage(false);
    }
  }

  // AI prompt edit
  async function handleAiEdit() {
    if (!prompt.trim() || !activePage || editing) return;
    const variant = activePage.variants[activeVariantIdx];
    if (!variant) return;

    setEditing(true);
    setError("");
    try {
      const result = await api.post(`/api/v2/strategist/landing-pages/${activePage.id}/ai-edit`, {
        variant_id: variant.id,
        prompt: prompt.trim(),
      });
      // Update the variant content in state
      const updated = { ...activePage };
      updated.variants = [...updated.variants];
      updated.variants[activeVariantIdx] = {
        ...updated.variants[activeVariantIdx],
        content: result.content,
      };
      setActivePage(updated);
      setEditHistory([...editHistory, prompt.trim()]);
      setPrompt("");
    } catch (e: any) {
      setError(e.message || "AI edit failed");
    } finally {
      setEditing(false);
    }
  }

  // Generate hero image for current variant
  async function handleGenerateImage() {
    if (!activePage || generatingImage) return;
    const variant = activePage.variants[activeVariantIdx];
    if (!variant) return;

    setGeneratingImage(true);
    setError("");
    try {
      const result = await api.post(`/api/v2/strategist/landing-pages/${activePage.id}/generate-image`, {
        variant_id: variant.id,
      });
      // Update the variant content with the new image URL
      const updated = { ...activePage };
      updated.variants = [...updated.variants];
      const updatedContent = { ...updated.variants[activeVariantIdx].content };
      updatedContent.hero = { ...updatedContent.hero, hero_image_url: result.image_url };
      updated.variants[activeVariantIdx] = {
        ...updated.variants[activeVariantIdx],
        content: updatedContent,
      };
      setActivePage(updated);
    } catch (e: any) {
      setError(e.message || "Image generation failed");
    } finally {
      setGeneratingImage(false);
    }
  }

  // Generate new LP
  async function handleGenerate() {
    if (!genService.trim() || generating) return;
    setGenerating(true);
    setError("");
    try {
      const result = await api.post("/api/v2/strategist/landing-pages/generate-from-prompt", {
        prompt: genService,
        service: genService,
        location: genLocation,
      });
      setShowGenerate(false);
      setGenService("");
      setGenLocation("");
      await loadPages();
      if (result.landing_page_id) {
        await loadPage(result.landing_page_id);
      }
    } catch (e: any) {
      setError(e.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  // Clone LP
  async function handleClone() {
    if (!activePage || cloning) return;
    setCloning(true);
    setError("");
    try {
      const result = await api.post(`/api/v2/strategist/landing-pages/${activePage.id}/clone`, {
        new_service: cloneService,
        new_location: cloneLocation,
        adapt_prompt: cloneAdapt || (cloneService ? `Adapt this landing page for '${cloneService}'${cloneLocation ? ` in '${cloneLocation}'` : ""}. Update all headlines, copy, and service references.` : ""),
      });
      setShowClone(false);
      setCloneService("");
      setCloneLocation("");
      setCloneAdapt("");
      await loadPages();
      if (result.landing_page_id) {
        await loadPage(result.landing_page_id);
      }
    } catch (e: any) {
      setError(e.message || "Clone failed");
    } finally {
      setCloning(false);
    }
  }

  // Update status
  async function updateStatus(status: string) {
    if (!activePage) return;
    try {
      await api.patch(`/api/v2/strategist/landing-pages/${activePage.id}/status`, { status });
      setActivePage({ ...activePage, status });
      loadPages();
    } catch (e: any) {
      setError(e.message || "Status update failed");
    }
  }

  const activeVariant = activePage?.variants?.[activeVariantIdx];

  return (
    <AppLayout>
      <div className="flex h-[calc(100vh-64px)] overflow-hidden -m-6">
        {/* ═══ LEFT SIDEBAR — PAGE LIST ═══ */}
        <div className="w-72 border-r bg-slate-50/50 flex flex-col overflow-hidden flex-shrink-0">
          <div className="p-4 border-b bg-white">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Globe className="w-5 h-5 text-purple-600" />
                <h2 className="font-bold text-slate-900 text-sm">Landing Pages</h2>
              </div>
              <Button
                size="sm"
                className="h-7 text-xs bg-purple-600 hover:bg-purple-700"
                onClick={() => setShowGenerate(true)}
              >
                <Plus className="w-3 h-3 mr-1" /> New
              </Button>
            </div>
            <p className="text-[11px] text-slate-500">{pages.length} pages</p>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loadingList ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
              </div>
            ) : pages.length === 0 ? (
              <div className="text-center py-8 px-4">
                <Globe className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-xs text-slate-500">No landing pages yet</p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2 text-xs"
                  onClick={() => setShowGenerate(true)}
                >
                  <Sparkles className="w-3 h-3 mr-1" /> Generate First Page
                </Button>
              </div>
            ) : (
              pages.map((p) => (
                <button
                  key={p.id}
                  onClick={() => loadPage(p.id)}
                  className={`w-full text-left rounded-lg p-3 transition-all ${
                    activePage?.id === p.id
                      ? "bg-purple-100 border border-purple-200"
                      : "bg-white border border-transparent hover:border-slate-200 hover:bg-white"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    {p.is_ai_generated ? (
                      <Sparkles className="w-3 h-3 text-purple-500 flex-shrink-0" />
                    ) : (
                      <Globe className="w-3 h-3 text-slate-400 flex-shrink-0" />
                    )}
                    <span className="text-xs font-medium text-slate-800 truncate">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5 ml-5">
                    <Badge className={`text-[9px] px-1 py-0 ${
                      p.status === "published" ? "bg-green-100 text-green-700" :
                      p.status === "draft" ? "bg-slate-100 text-slate-600" :
                      "bg-amber-100 text-amber-700"
                    }`}>
                      {p.status}
                    </Badge>
                    {p.variant_count > 0 && (
                      <span className="text-[9px] text-slate-400">{p.variant_count} variants</span>
                    )}
                    {p.audit_score !== null && (
                      <span className={`text-[9px] font-medium ${
                        p.audit_score >= 80 ? "text-green-600" : p.audit_score >= 60 ? "text-amber-600" : "text-red-600"
                      }`}>
                        {p.audit_score}/100
                      </span>
                    )}
                  </div>
                  {p.service && (
                    <p className="text-[10px] text-slate-400 ml-5 mt-0.5 truncate">{p.service}{p.location ? ` — ${p.location}` : ""}</p>
                  )}
                </button>
              ))
            )}
          </div>
        </div>

        {/* ═══ MAIN AREA ═══ */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {!activePage && !loadingPage ? (
            /* ── Empty State ── */
            <div className="flex-1 flex items-center justify-center bg-gradient-to-b from-slate-50 to-white">
              <div className="text-center max-w-md">
                <div className="w-16 h-16 rounded-2xl bg-purple-100 flex items-center justify-center mx-auto mb-4">
                  <Wand2 className="w-8 h-8 text-purple-600" />
                </div>
                <h2 className="text-xl font-bold text-slate-900 mb-2">AI Landing Page Studio</h2>
                <p className="text-sm text-slate-500 mb-6">
                  Create, edit, and manage landing pages with AI. Select a page from the sidebar or generate a new one.
                </p>
                <div className="flex gap-3 justify-center">
                  <Button onClick={() => setShowGenerate(true)} className="bg-purple-600 hover:bg-purple-700">
                    <Sparkles className="w-4 h-4 mr-2" /> Generate New Page
                  </Button>
                  {pages.length > 0 && (
                    <Button variant="outline" onClick={() => loadPage(pages[0].id)}>
                      <Eye className="w-4 h-4 mr-2" /> Open Latest
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ) : loadingPage ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Loader2 className="w-8 h-8 animate-spin text-purple-500 mx-auto mb-3" />
                <p className="text-sm text-slate-500">Loading page...</p>
              </div>
            </div>
          ) : activePage ? (
            <>
              {/* ── Top Bar ── */}
              <div className="border-b bg-white px-4 py-2 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <h1 className="text-sm font-bold text-slate-900">{activePage.name}</h1>
                    <p className="text-[11px] text-slate-400">
                      <code className="bg-slate-100 px-1 rounded">{activePage.slug}</code>
                    </p>
                  </div>
                  <Badge className={`text-[10px] ${
                    activePage.status === "published" ? "bg-green-100 text-green-700" :
                    activePage.status === "draft" ? "bg-slate-100 text-slate-600" :
                    "bg-amber-100 text-amber-700"
                  }`}>
                    {activePage.status}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  {/* Preview mode toggle */}
                  <div className="flex items-center border rounded-lg overflow-hidden">
                    <button
                      onClick={() => setPreviewMode("desktop")}
                      className={`p-1.5 ${previewMode === "desktop" ? "bg-slate-100" : "hover:bg-slate-50"}`}
                    >
                      <Monitor className="w-4 h-4 text-slate-600" />
                    </button>
                    <button
                      onClick={() => setPreviewMode("mobile")}
                      className={`p-1.5 ${previewMode === "mobile" ? "bg-slate-100" : "hover:bg-slate-50"}`}
                    >
                      <Smartphone className="w-4 h-4 text-slate-600" />
                    </button>
                  </div>
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowClone(true)}>
                    <Copy className="w-3 h-3 mr-1" /> Clone & Reuse
                  </Button>
                  {activePage.status === "draft" ? (
                    <Button size="sm" className="h-7 text-xs bg-green-600 hover:bg-green-700" onClick={() => updateStatus("published")}>
                      Publish
                    </Button>
                  ) : activePage.status === "published" ? (
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => updateStatus("paused")}>
                      Unpublish
                    </Button>
                  ) : null}
                </div>
              </div>

              {/* ── Variant Tabs ── */}
              {activePage.variants.length > 0 && (
                <div className="border-b bg-white px-4 py-1.5 flex items-center gap-1">
                  {activePage.variants.map((v, i) => (
                    <button
                      key={v.id}
                      onClick={() => setActiveVariantIdx(i)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                        activeVariantIdx === i
                          ? "bg-purple-100 text-purple-800 border border-purple-200"
                          : "text-slate-500 hover:bg-slate-50 border border-transparent"
                      }`}
                    >
                      <span className="font-bold mr-1">{v.key}</span>
                      {v.name}
                      {v.is_winner && <Star className="w-3 h-3 inline ml-1 text-amber-500" />}
                    </button>
                  ))}
                  <div className="ml-auto">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1"
                      onClick={handleGenerateImage}
                      disabled={generatingImage}
                    >
                      {generatingImage ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                      {generatingImage ? "Generating..." : "Generate Image"}
                    </Button>
                  </div>
                </div>
              )}

              {/* ── Preview Area ── */}
              <div className="flex-1 overflow-y-auto bg-slate-100 p-4">
                <div className={`mx-auto transition-all ${previewMode === "mobile" ? "max-w-[375px]" : "max-w-[900px]"}`}>
                  {activeVariant?.content ? (
                    <LandingPagePreview content={activeVariant.content} style={activePage.style} />
                  ) : (
                    <div className="bg-white rounded-xl border p-12 text-center">
                      <p className="text-slate-400 text-sm">No content for this variant</p>
                    </div>
                  )}
                </div>
              </div>

              {/* ── AI Prompt Bar ── */}
              <div className="border-t bg-white p-3">
                {error && (
                  <div className="mb-2 flex items-center gap-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-1.5">
                    <AlertCircle className="w-3 h-3" /> {error}
                    <button onClick={() => setError("")} className="ml-auto text-red-400 hover:text-red-600">dismiss</button>
                  </div>
                )}
                {editHistory.length > 0 && (
                  <div className="mb-2 flex items-center gap-2 overflow-x-auto pb-1">
                    <Clock className="w-3 h-3 text-slate-400 flex-shrink-0" />
                    {editHistory.map((h, i) => (
                      <span key={i} className="text-[10px] bg-purple-50 text-purple-700 rounded-full px-2 py-0.5 whitespace-nowrap flex-shrink-0">
                        {h.length > 40 ? h.slice(0, 40) + "..." : h}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <textarea
                    ref={promptRef}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAiEdit(); }
                    }}
                    placeholder={`Edit with AI: "Change the headline to..." / "Make it more urgent" / "Add a pricing section" / "Rewrite for emergency tone"...`}
                    className="flex-1 min-h-[44px] max-h-[100px] rounded-xl border bg-slate-50 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                    rows={1}
                  />
                  <Button
                    onClick={handleAiEdit}
                    disabled={editing || !prompt.trim()}
                    className="h-[44px] w-[44px] rounded-xl p-0 bg-purple-600 hover:bg-purple-700"
                  >
                    {editing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  </Button>
                </div>
                <p className="text-[10px] text-slate-400 mt-1.5">
                  Editing variant <strong>{activeVariant?.key}: {activeVariant?.name}</strong> — AI will modify only what you ask for
                </p>
              </div>
            </>
          ) : null}
        </div>

        {/* ═══ GENERATE MODAL ═══ */}
        {showGenerate && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !generating && setShowGenerate(false)}>
            <Card className="w-full max-w-md" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="w-5 h-5 text-purple-600" /> Generate AI Landing Page
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-slate-700 mb-1 block">Service / Page Topic *</label>
                  <input
                    value={genService}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGenService(e.target.value)}
                    placeholder="e.g. Jaguar BCM Repair, Emergency Lockout..."
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-700 mb-1 block">Location</label>
                  <input
                    value={genLocation}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGenLocation(e.target.value)}
                    placeholder="e.g. Dallas TX, Arlington..."
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                {error && <p className="text-xs text-red-600">{error}</p>}
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" onClick={() => setShowGenerate(false)} disabled={generating}>
                    Cancel
                  </Button>
                  <Button className="flex-1 bg-purple-600 hover:bg-purple-700" onClick={handleGenerate} disabled={generating || !genService.trim()}>
                    {generating ? (
                      <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Generating...</>
                    ) : (
                      <><Sparkles className="w-4 h-4 mr-2" /> Generate 3 Variants</>
                    )}
                  </Button>
                </div>
                {generating && (
                  <p className="text-[11px] text-slate-500 text-center">AI is creating 3 page variants with strategy, copy, and trust elements. This takes 30-60 seconds.</p>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* ═══ CLONE MODAL ═══ */}
        {showClone && activePage && (
          <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !cloning && setShowClone(false)}>
            <Card className="w-full max-w-md" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Copy className="w-5 h-5 text-blue-600" /> Clone & Reuse Landing Page
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-slate-500">
                  Cloning <strong>{activePage.name}</strong>. AI will adapt all content for the new service/location.
                </p>
                <div>
                  <label className="text-xs font-medium text-slate-700 mb-1 block">New Service</label>
                  <input
                    value={cloneService}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCloneService(e.target.value)}
                    placeholder="e.g. BMW Key Programming"
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-700 mb-1 block">New Location</label>
                  <input
                    value={cloneLocation}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCloneLocation(e.target.value)}
                    placeholder="e.g. Fort Worth TX"
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-700 mb-1 block">Custom AI Instructions (optional)</label>
                  <textarea
                    value={cloneAdapt}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setCloneAdapt(e.target.value)}
                    placeholder="e.g. Keep the same layout but change pricing to start at $299..."
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 resize-none"
                    rows={3}
                  />
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" className="flex-1" onClick={() => setShowClone(false)} disabled={cloning}>
                    Cancel
                  </Button>
                  <Button className="flex-1 bg-blue-600 hover:bg-blue-700" onClick={handleClone} disabled={cloning}>
                    {cloning ? (
                      <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Cloning...</>
                    ) : (
                      <><Copy className="w-4 h-4 mr-2" /> Clone & Adapt</>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   LANDING PAGE PREVIEW — Renders content JSON as a visual preview
   ═══════════════════════════════════════════════════════════════════ */

function LandingPagePreview({ content, style }: { content: any; style?: any }) {
  if (!content) return <div className="bg-white rounded-xl border p-8 text-center text-slate-400">No content</div>;

  const hero = content.hero || {};
  const trustBar = content.trust_bar || {};
  const servicesSection = content.services_section || {};
  const whyUs = content.why_us_section || {};
  const reviews = content.reviews_section || {};
  const faq = content.faq_section || {};
  const ctaFooter = content.cta_footer || {};

  const primaryColor = style?.primary_color || "#6d28d9";
  const accentColor = style?.accent_color || "#2563eb";

  return (
    <div className="bg-white rounded-xl border overflow-hidden shadow-sm">
      {/* ── HERO ── */}
      <div
        className="relative text-white p-8 md:p-12 text-center"
        style={{
          background: hero.hero_image_url
            ? `linear-gradient(rgba(0,0,0,0.55), rgba(0,0,0,0.65)), url(${hero.hero_image_url}) center/cover no-repeat`
            : `linear-gradient(135deg, ${primaryColor}, ${primaryColor}dd)`,
        }}
      >
        {hero.urgency_badge && (
          <div className="inline-block bg-amber-400 text-amber-900 text-xs font-bold px-3 py-1 rounded-full mb-4">
            {hero.urgency_badge}
          </div>
        )}
        <h1 className="text-2xl md:text-3xl font-bold mb-3 leading-tight drop-shadow-lg">{hero.headline || "Your Headline Here"}</h1>
        <p className="text-white/90 text-sm md:text-base mb-6 max-w-xl mx-auto drop-shadow">{hero.subheadline || ""}</p>
        {hero.cta_text && (
          <button
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-bold text-sm shadow-lg transition-transform hover:scale-105"
            style={{ background: accentColor }}
          >
            <Phone className="w-4 h-4" />
            {hero.cta_text}
          </button>
        )}
        {hero.cta_phone && (
          <p className="text-white/70 text-xs mt-3 drop-shadow">
            <Phone className="w-3 h-3 inline mr-1" /> {hero.cta_phone}
          </p>
        )}
      </div>

      {/* ── TRUST BAR ── */}
      {trustBar.items && trustBar.items.length > 0 && (
        <div className="bg-slate-50 border-b px-4 py-3 flex flex-wrap items-center justify-center gap-4">
          {trustBar.items.map((item: string, i: number) => (
            <div key={i} className="flex items-center gap-1.5 text-xs text-slate-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
              {item}
            </div>
          ))}
        </div>
      )}

      {/* ── SERVICES ── */}
      {servicesSection.services && servicesSection.services.length > 0 && (
        <div className="px-6 py-8">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{servicesSection.heading || "Our Services"}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {servicesSection.services.map((svc: any, i: number) => (
              <div key={i} className="flex items-start gap-3 p-4 rounded-lg border bg-slate-50/50">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: `${primaryColor}15` }}>
                  <SectionIcon name={svc.icon} color={primaryColor} />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-800 text-sm">{svc.name}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">{svc.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── WHY US ── */}
      {whyUs.reasons && whyUs.reasons.length > 0 && (
        <div className="px-6 py-8 bg-slate-50 border-t border-b">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{whyUs.heading || "Why Choose Us"}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {whyUs.reasons.map((r: any, i: number) => (
              <div key={i} className="text-center p-4">
                <div className="w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-3" style={{ background: `${primaryColor}15` }}>
                  <SectionIcon name={r.icon} color={primaryColor} />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm mb-1">{r.title}</h3>
                <p className="text-xs text-slate-500">{r.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── REVIEWS ── */}
      {reviews.reviews && reviews.reviews.length > 0 && (
        <div className="px-6 py-8">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{reviews.heading || "Customer Reviews"}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {reviews.reviews.slice(0, 4).map((r: any, i: number) => (
              <div key={i} className="p-4 rounded-lg border">
                <div className="flex items-center gap-1 mb-2">
                  {Array.from({ length: r.rating || 5 }).map((_, si) => (
                    <Star key={si} className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                  ))}
                </div>
                <p className="text-xs text-slate-600 italic mb-2">&ldquo;{r.text}&rdquo;</p>
                <p className="text-[11px] text-slate-400 font-medium">— {r.name}{r.service ? ` (${r.service})` : ""}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── FAQ ── */}
      {faq.faqs && faq.faqs.length > 0 && (
        <div className="px-6 py-8 bg-slate-50 border-t">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{faq.heading || "FAQ"}</h2>
          <div className="space-y-3 max-w-xl mx-auto">
            {faq.faqs.map((f: any, i: number) => (
              <div key={i} className="bg-white rounded-lg border p-4">
                <h3 className="font-semibold text-slate-800 text-sm mb-1">{f.question}</h3>
                <p className="text-xs text-slate-500">{f.answer}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── CTA FOOTER ── */}
      {ctaFooter.heading && (
        <div
          className="text-white p-8 text-center"
          style={{ background: `linear-gradient(135deg, ${primaryColor}, ${primaryColor}dd)` }}
        >
          <h2 className="text-xl font-bold mb-2">{ctaFooter.heading}</h2>
          {ctaFooter.subtext && <p className="text-white/70 text-sm mb-4">{ctaFooter.subtext}</p>}
          {ctaFooter.cta_text && (
            <button
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-bold text-sm shadow-lg"
              style={{ background: accentColor }}
            >
              <Phone className="w-4 h-4" />
              {ctaFooter.cta_text}
            </button>
          )}
          {ctaFooter.cta_phone && (
            <p className="text-white/50 text-xs mt-3">{ctaFooter.cta_phone}</p>
          )}
        </div>
      )}
    </div>
  );
}

function SectionIcon({ name, color }: { name: string; color: string }) {
  const cls = "w-4 h-4";
  const style = { color };
  switch (name) {
    case "key": return <Zap className={cls} style={style} />;
    case "shield": return <Shield className={cls} style={style} />;
    case "clock": return <Clock className={cls} style={style} />;
    case "star": return <Star className={cls} style={style} />;
    case "wrench": return <Wand2 className={cls} style={style} />;
    case "phone": return <Phone className={cls} style={style} />;
    case "map": return <MapPin className={cls} style={style} />;
    default: return <CheckCircle2 className={cls} style={style} />;
  }
}
