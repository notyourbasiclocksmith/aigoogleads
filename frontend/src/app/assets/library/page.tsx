"use client";

import { useState, useEffect, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
  Image, Search, Download, ExternalLink, Loader2, Calendar,
  Grid3X3, List, Filter, ChevronLeft, ChevronRight, Trash2,
  Sparkles, Layers, Eye, X, Copy, Check,
} from "lucide-react";

interface AssetItem {
  id: string;
  type: string;
  source: string;
  url: string;
  content: string | null;
  metadata: Record<string, any>;
  created_at: string | null;
}

export default function AssetLibraryPage() {
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [selectedAsset, setSelectedAsset] = useState<AssetItem | null>(null);
  const [copied, setCopied] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        asset_type: "IMAGE",
        page: page.toString(),
        limit: "24",
      });
      if (search) params.set("search", search);
      if (sourceFilter) params.set("source", sourceFilter);

      const data = await api.get(`/api/creative/assets?${params}`);
      // Support both old array format and new paginated format
      if (Array.isArray(data)) {
        setAssets(data);
        setTotal(data.length);
        setTotalPages(1);
      } else {
        setAssets(data.items || []);
        setTotal(data.total || 0);
        setTotalPages(data.pages || 1);
      }
    } catch (err) {
      console.error("Failed to fetch assets:", err);
    } finally {
      setLoading(false);
    }
  }, [page, search, sourceFilter]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const handleSearch = () => {
    setPage(1);
    setSearch(searchInput);
  };

  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this image? This cannot be undone.")) return;
    setDeleting(id);
    try {
      await api.delete(`/api/creative/assets/${id}`);
      setAssets((prev) => prev.filter((a) => a.id !== id));
      setTotal((t) => t - 1);
      if (selectedAsset?.id === id) setSelectedAsset(null);
    } catch (err) {
      console.error("Failed to delete:", err);
    } finally {
      setDeleting(null);
    }
  };

  const formatDate = (d: string | null) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString("en-US", {
      month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
    });
  };

  const engineLabel = (meta: Record<string, any>) => {
    const e = meta?.engine || meta?.source || "unknown";
    const map: Record<string, string> = {
      google: "Google Imagen", dalle: "DALL-E 3", stability: "Stability AI",
      flux: "Flux.1", seopix: "SEOpix",
    };
    return map[e] || e;
  };

  const sourceColors: Record<string, string> = {
    ai_image_generator: "bg-violet-500/20 text-violet-300 border-violet-500/30",
    seopix: "bg-blue-500/20 text-blue-300 border-blue-500/30",
    manual: "bg-slate-500/20 text-slate-300 border-slate-500/30",
    google_ads: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  };

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Image className="w-6 h-6 text-violet-400" />
              Asset Library
            </h1>
            <p className="text-sm text-white/50 mt-1">
              {total} image{total !== 1 ? "s" : ""} generated across all campaigns
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost" size="sm"
              className={viewMode === "grid" ? "text-violet-400" : "text-white/40"}
              onClick={() => setViewMode("grid")}
            >
              <Grid3X3 className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost" size="sm"
              className={viewMode === "list" ? "text-violet-400" : "text-white/40"}
              onClick={() => setViewMode("list")}
            >
              <List className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
            <Input
              placeholder="Search by prompt or content..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="pl-10 bg-white/5 border-white/10 text-white placeholder:text-white/30"
            />
          </div>
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-white/30" />
            {["", "ai_image_generator", "seopix", "manual"].map((src) => (
              <Button
                key={src || "all"}
                variant="ghost" size="sm"
                className={`text-xs ${sourceFilter === src ? "bg-violet-500/20 text-violet-300" : "text-white/40"}`}
                onClick={() => { setSourceFilter(src); setPage(1); }}
              >
                {src === "" ? "All" : src === "ai_image_generator" ? "AI Generated" : src === "seopix" ? "SEOpix" : "Manual"}
              </Button>
            ))}
          </div>
        </div>

        {/* Loading */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          </div>
        ) : assets.length === 0 ? (
          <div className="text-center py-20">
            <Image className="w-12 h-12 text-white/10 mx-auto mb-4" />
            <p className="text-white/40 text-sm">No images found</p>
            <p className="text-white/20 text-xs mt-1">Generate images through IntelliDrive Operator or Creative Studio</p>
          </div>
        ) : viewMode === "grid" ? (
          /* Grid View */
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {assets.map((asset) => (
              <div
                key={asset.id}
                className="group relative rounded-xl overflow-hidden border border-white/10 bg-white/[0.02] cursor-pointer hover:border-violet-500/30 transition-all"
                onClick={() => setSelectedAsset(asset)}
              >
                <div className="aspect-square relative">
                  <img
                    src={asset.url}
                    alt={asset.metadata?.prompt || "Generated image"}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="absolute bottom-0 left-0 right-0 p-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <p className="text-[9px] text-white/80 line-clamp-2">{asset.metadata?.prompt || "—"}</p>
                  </div>
                  <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleCopyUrl(asset.url); }}
                      className="w-6 h-6 bg-black/60 rounded-md flex items-center justify-center hover:bg-black/80"
                    >
                      <Copy className="w-3 h-3 text-white/70" />
                    </button>
                    <a
                      href={asset.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="w-6 h-6 bg-black/60 rounded-md flex items-center justify-center hover:bg-black/80"
                    >
                      <ExternalLink className="w-3 h-3 text-white/70" />
                    </a>
                  </div>
                </div>
                <div className="p-2">
                  <Badge variant="outline" className={`text-[9px] ${sourceColors[asset.source] || sourceColors.manual}`}>
                    {engineLabel(asset.metadata)}
                  </Badge>
                  <p className="text-[10px] text-white/30 mt-1">{formatDate(asset.created_at)}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* List View */
          <div className="space-y-2">
            {assets.map((asset) => (
              <div
                key={asset.id}
                className="flex items-center gap-4 p-3 rounded-xl border border-white/10 bg-white/[0.02] hover:border-violet-500/30 cursor-pointer transition-all"
                onClick={() => setSelectedAsset(asset)}
              >
                <img
                  src={asset.url}
                  alt={asset.metadata?.prompt || "Generated image"}
                  className="w-16 h-16 rounded-lg object-cover flex-shrink-0"
                  loading="lazy"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white/70 truncate">{asset.metadata?.prompt || "No prompt"}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="outline" className={`text-[9px] ${sourceColors[asset.source] || sourceColors.manual}`}>
                      {engineLabel(asset.metadata)}
                    </Badge>
                    {asset.metadata?.size && (
                      <span className="text-[10px] text-white/30">{asset.metadata.size}</span>
                    )}
                    {asset.metadata?.campaign_id && (
                      <Badge variant="outline" className="text-[9px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                        Campaign linked
                      </Badge>
                    )}
                  </div>
                </div>
                <span className="text-xs text-white/30 flex-shrink-0">{formatDate(asset.created_at)}</span>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <a href={asset.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>
                    <ExternalLink className="w-4 h-4 text-white/30 hover:text-white/60" />
                  </a>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(asset.id); }}>
                    {deleting === asset.id ? (
                      <Loader2 className="w-4 h-4 animate-spin text-red-400" />
                    ) : (
                      <Trash2 className="w-4 h-4 text-white/20 hover:text-red-400" />
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3">
            <Button
              variant="ghost" size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="text-white/40"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-xs text-white/40">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="ghost" size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="text-white/40"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}

        {/* Lightbox / Detail Modal */}
        {selectedAsset && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedAsset(null)}
          >
            <div
              className="relative max-w-3xl w-full mx-4 bg-[#0f1117] border border-white/10 rounded-2xl overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setSelectedAsset(null)}
                className="absolute top-3 right-3 z-10 w-8 h-8 bg-black/60 rounded-lg flex items-center justify-center hover:bg-black/80"
              >
                <X className="w-4 h-4 text-white/70" />
              </button>

              <img
                src={selectedAsset.url}
                alt={selectedAsset.metadata?.prompt || "Generated image"}
                className="w-full max-h-[60vh] object-contain bg-black/40"
              />

              <div className="p-5 space-y-3">
                {selectedAsset.metadata?.prompt && (
                  <div>
                    <p className="text-[10px] text-white/30 uppercase tracking-wider mb-1">Prompt</p>
                    <p className="text-sm text-white/70">{selectedAsset.metadata.prompt}</p>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className={sourceColors[selectedAsset.source] || sourceColors.manual}>
                    {engineLabel(selectedAsset.metadata)}
                  </Badge>
                  {selectedAsset.metadata?.size && (
                    <Badge variant="outline" className="text-xs bg-white/5 text-white/50 border-white/10">
                      {selectedAsset.metadata.size}
                    </Badge>
                  )}
                  {selectedAsset.metadata?.style && (
                    <Badge variant="outline" className="text-xs bg-white/5 text-white/50 border-white/10">
                      {selectedAsset.metadata.style}
                    </Badge>
                  )}
                  {selectedAsset.metadata?.campaign_id && (
                    <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                      Campaign: {selectedAsset.metadata.campaign_id}
                    </Badge>
                  )}
                </div>

                <div className="flex items-center gap-2 text-xs text-white/30">
                  <Calendar className="w-3 h-3" />
                  {formatDate(selectedAsset.created_at)}
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <a
                    href={selectedAsset.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1"
                  >
                    <Button variant="outline" size="sm" className="w-full text-xs">
                      <ExternalLink className="w-3 h-3 mr-1.5" /> Open Full Size
                    </Button>
                  </a>
                  <Button
                    variant="outline" size="sm"
                    className="text-xs"
                    onClick={() => handleCopyUrl(selectedAsset.url)}
                  >
                    {copied ? <Check className="w-3 h-3 mr-1.5 text-emerald-400" /> : <Copy className="w-3 h-3 mr-1.5" />}
                    {copied ? "Copied!" : "Copy URL"}
                  </Button>
                  <Button
                    variant="outline" size="sm"
                    className="text-xs text-red-400 hover:text-red-300"
                    onClick={() => handleDelete(selectedAsset.id)}
                  >
                    {deleting === selectedAsset.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <><Trash2 className="w-3 h-3 mr-1.5" /> Delete</>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
