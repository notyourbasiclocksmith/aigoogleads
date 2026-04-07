"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Globe, Sparkles, Loader2, Send, Plus, Copy, Trash2,
  Eye, Pencil, CheckCircle2, AlertCircle, ChevronRight, ChevronLeft,
  Smartphone, Monitor, Wand2, RotateCcw, GripVertical, X,
  Phone, Star, Shield, ArrowRight, MapPin, MessageSquare,
  Zap, FileText, ExternalLink, Palette, Type, Layout,
  Image as ImageIcon, Quote, HelpCircle, BarChart3,
  Clock, ChevronDown, ChevronUp, Settings2, Undo2, Save,
  Layers, PanelRightClose, PanelRight, MousePointerClick,
  Users, Award, Play, Mail, Hash, Grip, Move,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════

interface LandingPageItem {
  id: string; name: string; slug: string; service: string; location: string;
  status: string; page_type: string; is_ai_generated: boolean;
  audit_score: number | null; variant_count: number;
  created_at: string | null; published_at: string | null;
}

interface Variant {
  id: string; key: string; name: string; content: any;
  is_active: boolean; is_winner: boolean;
  visits: number; conversions: number; conversion_rate: number;
}

interface LandingPageDetail {
  id: string; name: string; slug: string; service: string; location: string;
  status: string; strategy: any; content: any; style: any; seo: any;
  audit_score: number | null; variants: Variant[]; created_at: string | null;
}

interface Section {
  id: string;
  type: SectionType;
  data: any;
}

type SectionType =
  | "hero" | "trust_bar" | "services" | "why_us" | "reviews"
  | "faq" | "cta_banner" | "contact_form" | "stats" | "gallery"
  | "video" | "text_block";

// ═══════════════════════════════════════════════════════════════════
// SECTION CATALOG — what users can drag onto the page
// ═══════════════════════════════════════════════════════════════════

const SECTION_CATALOG: { type: SectionType; label: string; icon: any; description: string; defaultData: any }[] = [
  {
    type: "hero", label: "Hero Banner", icon: Layout, description: "Main headline with CTA",
    defaultData: { headline: "Your Headline Here", subheadline: "Describe your service in one compelling sentence", cta_text: "Call Now", cta_phone: "", urgency_badge: "", hero_image_url: "" },
  },
  {
    type: "trust_bar", label: "Trust Bar", icon: Shield, description: "Trust badges & credentials",
    defaultData: { items: ["Licensed & Insured", "5-Star Rated", "24/7 Available", "Free Estimates"] },
  },
  {
    type: "services", label: "Services Grid", icon: Layers, description: "Service cards with icons",
    defaultData: { heading: "Our Services", services: [
      { name: "Service One", description: "Brief description of this service", icon: "wrench" },
      { name: "Service Two", description: "Brief description of this service", icon: "shield" },
      { name: "Service Three", description: "Brief description of this service", icon: "clock" },
    ]},
  },
  {
    type: "why_us", label: "Why Choose Us", icon: Award, description: "Differentiators & reasons",
    defaultData: { heading: "Why Choose Us", reasons: [
      { title: "Expert Team", description: "Years of experience you can trust", icon: "star" },
      { title: "Fast Response", description: "We arrive within 30 minutes", icon: "clock" },
      { title: "Best Price", description: "Competitive pricing guaranteed", icon: "shield" },
    ]},
  },
  {
    type: "reviews", label: "Reviews", icon: Star, description: "Customer testimonials",
    defaultData: { heading: "What Our Customers Say", reviews: [
      { name: "John D.", text: "Excellent service! Fast and professional.", rating: 5, service: "" },
      { name: "Sarah M.", text: "Best in the area. Highly recommend!", rating: 5, service: "" },
    ]},
  },
  {
    type: "faq", label: "FAQ", icon: HelpCircle, description: "Common questions & answers",
    defaultData: { heading: "Frequently Asked Questions", faqs: [
      { question: "How quickly can you respond?", answer: "We offer same-day service for most requests." },
      { question: "Do you offer free estimates?", answer: "Yes, all estimates are free with no obligation." },
    ]},
  },
  {
    type: "contact_form", label: "Contact Form", icon: Mail, description: "Lead capture form",
    defaultData: { heading: "Get Your Free Quote", subheading: "Fill out the form and we'll respond within minutes", embed_slug: "", embed_url: "" },
  },
  {
    type: "cta_banner", label: "CTA Banner", icon: MousePointerClick, description: "Call-to-action section",
    defaultData: { heading: "Ready to Get Started?", subtext: "Call now for a free estimate", cta_text: "Call Now", cta_phone: "" },
  },
  {
    type: "stats", label: "Stats / Numbers", icon: Hash, description: "Impressive statistics",
    defaultData: { heading: "", stats: [
      { number: "500+", label: "Happy Customers" },
      { number: "24/7", label: "Availability" },
      { number: "15+", label: "Years Experience" },
      { number: "4.9", label: "Star Rating" },
    ]},
  },
  {
    type: "text_block", label: "Text Block", icon: Type, description: "Custom content section",
    defaultData: { heading: "About Us", content: "Write your custom content here. Tell your story, explain your process, or highlight what makes you different." },
  },
  {
    type: "gallery", label: "Image Gallery", icon: ImageIcon, description: "Photo showcase",
    defaultData: { heading: "Our Work", images: [] },
  },
  {
    type: "video", label: "Video", icon: Play, description: "Embedded video section",
    defaultData: { heading: "", video_url: "", caption: "" },
  },
];

// ═══════════════════════════════════════════════════════════════════
// TEMPLATES
// ═══════════════════════════════════════════════════════════════════

const TEMPLATES: { name: string; description: string; icon: string; sections: SectionType[] }[] = [
  { name: "Emergency Service", description: "Urgent, high-converting layout", icon: "🚨", sections: ["hero", "trust_bar", "services", "stats", "reviews", "contact_form", "faq", "cta_banner"] },
  { name: "Professional Service", description: "Trust-focused, detail-rich", icon: "🏢", sections: ["hero", "trust_bar", "why_us", "services", "reviews", "contact_form", "faq", "cta_banner"] },
  { name: "Lead Generation", description: "Form-first, conversion-optimized", icon: "📋", sections: ["hero", "trust_bar", "contact_form", "services", "stats", "reviews", "cta_banner"] },
  { name: "Minimal Clean", description: "Simple and fast", icon: "✨", sections: ["hero", "services", "contact_form", "cta_banner"] },
  { name: "Full Feature", description: "Everything included", icon: "🎯", sections: ["hero", "trust_bar", "services", "why_us", "stats", "reviews", "gallery", "faq", "contact_form", "cta_banner"] },
];

// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════

function genId() { return Math.random().toString(36).slice(2, 10); }

function contentToSections(content: any): Section[] {
  if (!content) return [];
  const sections: Section[] = [];
  if (content.hero) sections.push({ id: genId(), type: "hero", data: content.hero });
  if (content.trust_bar?.items?.length) sections.push({ id: genId(), type: "trust_bar", data: content.trust_bar });
  if (content.services_section?.services?.length) sections.push({ id: genId(), type: "services", data: content.services_section });
  if (content.why_us_section?.reasons?.length) sections.push({ id: genId(), type: "why_us", data: content.why_us_section });
  if (content.stats_section?.stats?.length) sections.push({ id: genId(), type: "stats", data: content.stats_section });
  if (content.reviews_section?.reviews?.length) sections.push({ id: genId(), type: "reviews", data: content.reviews_section });
  if (content.gallery_section) sections.push({ id: genId(), type: "gallery", data: content.gallery_section });
  if (content.video_section) sections.push({ id: genId(), type: "video", data: content.video_section });
  if (content.text_block) sections.push({ id: genId(), type: "text_block", data: content.text_block });
  if (content.contact_form) sections.push({ id: genId(), type: "contact_form", data: content.contact_form });
  if (content.faq_section?.faqs?.length) sections.push({ id: genId(), type: "faq", data: content.faq_section });
  if (content.cta_footer) sections.push({ id: genId(), type: "cta_banner", data: content.cta_footer });
  return sections;
}

function sectionsToContent(sections: Section[]): any {
  const c: any = {};
  for (const s of sections) {
    switch (s.type) {
      case "hero": c.hero = s.data; break;
      case "trust_bar": c.trust_bar = s.data; break;
      case "services": c.services_section = s.data; break;
      case "why_us": c.why_us_section = s.data; break;
      case "reviews": c.reviews_section = s.data; break;
      case "faq": c.faq_section = s.data; break;
      case "cta_banner": c.cta_footer = s.data; break;
      case "contact_form": c.contact_form = s.data; break;
      case "stats": c.stats_section = s.data; break;
      case "gallery": c.gallery_section = s.data; break;
      case "video": c.video_section = s.data; break;
      case "text_block": c.text_block = s.data; break;
    }
  }
  return c;
}

function sectionLabel(type: SectionType): string {
  return SECTION_CATALOG.find(c => c.type === type)?.label || type;
}

function SectionTypeIcon({ type, className = "w-4 h-4" }: { type: SectionType; className?: string }) {
  const catalog = SECTION_CATALOG.find(c => c.type === type);
  if (!catalog) return <Layers className={className} />;
  const Icon = catalog.icon;
  return <Icon className={className} />;
}

// ═══════════════════════════════════════════════════════════════════
// MAIN PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════

export default function LandingPageStudioPage() {
  // ── Page list state
  const [pages, setPages] = useState<LandingPageItem[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [showPageList, setShowPageList] = useState(true);

  // ── Active page state
  const [activePage, setActivePage] = useState<LandingPageDetail | null>(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const [activeVariantIdx, setActiveVariantIdx] = useState(0);

  // ── Builder state
  const [sections, setSections] = useState<Section[]>([]);
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
  const [showProperties, setShowProperties] = useState(true);
  const [previewMode, setPreviewMode] = useState<"desktop" | "mobile">("desktop");
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);

  // ── Style state
  const [primaryColor, setPrimaryColor] = useState("#6d28d9");
  const [accentColor, setAccentColor] = useState("#2563eb");
  const [fontFamily, setFontFamily] = useState("Inter");

  // ── DnD state
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [dragFromPalette, setDragFromPalette] = useState<SectionType | null>(null);

  // ── AI prompt state
  const [prompt, setPrompt] = useState("");
  const [editing, setEditing] = useState(false);

  // ── Modals
  const [showGenerate, setShowGenerate] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showClone, setShowClone] = useState(false);
  const [genService, setGenService] = useState("");
  const [genLocation, setGenLocation] = useState("");
  const [generating, setGenerating] = useState(false);
  const [cloneService, setCloneService] = useState("");
  const [cloneLocation, setCloneLocation] = useState("");
  const [cloneAdapt, setCloneAdapt] = useState("");
  const [cloning, setCloning] = useState(false);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [imageEngine, setImageEngine] = useState<"google" | "dalle" | "flux" | "stability">("google");

  const [error, setError] = useState("");

  const selectedSection = sections.find(s => s.id === selectedSectionId) || null;

  // ── Load pages
  const loadPages = useCallback(async () => {
    try {
      const data = await api.get("/api/v2/strategist/landing-pages");
      setPages(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
    finally { setLoadingList(false); }
  }, []);

  useEffect(() => { loadPages(); }, [loadPages]);

  // ── Load page detail
  async function loadPage(id: string) {
    setLoadingPage(true); setError("");
    try {
      const data = await api.get(`/api/v2/strategist/landing-pages/${id}`);
      setActivePage(data);
      setActiveVariantIdx(0);
      const variant = data.variants?.[0];
      if (variant?.content) setSections(contentToSections(variant.content));
      else setSections([]);
      if (data.style) {
        setPrimaryColor(data.style.primary_color || "#6d28d9");
        setAccentColor(data.style.accent_color || "#2563eb");
        setFontFamily(data.style.font_family || "Inter");
      }
      setSelectedSectionId(null);
      setHasChanges(false);
    } catch (e: any) { setError(e.message || "Failed to load page"); }
    finally { setLoadingPage(false); }
  }

  // ── Switch variant
  function switchVariant(idx: number) {
    if (!activePage) return;
    setActiveVariantIdx(idx);
    const variant = activePage.variants?.[idx];
    if (variant?.content) setSections(contentToSections(variant.content));
    else setSections([]);
    setSelectedSectionId(null);
    setHasChanges(false);
  }

  // ── Save sections back to variant
  async function handleSave() {
    if (!activePage) return;
    const variant = activePage.variants?.[activeVariantIdx];
    if (!variant) return;
    setSaving(true);
    try {
      const content = sectionsToContent(sections);
      await api.patch(`/api/v2/strategist/landing-pages/${activePage.id}/variants/${variant.id}`, {
        content_json: content,
      });
      // Update local state
      const updated = { ...activePage };
      updated.variants = [...updated.variants];
      updated.variants[activeVariantIdx] = { ...variant, content };
      if (activePage.style?.primary_color !== primaryColor || activePage.style?.accent_color !== accentColor) {
        // Also save style if changed — we'll include it
      }
      setActivePage(updated);
      setHasChanges(false);
    } catch (e: any) { setError(e.message || "Save failed"); }
    finally { setSaving(false); }
  }

  // ── Modify sections (marks dirty)
  function updateSections(newSections: Section[]) {
    setSections(newSections);
    setHasChanges(true);
  }

  function updateSectionData(id: string, newData: any) {
    updateSections(sections.map(s => s.id === id ? { ...s, data: newData } : s));
  }

  function addSection(type: SectionType, atIndex?: number) {
    const catalog = SECTION_CATALOG.find(c => c.type === type);
    if (!catalog) return;
    const newSection: Section = { id: genId(), type, data: { ...catalog.defaultData } };
    const idx = atIndex !== undefined ? atIndex : sections.length;
    const newSections = [...sections];
    newSections.splice(idx, 0, newSection);
    updateSections(newSections);
    setSelectedSectionId(newSection.id);
  }

  function removeSection(id: string) {
    updateSections(sections.filter(s => s.id !== id));
    if (selectedSectionId === id) setSelectedSectionId(null);
  }

  function duplicateSection(id: string) {
    const idx = sections.findIndex(s => s.id === id);
    if (idx === -1) return;
    const original = sections[idx];
    const newSection: Section = { id: genId(), type: original.type, data: JSON.parse(JSON.stringify(original.data)) };
    const newSections = [...sections];
    newSections.splice(idx + 1, 0, newSection);
    updateSections(newSections);
    setSelectedSectionId(newSection.id);
  }

  function moveSection(fromIdx: number, toIdx: number) {
    if (fromIdx === toIdx) return;
    const newSections = [...sections];
    const [moved] = newSections.splice(fromIdx, 1);
    newSections.splice(toIdx, 0, moved);
    updateSections(newSections);
  }

  // ── DnD handlers
  function handleDragStart(idx: number) { setDragIdx(idx); }
  function handleDragOver(e: React.DragEvent, idx: number) { e.preventDefault(); setDragOverIdx(idx); }
  function handleDragEnd() {
    if (dragIdx !== null && dragOverIdx !== null && dragIdx !== dragOverIdx) {
      moveSection(dragIdx, dragOverIdx);
    }
    if (dragFromPalette && dragOverIdx !== null) {
      addSection(dragFromPalette, dragOverIdx);
    }
    setDragIdx(null); setDragOverIdx(null); setDragFromPalette(null);
  }

  // ── AI edit
  async function handleAiEdit() {
    if (!prompt.trim() || !activePage || editing) return;
    const variant = activePage.variants[activeVariantIdx];
    if (!variant) return;
    setEditing(true); setError("");
    try {
      const result = await api.post(`/api/v2/strategist/landing-pages/${activePage.id}/ai-edit`, {
        variant_id: variant.id, prompt: prompt.trim(),
      });
      const updated = { ...activePage };
      updated.variants = [...updated.variants];
      updated.variants[activeVariantIdx] = { ...variant, content: result.content };
      setActivePage(updated);
      setSections(contentToSections(result.content));
      setPrompt("");
    } catch (e: any) { setError(e.message || "AI edit failed"); }
    finally { setEditing(false); }
  }

  // ── Generate new LP
  async function handleGenerate() {
    if (!genService.trim() || generating) return;
    setGenerating(true); setError("");
    try {
      const result = await api.post("/api/v2/strategist/landing-pages/generate-from-prompt", {
        prompt: genService, service: genService, location: genLocation,
        image_engine: imageEngine,
      });
      setShowGenerate(false); setGenService(""); setGenLocation("");
      await loadPages();
      if (result.landing_page_id) await loadPage(result.landing_page_id);
    } catch (e: any) { setError(e.message || "Generation failed"); }
    finally { setGenerating(false); }
  }

  // ── Apply template
  function applyTemplate(template: typeof TEMPLATES[0]) {
    const newSections: Section[] = template.sections.map(type => {
      const catalog = SECTION_CATALOG.find(c => c.type === type)!;
      return { id: genId(), type, data: { ...catalog.defaultData } };
    });
    updateSections(newSections);
    setShowTemplates(false);
    setSelectedSectionId(null);
  }

  // ── Clone LP
  async function handleClone() {
    if (!activePage || cloning) return;
    setCloning(true); setError("");
    try {
      const result = await api.post(`/api/v2/strategist/landing-pages/${activePage.id}/clone`, {
        new_service: cloneService, new_location: cloneLocation,
        adapt_prompt: cloneAdapt || `Adapt for '${cloneService}'${cloneLocation ? ` in '${cloneLocation}'` : ""}`,
      });
      setShowClone(false); setCloneService(""); setCloneLocation(""); setCloneAdapt("");
      await loadPages();
      if (result.landing_page_id) await loadPage(result.landing_page_id);
    } catch (e: any) { setError(e.message || "Clone failed"); }
    finally { setCloning(false); }
  }

  // ── Status update
  async function updateStatus(status: string) {
    if (!activePage) return;
    try {
      await api.patch(`/api/v2/strategist/landing-pages/${activePage.id}/status`, { status });
      setActivePage({ ...activePage, status }); loadPages();
    } catch (e: any) { setError(e.message || "Status update failed"); }
  }

  // ── Generate image
  async function handleGenerateImage() {
    if (!activePage || generatingImage) return;
    const variant = activePage.variants[activeVariantIdx];
    if (!variant) return;
    setGeneratingImage(true); setError("");
    try {
      const result = await api.post(`/api/v2/strategist/landing-pages/${activePage.id}/generate-image`, {
        variant_id: variant.id, engine: imageEngine,
      });
      // Update hero image in sections
      setSections(prev => prev.map(s =>
        s.type === "hero" ? { ...s, data: { ...s.data, hero_image_url: result.image_url } } : s
      ));
      setHasChanges(true);
    } catch (e: any) { setError(e.message || "Image generation failed"); }
    finally { setGeneratingImage(false); }
  }

  // ═══════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════

  return (
    <AppLayout>
      <div className="flex h-[calc(100vh-64px)] overflow-hidden -m-4 lg:-m-8 xl:-m-10">

        {/* ═══ LEFT: PAGE LIST (collapsible) ═══ */}
        {showPageList && (
          <div className="w-64 border-r bg-white flex flex-col overflow-hidden flex-shrink-0">
            <div className="p-3 border-b flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-violet-600" />
                <span className="font-semibold text-sm text-slate-800">Pages</span>
                <Badge variant="secondary" className="text-[10px] px-1.5">{pages.length}</Badge>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => setShowGenerate(true)} className="p-1 rounded-md hover:bg-slate-100 text-slate-500">
                  <Plus className="w-4 h-4" />
                </button>
                <button onClick={() => setShowPageList(false)} className="p-1 rounded-md hover:bg-slate-100 text-slate-400">
                  <ChevronLeft className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
              {loadingList ? (
                <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-slate-400" /></div>
              ) : pages.length === 0 ? (
                <div className="text-center py-8 px-4">
                  <Globe className="w-8 h-8 text-slate-200 mx-auto mb-2" />
                  <p className="text-xs text-slate-400 mb-3">No landing pages yet</p>
                  <Button size="sm" className="text-xs bg-violet-600 hover:bg-violet-700" onClick={() => setShowGenerate(true)}>
                    <Sparkles className="w-3 h-3 mr-1" /> Generate First
                  </Button>
                </div>
              ) : pages.map(p => (
                <button
                  key={p.id}
                  onClick={() => loadPage(p.id)}
                  className={`w-full text-left rounded-lg px-3 py-2.5 transition-all text-xs ${
                    activePage?.id === p.id
                      ? "bg-violet-50 border border-violet-200 ring-1 ring-violet-100"
                      : "hover:bg-slate-50 border border-transparent"
                  }`}
                >
                  <div className="font-medium text-slate-800 truncate">{p.name}</div>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className={`inline-flex items-center text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                      p.status === "published" ? "bg-emerald-50 text-emerald-700" :
                      p.status === "draft" ? "bg-slate-100 text-slate-500" : "bg-amber-50 text-amber-700"
                    }`}>{p.status}</span>
                    {p.audit_score !== null && (
                      <span className={`text-[9px] font-medium ${p.audit_score >= 80 ? "text-emerald-600" : p.audit_score >= 60 ? "text-amber-600" : "text-red-500"}`}>
                        {p.audit_score}/100
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ═══ CENTER: MAIN BUILDER ═══ */}
        <div className="flex-1 flex flex-col overflow-hidden bg-slate-100/80">

          {/* ── Top Toolbar ── */}
          <div className="border-b bg-white px-3 py-2 flex items-center gap-2 flex-shrink-0">
            {!showPageList && (
              <button onClick={() => setShowPageList(true)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 mr-1">
                <PanelRight className="w-4 h-4" />
              </button>
            )}

            {activePage ? (
              <>
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <div className="min-w-0">
                    <h1 className="text-sm font-bold text-slate-800 truncate">{activePage.name}</h1>
                    <p className="text-[10px] text-slate-400 truncate">/lp/{activePage.slug}</p>
                  </div>
                  <Badge className={`text-[9px] flex-shrink-0 ${
                    activePage.status === "published" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                    activePage.status === "draft" ? "bg-slate-50 text-slate-500 border-slate-200" : "bg-amber-50 text-amber-700 border-amber-200"
                  }`}>{activePage.status}</Badge>
                </div>

                {/* Variant tabs */}
                {activePage.variants.length > 1 && (
                  <div className="flex items-center border rounded-lg overflow-hidden mx-2">
                    {activePage.variants.map((v, i) => (
                      <button
                        key={v.id}
                        onClick={() => switchVariant(i)}
                        className={`px-2.5 py-1 text-[11px] font-medium transition-all ${
                          activeVariantIdx === i ? "bg-violet-100 text-violet-800" : "text-slate-400 hover:bg-slate-50"
                        }`}
                      >
                        {v.key}
                        {v.is_winner && <Star className="w-2.5 h-2.5 inline ml-0.5 text-amber-500 fill-amber-500" />}
                      </button>
                    ))}
                  </div>
                )}

                {/* Preview toggle */}
                <div className="flex items-center border rounded-lg overflow-hidden">
                  <button onClick={() => setPreviewMode("desktop")} className={`p-1.5 ${previewMode === "desktop" ? "bg-slate-100" : "hover:bg-slate-50"}`}>
                    <Monitor className="w-3.5 h-3.5 text-slate-500" />
                  </button>
                  <button onClick={() => setPreviewMode("mobile")} className={`p-1.5 ${previewMode === "mobile" ? "bg-slate-100" : "hover:bg-slate-50"}`}>
                    <Smartphone className="w-3.5 h-3.5 text-slate-500" />
                  </button>
                </div>

                {/* Image Engine Selector */}
                <div className="flex items-center border rounded-lg overflow-hidden">
                  {([
                    { v: "google" as const, l: "🍌" },
                    { v: "flux" as const, l: "⚡" },
                    { v: "dalle" as const, l: "🎨" },
                    { v: "stability" as const, l: "🖼️" },
                  ] as const).map(e => (
                    <button key={e.v} onClick={() => setImageEngine(e.v)} title={`Image engine: ${e.v === "google" ? "Nano Banana" : e.v === "flux" ? "Flux.1" : e.v === "dalle" ? "DALL-E 3" : "Stability"}`}
                      className={`px-1.5 py-1 text-xs ${imageEngine === e.v ? "bg-violet-100 text-violet-700" : "hover:bg-slate-50 text-slate-500"}`}>
                      {e.l}
                    </button>
                  ))}
                </div>

                <button onClick={handleGenerateImage} disabled={generatingImage} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 disabled:opacity-50" title={`Generate hero image (${imageEngine === "google" ? "Nano Banana" : imageEngine})`}>
                  {generatingImage ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImageIcon className="w-4 h-4" />}
                </button>

                <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1" onClick={() => setShowTemplates(true)}>
                  <Layout className="w-3 h-3" /> Templates
                </Button>

                <Button size="sm" variant="outline" className="h-7 text-[11px] gap-1" onClick={() => setShowClone(true)}>
                  <Copy className="w-3 h-3" /> Clone
                </Button>

                {hasChanges && (
                  <Button size="sm" className="h-7 text-[11px] gap-1 bg-violet-600 hover:bg-violet-700" onClick={handleSave} disabled={saving}>
                    {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    {saving ? "Saving..." : "Save"}
                  </Button>
                )}

                {activePage.status === "draft" ? (
                  <Button size="sm" className="h-7 text-[11px] bg-emerald-600 hover:bg-emerald-700" onClick={() => updateStatus("published")}>
                    Publish
                  </Button>
                ) : activePage.status === "published" ? (
                  <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => updateStatus("paused")}>
                    Unpublish
                  </Button>
                ) : null}

                <button
                  onClick={() => setShowProperties(!showProperties)}
                  className={`p-1.5 rounded-lg transition-colors ${showProperties ? "bg-violet-100 text-violet-700" : "hover:bg-slate-100 text-slate-500"}`}
                  title="Toggle properties panel"
                >
                  <Settings2 className="w-4 h-4" />
                </button>
              </>
            ) : (
              <div className="flex-1" />
            )}
          </div>

          {/* ── Builder Canvas + Palette ── */}
          {!activePage && !loadingPage ? (
            /* Empty state */
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center max-w-lg px-8">
                <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-100 to-indigo-100 flex items-center justify-center mx-auto mb-6">
                  <Wand2 className="w-10 h-10 text-violet-600" />
                </div>
                <h2 className="text-2xl font-bold text-slate-800 mb-3">Landing Page Studio</h2>
                <p className="text-sm text-slate-500 mb-8 leading-relaxed">
                  Create beautiful, high-converting landing pages with drag-and-drop editing, AI generation, and A/B testing.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                  <Button onClick={() => setShowGenerate(true)} className="bg-violet-600 hover:bg-violet-700 h-11 px-6">
                    <Sparkles className="w-4 h-4 mr-2" /> AI Generate
                  </Button>
                  <Button variant="outline" className="h-11 px-6" onClick={() => { setShowTemplates(true); setSections([]); setActivePage({ id: "new", name: "New Page", slug: "", service: "", location: "", status: "draft", strategy: {}, content: {}, style: {}, seo: {}, audit_score: null, variants: [], created_at: null }); }}>
                    <Layout className="w-4 h-4 mr-2" /> Start from Template
                  </Button>
                </div>
              </div>
            </div>
          ) : loadingPage ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-violet-500" />
            </div>
          ) : (
            <div className="flex-1 flex overflow-hidden">

              {/* ── Section Palette (left narrow strip) ── */}
              <div className="w-14 border-r bg-white flex flex-col items-center py-2 gap-1 overflow-y-auto flex-shrink-0">
                <div className="text-[8px] font-bold text-slate-400 uppercase tracking-wider mb-1">Add</div>
                {SECTION_CATALOG.map(cat => {
                  const Icon = cat.icon;
                  return (
                    <button
                      key={cat.type}
                      draggable
                      onDragStart={() => setDragFromPalette(cat.type)}
                      onDragEnd={handleDragEnd}
                      onClick={() => addSection(cat.type)}
                      className="w-10 h-10 rounded-lg hover:bg-violet-50 flex items-center justify-center text-slate-400 hover:text-violet-600 transition-all group relative"
                      title={cat.label}
                    >
                      <Icon className="w-4 h-4" />
                      <div className="absolute left-12 bg-slate-800 text-white text-[10px] px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none z-50 transition-opacity">
                        {cat.label}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* ── Canvas ── */}
              <div className="flex-1 overflow-y-auto p-4 lg:p-6">
                <div className={`mx-auto transition-all duration-300 ${previewMode === "mobile" ? "max-w-[400px]" : "max-w-[880px]"}`}>

                  {sections.length === 0 ? (
                    <div className="bg-white rounded-2xl border-2 border-dashed border-slate-200 p-16 text-center">
                      <Layers className="w-12 h-12 text-slate-200 mx-auto mb-4" />
                      <h3 className="font-semibold text-slate-600 mb-2">Start Building Your Page</h3>
                      <p className="text-sm text-slate-400 mb-6">Drag sections from the left palette, or pick a template to get started.</p>
                      <div className="flex gap-2 justify-center">
                        <Button size="sm" variant="outline" onClick={() => addSection("hero")}>
                          <Plus className="w-3 h-3 mr-1" /> Add Hero
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setShowTemplates(true)}>
                          <Layout className="w-3 h-3 mr-1" /> Use Template
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-0">
                      {sections.map((section, idx) => (
                        <div
                          key={section.id}
                          draggable
                          onDragStart={() => handleDragStart(idx)}
                          onDragOver={(e) => handleDragOver(e, idx)}
                          onDragEnd={handleDragEnd}
                          onClick={() => setSelectedSectionId(section.id)}
                          className={`group relative transition-all duration-150 ${
                            selectedSectionId === section.id
                              ? "ring-2 ring-violet-400 ring-offset-2 rounded-xl"
                              : "hover:ring-1 hover:ring-slate-300 hover:ring-offset-1 rounded-xl"
                          } ${dragOverIdx === idx ? "border-t-2 border-violet-500" : ""}`}
                        >
                          {/* Section controls overlay */}
                          <div className={`absolute -top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1 bg-white shadow-lg rounded-full px-1 py-0.5 border transition-opacity ${
                            selectedSectionId === section.id ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                          }`}>
                            <button className="p-1 rounded-full hover:bg-slate-100 cursor-grab active:cursor-grabbing text-slate-400">
                              <GripVertical className="w-3 h-3" />
                            </button>
                            <span className="text-[9px] font-medium text-slate-500 px-1">{sectionLabel(section.type)}</span>
                            {idx > 0 && (
                              <button onClick={(e) => { e.stopPropagation(); moveSection(idx, idx - 1); }} className="p-1 rounded-full hover:bg-slate-100 text-slate-400">
                                <ChevronUp className="w-3 h-3" />
                              </button>
                            )}
                            {idx < sections.length - 1 && (
                              <button onClick={(e) => { e.stopPropagation(); moveSection(idx, idx + 1); }} className="p-1 rounded-full hover:bg-slate-100 text-slate-400">
                                <ChevronDown className="w-3 h-3" />
                              </button>
                            )}
                            <button onClick={(e) => { e.stopPropagation(); duplicateSection(section.id); }} className="p-1 rounded-full hover:bg-slate-100 text-slate-400">
                              <Copy className="w-3 h-3" />
                            </button>
                            <button onClick={(e) => { e.stopPropagation(); removeSection(section.id); }} className="p-1 rounded-full hover:bg-red-50 text-red-400">
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>

                          {/* Section Preview */}
                          <SectionPreview section={section} primaryColor={primaryColor} accentColor={accentColor} />
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* ── AI Edit Bar at bottom of canvas ── */}
                {activePage && activePage.id !== "new" && (
                  <div className="max-w-[880px] mx-auto mt-6">
                    {error && (
                      <div className="mb-2 flex items-center gap-2 text-xs text-red-600 bg-red-50 rounded-xl px-4 py-2">
                        <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                        <button onClick={() => setError("")} className="ml-auto text-red-400 hover:text-red-600 text-xs">✕</button>
                      </div>
                    )}
                    <div className="flex gap-2 bg-white rounded-2xl border shadow-sm p-2">
                      <div className="flex-1 relative">
                        <Wand2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-violet-400" />
                        <input
                          value={prompt}
                          onChange={(e) => setPrompt(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAiEdit(); } }}
                          placeholder='AI: "Make it more urgent" / "Add pricing" / "Rewrite for plumbing"...'
                          className="w-full pl-10 pr-4 py-2.5 text-sm focus:outline-none rounded-xl bg-slate-50"
                        />
                      </div>
                      <Button onClick={handleAiEdit} disabled={editing || !prompt.trim()} className="h-10 px-4 bg-violet-600 hover:bg-violet-700 rounded-xl">
                        {editing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* ═══ RIGHT: PROPERTIES PANEL ═══ */}
              {showProperties && selectedSection && (
                <div className="w-80 border-l bg-white flex flex-col overflow-hidden flex-shrink-0">
                  <div className="p-3 border-b flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <SectionTypeIcon type={selectedSection.type} className="w-4 h-4 text-violet-600" />
                      <span className="font-semibold text-sm text-slate-800">{sectionLabel(selectedSection.type)}</span>
                    </div>
                    <button onClick={() => setSelectedSectionId(null)} className="p-1 rounded-md hover:bg-slate-100 text-slate-400">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto p-3">
                    <PropertiesPanel
                      section={selectedSection}
                      onUpdate={(data) => updateSectionData(selectedSection.id, data)}
                      primaryColor={primaryColor}
                      accentColor={accentColor}
                      onPrimaryChange={(c) => { setPrimaryColor(c); setHasChanges(true); }}
                      onAccentChange={(c) => { setAccentColor(c); setHasChanges(true); }}
                    />
                  </div>
                </div>
              )}

              {/* Style panel when no section selected */}
              {showProperties && !selectedSection && activePage && (
                <div className="w-80 border-l bg-white flex flex-col overflow-hidden flex-shrink-0">
                  <div className="p-3 border-b">
                    <div className="flex items-center gap-2">
                      <Palette className="w-4 h-4 text-violet-600" />
                      <span className="font-semibold text-sm text-slate-800">Page Style</span>
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4 space-y-5">
                    <FieldGroup label="Primary Color">
                      <div className="flex items-center gap-2">
                        <input type="color" value={primaryColor} onChange={e => { setPrimaryColor(e.target.value); setHasChanges(true); }} className="w-10 h-8 rounded-lg border cursor-pointer" />
                        <input value={primaryColor} onChange={e => { setPrimaryColor(e.target.value); setHasChanges(true); }} className="flex-1 text-xs font-mono border rounded-lg px-2 py-1.5" />
                      </div>
                    </FieldGroup>
                    <FieldGroup label="Accent / CTA Color">
                      <div className="flex items-center gap-2">
                        <input type="color" value={accentColor} onChange={e => { setAccentColor(e.target.value); setHasChanges(true); }} className="w-10 h-8 rounded-lg border cursor-pointer" />
                        <input value={accentColor} onChange={e => { setAccentColor(e.target.value); setHasChanges(true); }} className="flex-1 text-xs font-mono border rounded-lg px-2 py-1.5" />
                      </div>
                    </FieldGroup>
                    <FieldGroup label="Font Family">
                      <select value={fontFamily} onChange={e => { setFontFamily(e.target.value); setHasChanges(true); }} className="w-full border rounded-lg px-2 py-1.5 text-sm">
                        {["Inter", "Poppins", "Open Sans", "Roboto", "Lato", "Montserrat", "Playfair Display", "Source Sans Pro"].map(f => (
                          <option key={f} value={f}>{f}</option>
                        ))}
                      </select>
                    </FieldGroup>

                    <div className="border-t pt-4">
                      <h4 className="text-xs font-semibold text-slate-600 mb-3 uppercase tracking-wider">Quick Colors</h4>
                      <div className="grid grid-cols-4 gap-2">
                        {["#6d28d9","#2563eb","#059669","#dc2626","#ea580c","#0891b2","#4f46e5","#be185d"].map(c => (
                          <button
                            key={c}
                            onClick={() => { setPrimaryColor(c); setHasChanges(true); }}
                            className={`w-full aspect-square rounded-xl border-2 transition-all ${primaryColor === c ? "border-slate-800 scale-110" : "border-transparent hover:scale-105"}`}
                            style={{ background: c }}
                          />
                        ))}
                      </div>
                    </div>

                    <div className="border-t pt-4">
                      <p className="text-[11px] text-slate-400">Click any section in the canvas to edit its properties. Drag sections to reorder.</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ═══ GENERATE MODAL ═══ */}
        {showGenerate && (
          <Modal onClose={() => !generating && setShowGenerate(false)}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-2xl bg-violet-100 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-violet-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">AI Generate Landing Page</h3>
                <p className="text-xs text-slate-500">Creates 3 conversion-optimized variants</p>
              </div>
            </div>
            <div className="space-y-3">
              <FieldGroup label="Service / Page Topic *">
                <input value={genService} onChange={(e) => setGenService(e.target.value)} placeholder="e.g. Emergency Lockout, BMW Key Programming..." className="w-full px-3 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-violet-500 focus:outline-none" />
              </FieldGroup>
              <FieldGroup label="Location">
                <input value={genLocation} onChange={(e) => setGenLocation(e.target.value)} placeholder="e.g. Dallas TX, DFW area..." className="w-full px-3 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-violet-500 focus:outline-none" />
              </FieldGroup>
              <FieldGroup label="Image Engine">
                <div className="flex gap-1.5">
                  {([
                    { value: "google" as const, label: "Nano Banana", badge: "Default" },
                    { value: "flux" as const, label: "Flux.1", badge: null },
                    { value: "dalle" as const, label: "DALL-E 3", badge: null },
                    { value: "stability" as const, label: "Stability", badge: null },
                  ] as const).map(eng => (
                    <button key={eng.value} onClick={() => setImageEngine(eng.value)}
                      className={`flex-1 px-2 py-2 rounded-lg text-xs font-medium border transition-all ${imageEngine === eng.value ? "bg-violet-50 border-violet-400 text-violet-700 ring-1 ring-violet-200" : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                      {eng.label}
                      {eng.badge && <span className="ml-1 text-[9px] px-1 py-0.5 rounded bg-violet-100 text-violet-600">{eng.badge}</span>}
                    </button>
                  ))}
                </div>
              </FieldGroup>
            </div>
            <div className="flex gap-2 mt-5">
              <Button variant="outline" className="flex-1 h-11 rounded-xl" onClick={() => setShowGenerate(false)} disabled={generating}>Cancel</Button>
              <Button className="flex-1 h-11 rounded-xl bg-violet-600 hover:bg-violet-700" onClick={handleGenerate} disabled={generating || !genService.trim()}>
                {generating ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Generating...</> : <><Sparkles className="w-4 h-4 mr-2" /> Generate</>}
              </Button>
            </div>
            {generating && <p className="text-[11px] text-slate-500 text-center mt-3">Creating 3 variants with AI... 30-60 seconds</p>}
          </Modal>
        )}

        {/* ═══ TEMPLATES MODAL ═══ */}
        {showTemplates && (
          <Modal onClose={() => setShowTemplates(false)} wide>
            <h3 className="font-bold text-lg text-slate-800 mb-1">Page Templates</h3>
            <p className="text-sm text-slate-500 mb-5">Pick a template to start with — you can customize everything after.</p>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              {TEMPLATES.map(t => (
                <button
                  key={t.name}
                  onClick={() => applyTemplate(t)}
                  className="text-left p-4 rounded-2xl border-2 border-transparent hover:border-violet-300 hover:bg-violet-50/50 transition-all group"
                >
                  <div className="text-2xl mb-2">{t.icon}</div>
                  <h4 className="font-semibold text-sm text-slate-800">{t.name}</h4>
                  <p className="text-[11px] text-slate-500 mt-0.5">{t.description}</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {t.sections.map(s => (
                      <span key={s} className="text-[8px] bg-slate-100 text-slate-500 rounded-full px-1.5 py-0.5">{sectionLabel(s)}</span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </Modal>
        )}

        {/* ═══ CLONE MODAL ═══ */}
        {showClone && activePage && (
          <Modal onClose={() => !cloning && setShowClone(false)}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-2xl bg-blue-100 flex items-center justify-center">
                <Copy className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h3 className="font-bold text-slate-800">Clone & Adapt</h3>
                <p className="text-xs text-slate-500">AI adapts all copy for new service/location</p>
              </div>
            </div>
            <div className="space-y-3">
              <FieldGroup label="New Service"><input value={cloneService} onChange={(e) => setCloneService(e.target.value)} placeholder="e.g. BMW Key Programming" className="w-full px-3 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" /></FieldGroup>
              <FieldGroup label="New Location"><input value={cloneLocation} onChange={(e) => setCloneLocation(e.target.value)} placeholder="e.g. Fort Worth TX" className="w-full px-3 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" /></FieldGroup>
              <FieldGroup label="Custom Instructions (optional)"><textarea value={cloneAdapt} onChange={(e) => setCloneAdapt(e.target.value)} placeholder="Extra AI instructions..." className="w-full px-3 py-2.5 border rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none resize-none" rows={2} /></FieldGroup>
            </div>
            <div className="flex gap-2 mt-5">
              <Button variant="outline" className="flex-1 h-11 rounded-xl" onClick={() => setShowClone(false)} disabled={cloning}>Cancel</Button>
              <Button className="flex-1 h-11 rounded-xl bg-blue-600 hover:bg-blue-700" onClick={handleClone} disabled={cloning}>
                {cloning ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Cloning...</> : <><Copy className="w-4 h-4 mr-2" /> Clone & Adapt</>}
              </Button>
            </div>
          </Modal>
        )}
      </div>
    </AppLayout>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MODAL WRAPPER
// ═══════════════════════════════════════════════════════════════════

function Modal({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className={`bg-white rounded-3xl shadow-2xl p-6 ${wide ? "max-w-2xl" : "max-w-md"} w-full max-h-[85vh] overflow-y-auto`} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// FIELD GROUP
// ═══════════════════════════════════════════════════════════════════

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1.5">{label}</label>
      {children}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SECTION PREVIEW — renders each section in the canvas
// ═══════════════════════════════════════════════════════════════════

function SectionPreview({ section, primaryColor, accentColor }: { section: Section; primaryColor: string; accentColor: string }) {
  const { type, data } = section;

  switch (type) {
    case "hero":
      return (
        <div
          className="relative text-white p-8 md:p-12 text-center rounded-t-xl overflow-hidden"
          style={{ background: data.hero_image_url ? `linear-gradient(rgba(0,0,0,0.55),rgba(0,0,0,0.65)),url(${data.hero_image_url}) center/cover` : `linear-gradient(135deg, ${primaryColor}, ${primaryColor}cc)` }}
        >
          {data.urgency_badge && <div className="inline-block bg-amber-400 text-amber-900 text-xs font-bold px-3 py-1 rounded-full mb-4">{data.urgency_badge}</div>}
          <h1 className="text-2xl md:text-3xl font-bold mb-3 leading-tight drop-shadow-lg">{data.headline || "Your Headline Here"}</h1>
          <p className="text-white/90 text-sm md:text-base mb-6 max-w-xl mx-auto">{data.subheadline || ""}</p>
          {data.cta_text && (
            <button className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-bold text-sm shadow-lg" style={{ background: accentColor }}>
              <Phone className="w-4 h-4" /> {data.cta_text}
            </button>
          )}
          {data.cta_phone && <p className="text-white/60 text-xs mt-3">{data.cta_phone}</p>}
        </div>
      );

    case "trust_bar":
      return (
        <div className="bg-slate-50 border-y px-4 py-3 flex flex-wrap items-center justify-center gap-4">
          {(data.items || []).map((item: string, i: number) => (
            <div key={i} className="flex items-center gap-1.5 text-xs text-slate-600 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> {item}
            </div>
          ))}
        </div>
      );

    case "services":
      return (
        <div className="bg-white px-6 py-8">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{data.heading || "Our Services"}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {(data.services || []).map((svc: any, i: number) => (
              <div key={i} className="flex items-start gap-3 p-4 rounded-xl border bg-slate-50/50 hover:shadow-sm transition-shadow">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: `${primaryColor}12` }}>
                  <SectionIcon name={svc.icon} color={primaryColor} />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-800 text-sm">{svc.name}</h3>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{svc.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      );

    case "why_us":
      return (
        <div className="bg-slate-50 px-6 py-8 border-y">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{data.heading || "Why Choose Us"}</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {(data.reasons || []).map((r: any, i: number) => (
              <div key={i} className="text-center p-4">
                <div className="w-11 h-11 rounded-2xl flex items-center justify-center mx-auto mb-3" style={{ background: `${primaryColor}12` }}>
                  <SectionIcon name={r.icon} color={primaryColor} />
                </div>
                <h3 className="font-semibold text-slate-800 text-sm mb-1">{r.title}</h3>
                <p className="text-xs text-slate-500 leading-relaxed">{r.description}</p>
              </div>
            ))}
          </div>
        </div>
      );

    case "reviews":
      return (
        <div className="bg-white px-6 py-8">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{data.heading || "Reviews"}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(data.reviews || []).map((r: any, i: number) => (
              <div key={i} className="p-4 rounded-xl border hover:shadow-sm transition-shadow">
                <div className="flex items-center gap-0.5 mb-2">
                  {Array.from({ length: r.rating || 5 }).map((_, si) => <Star key={si} className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />)}
                </div>
                <p className="text-xs text-slate-600 italic leading-relaxed mb-2">&ldquo;{r.text}&rdquo;</p>
                <p className="text-[11px] text-slate-400 font-medium">— {r.name}</p>
              </div>
            ))}
          </div>
        </div>
      );

    case "faq":
      return (
        <div className="bg-slate-50 px-6 py-8 border-t">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{data.heading || "FAQ"}</h2>
          <div className="space-y-2 max-w-xl mx-auto">
            {(data.faqs || []).map((f: any, i: number) => (
              <div key={i} className="bg-white rounded-xl border p-4">
                <h3 className="font-semibold text-slate-800 text-sm mb-1">{f.question}</h3>
                <p className="text-xs text-slate-500 leading-relaxed">{f.answer}</p>
              </div>
            ))}
          </div>
        </div>
      );

    case "contact_form":
      return (
        <div className="bg-slate-50 px-6 py-8 border-y">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-2">{data.heading || "Get Your Free Quote"}</h2>
          {data.subheading && <p className="text-sm text-slate-500 text-center mb-6">{data.subheading}</p>}
          {data.embed_slug || data.embed_url ? (
            <div className="max-w-lg mx-auto bg-white rounded-2xl shadow-sm border p-4">
              <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-xl px-3 py-2">
                <CheckCircle2 className="w-4 h-4" /> BotForms contact form connected
              </div>
            </div>
          ) : (
            <div className="max-w-lg mx-auto bg-white rounded-2xl shadow-sm border p-6 space-y-3">
              <div><div className="text-xs font-medium text-slate-600 mb-1">Full Name *</div><div className="h-10 bg-slate-100 rounded-xl" /></div>
              <div><div className="text-xs font-medium text-slate-600 mb-1">Phone *</div><div className="h-10 bg-slate-100 rounded-xl" /></div>
              <div><div className="text-xs font-medium text-slate-600 mb-1">Email</div><div className="h-10 bg-slate-100 rounded-xl" /></div>
              <div><div className="text-xs font-medium text-slate-600 mb-1">Message</div><div className="h-20 bg-slate-100 rounded-xl" /></div>
              <button className="w-full py-3 rounded-xl text-white text-sm font-bold" style={{ background: accentColor }}>Get My Free Quote</button>
            </div>
          )}
        </div>
      );

    case "cta_banner":
      return (
        <div className="text-white p-8 text-center rounded-b-xl" style={{ background: `linear-gradient(135deg, ${primaryColor}, ${primaryColor}cc)` }}>
          <h2 className="text-xl font-bold mb-2">{data.heading || "Ready to Get Started?"}</h2>
          {data.subtext && <p className="text-white/80 text-sm mb-4">{data.subtext}</p>}
          {data.cta_text && (
            <button className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-bold text-sm shadow-lg" style={{ background: accentColor }}>
              <Phone className="w-4 h-4" /> {data.cta_text}
            </button>
          )}
        </div>
      );

    case "stats":
      return (
        <div className="bg-white px-6 py-8 border-y">
          {data.heading && <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{data.heading}</h2>}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(data.stats || []).map((s: any, i: number) => (
              <div key={i} className="text-center p-4">
                <div className="text-3xl font-bold mb-1" style={{ color: primaryColor }}>{s.number}</div>
                <div className="text-xs text-slate-500 font-medium">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      );

    case "text_block":
      return (
        <div className="bg-white px-6 py-8">
          {data.heading && <h2 className="text-lg font-bold text-slate-900 mb-4">{data.heading}</h2>}
          <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{data.content}</p>
        </div>
      );

    case "gallery":
      return (
        <div className="bg-slate-50 px-6 py-8 border-y">
          <h2 className="text-lg font-bold text-slate-900 text-center mb-6">{data.heading || "Our Work"}</h2>
          <div className="grid grid-cols-3 gap-2">
            {(data.images || []).length > 0 ? data.images.map((img: string, i: number) => (
              <div key={i} className="aspect-square rounded-xl bg-slate-200 overflow-hidden">
                <img src={img} alt="" className="w-full h-full object-cover" />
              </div>
            )) : (
              [0,1,2].map(i => <div key={i} className="aspect-square rounded-xl bg-slate-200 flex items-center justify-center"><ImageIcon className="w-6 h-6 text-slate-300" /></div>)
            )}
          </div>
        </div>
      );

    case "video":
      return (
        <div className="bg-white px-6 py-8">
          {data.heading && <h2 className="text-lg font-bold text-slate-900 text-center mb-4">{data.heading}</h2>}
          <div className="aspect-video bg-slate-900 rounded-xl flex items-center justify-center">
            {data.video_url ? (
              <iframe src={data.video_url} className="w-full h-full rounded-xl" allowFullScreen />
            ) : (
              <div className="text-center">
                <Play className="w-12 h-12 text-white/30 mx-auto mb-2" />
                <p className="text-xs text-white/50">Add a video URL</p>
              </div>
            )}
          </div>
          {data.caption && <p className="text-xs text-slate-500 text-center mt-3">{data.caption}</p>}
        </div>
      );

    default:
      return <div className="bg-white p-6 text-center text-sm text-slate-400">Unknown section: {type}</div>;
  }
}

// ═══════════════════════════════════════════════════════════════════
// PROPERTIES PANEL — edit selected section
// ═══════════════════════════════════════════════════════════════════

function PropertiesPanel({
  section, onUpdate, primaryColor, accentColor, onPrimaryChange, onAccentChange,
}: {
  section: Section; onUpdate: (data: any) => void;
  primaryColor: string; accentColor: string;
  onPrimaryChange: (c: string) => void; onAccentChange: (c: string) => void;
}) {
  const { type, data } = section;

  function set(key: string, value: any) { onUpdate({ ...data, [key]: value }); }
  function setArray(key: string, idx: number, field: string, value: any) {
    const arr = [...(data[key] || [])];
    arr[idx] = { ...arr[idx], [field]: value };
    onUpdate({ ...data, [key]: arr });
  }
  function addArrayItem(key: string, item: any) {
    onUpdate({ ...data, [key]: [...(data[key] || []), item] });
  }
  function removeArrayItem(key: string, idx: number) {
    const arr = [...(data[key] || [])];
    arr.splice(idx, 1);
    onUpdate({ ...data, [key]: arr });
  }

  const inputCls = "w-full px-3 py-2 border rounded-xl text-sm focus:ring-2 focus:ring-violet-500 focus:outline-none";
  const textareaCls = `${inputCls} resize-none`;

  switch (type) {
    case "hero":
      return (
        <div className="space-y-4">
          <FieldGroup label="Headline"><input value={data.headline || ""} onChange={e => set("headline", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Subheadline"><textarea value={data.subheadline || ""} onChange={e => set("subheadline", e.target.value)} rows={2} className={textareaCls} /></FieldGroup>
          <FieldGroup label="CTA Button Text"><input value={data.cta_text || ""} onChange={e => set("cta_text", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Phone Number"><input value={data.cta_phone || ""} onChange={e => set("cta_phone", e.target.value)} placeholder="(555) 123-4567" className={inputCls} /></FieldGroup>
          <FieldGroup label="Urgency Badge"><input value={data.urgency_badge || ""} onChange={e => set("urgency_badge", e.target.value)} placeholder="e.g. 24/7 Emergency" className={inputCls} /></FieldGroup>
          <FieldGroup label="Hero Image URL"><input value={data.hero_image_url || ""} onChange={e => set("hero_image_url", e.target.value)} placeholder="https://..." className={inputCls} /></FieldGroup>
          <div className="grid grid-cols-2 gap-2">
            <FieldGroup label="Primary Color"><input type="color" value={primaryColor} onChange={e => onPrimaryChange(e.target.value)} className="w-full h-9 rounded-xl border cursor-pointer" /></FieldGroup>
            <FieldGroup label="CTA Color"><input type="color" value={accentColor} onChange={e => onAccentChange(e.target.value)} className="w-full h-9 rounded-xl border cursor-pointer" /></FieldGroup>
          </div>
        </div>
      );

    case "trust_bar":
      return (
        <div className="space-y-3">
          <FieldGroup label="Trust Items">
            {(data.items || []).map((item: string, i: number) => (
              <div key={i} className="flex items-center gap-1.5 mb-1.5">
                <input value={item} onChange={e => { const arr = [...data.items]; arr[i] = e.target.value; set("items", arr); }} className={`flex-1 ${inputCls} !py-1.5 text-xs`} />
                <button onClick={() => { const arr = [...data.items]; arr.splice(i, 1); set("items", arr); }} className="p-1 rounded-lg hover:bg-red-50 text-red-400"><Trash2 className="w-3 h-3" /></button>
              </div>
            ))}
          </FieldGroup>
          <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => set("items", [...(data.items || []), "New Item"])}>
            <Plus className="w-3 h-3 mr-1" /> Add Item
          </Button>
        </div>
      );

    case "services":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          <div className="space-y-3">
            {(data.services || []).map((svc: any, i: number) => (
              <div key={i} className="p-3 bg-slate-50 rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-400 uppercase">Service {i + 1}</span>
                  <button onClick={() => removeArrayItem("services", i)} className="p-0.5 rounded hover:bg-red-50 text-red-400"><Trash2 className="w-3 h-3" /></button>
                </div>
                <input value={svc.name || ""} onChange={e => setArray("services", i, "name", e.target.value)} placeholder="Service name" className={`${inputCls} !py-1.5 text-xs`} />
                <textarea value={svc.description || ""} onChange={e => setArray("services", i, "description", e.target.value)} placeholder="Description" rows={2} className={`${textareaCls} !py-1.5 text-xs`} />
              </div>
            ))}
          </div>
          <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => addArrayItem("services", { name: "New Service", description: "Description here", icon: "star" })}>
            <Plus className="w-3 h-3 mr-1" /> Add Service
          </Button>
        </div>
      );

    case "why_us":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          {(data.reasons || []).map((r: any, i: number) => (
            <div key={i} className="p-3 bg-slate-50 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-400 uppercase">Reason {i + 1}</span>
                <button onClick={() => removeArrayItem("reasons", i)} className="p-0.5 rounded hover:bg-red-50 text-red-400"><Trash2 className="w-3 h-3" /></button>
              </div>
              <input value={r.title || ""} onChange={e => setArray("reasons", i, "title", e.target.value)} placeholder="Title" className={`${inputCls} !py-1.5 text-xs`} />
              <textarea value={r.description || ""} onChange={e => setArray("reasons", i, "description", e.target.value)} placeholder="Description" rows={2} className={`${textareaCls} !py-1.5 text-xs`} />
            </div>
          ))}
          <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => addArrayItem("reasons", { title: "New Reason", description: "Why choose us", icon: "star" })}>
            <Plus className="w-3 h-3 mr-1" /> Add Reason
          </Button>
        </div>
      );

    case "reviews":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          {(data.reviews || []).map((r: any, i: number) => (
            <div key={i} className="p-3 bg-slate-50 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-400 uppercase">Review {i + 1}</span>
                <button onClick={() => removeArrayItem("reviews", i)} className="p-0.5 rounded hover:bg-red-50 text-red-400"><Trash2 className="w-3 h-3" /></button>
              </div>
              <input value={r.name || ""} onChange={e => setArray("reviews", i, "name", e.target.value)} placeholder="Reviewer name" className={`${inputCls} !py-1.5 text-xs`} />
              <textarea value={r.text || ""} onChange={e => setArray("reviews", i, "text", e.target.value)} placeholder="Review text" rows={2} className={`${textareaCls} !py-1.5 text-xs`} />
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-500">Rating:</span>
                {[1,2,3,4,5].map(n => (
                  <button key={n} onClick={() => setArray("reviews", i, "rating", n)}>
                    <Star className={`w-4 h-4 ${n <= (r.rating || 5) ? "text-amber-400 fill-amber-400" : "text-slate-200"}`} />
                  </button>
                ))}
              </div>
            </div>
          ))}
          <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => addArrayItem("reviews", { name: "Customer", text: "Great service!", rating: 5 })}>
            <Plus className="w-3 h-3 mr-1" /> Add Review
          </Button>
        </div>
      );

    case "faq":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          {(data.faqs || []).map((f: any, i: number) => (
            <div key={i} className="p-3 bg-slate-50 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-400 uppercase">Q&A {i + 1}</span>
                <button onClick={() => removeArrayItem("faqs", i)} className="p-0.5 rounded hover:bg-red-50 text-red-400"><Trash2 className="w-3 h-3" /></button>
              </div>
              <input value={f.question || ""} onChange={e => setArray("faqs", i, "question", e.target.value)} placeholder="Question" className={`${inputCls} !py-1.5 text-xs`} />
              <textarea value={f.answer || ""} onChange={e => setArray("faqs", i, "answer", e.target.value)} placeholder="Answer" rows={2} className={`${textareaCls} !py-1.5 text-xs`} />
            </div>
          ))}
          <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => addArrayItem("faqs", { question: "New question?", answer: "Answer here." })}>
            <Plus className="w-3 h-3 mr-1" /> Add FAQ
          </Button>
        </div>
      );

    case "contact_form":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Subheading"><input value={data.subheading || ""} onChange={e => set("subheading", e.target.value)} className={inputCls} /></FieldGroup>
          <div className="p-3 bg-violet-50 rounded-xl">
            <div className="flex items-center gap-2 mb-2">
              <Mail className="w-4 h-4 text-violet-600" />
              <span className="text-xs font-semibold text-violet-800">BotForms Integration</span>
            </div>
            <p className="text-[11px] text-violet-600 mb-2">Forms are auto-created when the landing page is generated. Submissions are emailed to you and tracked as leads.</p>
            {data.embed_slug && (
              <div className="flex items-center gap-2 text-[11px] text-emerald-700 bg-emerald-50 rounded-lg px-2 py-1.5">
                <CheckCircle2 className="w-3 h-3" /> Form connected: {data.embed_slug}
              </div>
            )}
          </div>
        </div>
      );

    case "cta_banner":
      return (
        <div className="space-y-4">
          <FieldGroup label="Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Subtext"><input value={data.subtext || ""} onChange={e => set("subtext", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="CTA Button Text"><input value={data.cta_text || ""} onChange={e => set("cta_text", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Phone Number"><input value={data.cta_phone || ""} onChange={e => set("cta_phone", e.target.value)} className={inputCls} /></FieldGroup>
        </div>
      );

    case "stats":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} placeholder="Optional heading" className={inputCls} /></FieldGroup>
          {(data.stats || []).map((s: any, i: number) => (
            <div key={i} className="flex items-center gap-2">
              <input value={s.number || ""} onChange={e => setArray("stats", i, "number", e.target.value)} placeholder="500+" className={`w-20 ${inputCls} !py-1.5 text-xs`} />
              <input value={s.label || ""} onChange={e => setArray("stats", i, "label", e.target.value)} placeholder="Label" className={`flex-1 ${inputCls} !py-1.5 text-xs`} />
              <button onClick={() => removeArrayItem("stats", i)} className="p-1 rounded hover:bg-red-50 text-red-400"><Trash2 className="w-3 h-3" /></button>
            </div>
          ))}
          <Button size="sm" variant="outline" className="w-full text-xs" onClick={() => addArrayItem("stats", { number: "100+", label: "New Stat" })}>
            <Plus className="w-3 h-3 mr-1" /> Add Stat
          </Button>
        </div>
      );

    case "text_block":
      return (
        <div className="space-y-4">
          <FieldGroup label="Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Content"><textarea value={data.content || ""} onChange={e => set("content", e.target.value)} rows={6} className={textareaCls} /></FieldGroup>
        </div>
      );

    case "video":
      return (
        <div className="space-y-4">
          <FieldGroup label="Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Video URL (YouTube/Vimeo embed)"><input value={data.video_url || ""} onChange={e => set("video_url", e.target.value)} placeholder="https://youtube.com/embed/..." className={inputCls} /></FieldGroup>
          <FieldGroup label="Caption"><input value={data.caption || ""} onChange={e => set("caption", e.target.value)} className={inputCls} /></FieldGroup>
        </div>
      );

    case "gallery":
      return (
        <div className="space-y-4">
          <FieldGroup label="Section Heading"><input value={data.heading || ""} onChange={e => set("heading", e.target.value)} className={inputCls} /></FieldGroup>
          <FieldGroup label="Image URLs (one per line)">
            <textarea
              value={(data.images || []).join("\n")}
              onChange={e => set("images", e.target.value.split("\n").filter(Boolean))}
              rows={4}
              placeholder="https://image1.jpg&#10;https://image2.jpg"
              className={textareaCls}
            />
          </FieldGroup>
        </div>
      );

    default:
      return <p className="text-xs text-slate-400">No properties for this section type.</p>;
  }
}

// ═══════════════════════════════════════════════════════════════════
// SECTION ICON (shared with preview)
// ═══════════════════════════════════════════════════════════════════

function SectionIcon({ name, color }: { name: string; color: string }) {
  const cls = "w-4 h-4";
  const s = { color };
  switch (name) {
    case "key": return <Zap className={cls} style={s} />;
    case "shield": return <Shield className={cls} style={s} />;
    case "clock": return <Clock className={cls} style={s} />;
    case "star": return <Star className={cls} style={s} />;
    case "wrench": return <Wand2 className={cls} style={s} />;
    case "phone": return <Phone className={cls} style={s} />;
    case "map": return <MapPin className={cls} style={s} />;
    case "users": return <Users className={cls} style={s} />;
    case "award": return <Award className={cls} style={s} />;
    default: return <CheckCircle2 className={cls} style={s} />;
  }
}
