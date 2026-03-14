"use client";

import { useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Loader2, Zap, Rocket, ArrowRight, CheckCircle,
  Sparkles, TrendingUp, Target, Star,
} from "lucide-react";

interface Suggestion {
  service_name: string;
  category: string;
  why_good_fit: string;
  search_volume: string;
  entry_difficulty: string;
  estimated_monthly_searches: number;
  campaign_prompt: string;
  suggested_keywords: string[];
  priority: number;
}

interface ExpansionResult {
  status: string;
  current_services: string[];
  industry: string;
  suggestions: Suggestion[];
  estimated_total_campaigns: number;
  rationale: string;
  ai_generated: boolean;
}

export default function ExpandServicesPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExpansionResult | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [generated, setGenerated] = useState<Set<string>>(new Set());

  async function loadSuggestions() {
    setLoading(true);
    try {
      const res = await api.get("/api/v2/growth/service-expansion/suggestions");
      setResult(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function generateCampaign(suggestion: Suggestion) {
    setGenerating(suggestion.service_name);
    try {
      await api.post("/api/v2/growth/service-expansion/generate", {
        campaign_prompt: suggestion.campaign_prompt,
        service_name: suggestion.service_name,
      });
      setGenerated((prev) => new Set(prev).add(suggestion.service_name));
    } catch (e) {
      console.error(e);
    } finally {
      setGenerating(null);
    }
  }

  const difficultyColor = (d: string) => {
    if (d === "easy") return "bg-green-100 text-green-800";
    if (d === "moderate") return "bg-amber-100 text-amber-800";
    return "bg-red-100 text-red-800";
  };

  const volumeColor = (v: string) => {
    if (v === "high") return "bg-blue-100 text-blue-800";
    if (v === "medium") return "bg-slate-100 text-slate-800";
    return "bg-slate-50 text-slate-600";
  };

  return (
    <AppLayout>
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Zap className="w-6 h-6 text-purple-500" />
              Auto-Expand Services
            </h1>
            <p className="text-slate-500 mt-1">
              AI identifies adjacent niches you can expand into — instantly 8x your campaign volume
            </p>
          </div>
          <Button
            onClick={loadSuggestions}
            disabled={loading}
            className="bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 text-white px-6"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Analyzing...</>
            ) : (
              <><Sparkles className="w-4 h-4 mr-2" /> Find Expansions</>
            )}
          </Button>
        </div>

        {/* Current services */}
        {result && result.current_services?.length > 0 && (
          <Card className="border-slate-200">
            <CardContent className="pt-4">
              <p className="text-sm font-medium text-slate-500 mb-2">Your Current Services</p>
              <div className="flex flex-wrap gap-2">
                {result.current_services.map((s, i) => (
                  <Badge key={i} className="bg-slate-100 text-slate-700 px-3 py-1">
                    {s}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* AI Rationale */}
        {result?.rationale && (
          <Card className="border-purple-200 bg-purple-50/50">
            <CardContent className="pt-4">
              <p className="text-sm font-medium text-purple-900 mb-1 flex items-center gap-1">
                <Sparkles className="w-4 h-4" /> AI Expansion Strategy
              </p>
              <p className="text-slate-700">{result.rationale}</p>
              {result.estimated_total_campaigns > 0 && (
                <p className="text-sm text-purple-700 mt-2 font-medium">
                  Potential: {result.estimated_total_campaigns} new campaigns from these expansions
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Suggestions */}
        {(result?.suggestions?.length ?? 0) > 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-800">
              Expansion Opportunities ({result.suggestions.length})
            </h2>
            {result.suggestions.map((s, i) => (
              <Card
                key={i}
                className={`transition hover:shadow-md ${
                  generated.has(s.service_name) ? "border-green-200 bg-green-50/30" : ""
                }`}
              >
                <CardContent className="pt-5 pb-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-lg font-bold text-slate-900">
                          {s.service_name}
                        </h3>
                        <Badge className={volumeColor(s.search_volume)}>
                          {s.search_volume} volume
                        </Badge>
                        <Badge className={difficultyColor(s.entry_difficulty)}>
                          {s.entry_difficulty} entry
                        </Badge>
                        {s.estimated_monthly_searches > 0 && (
                          <span className="text-xs text-slate-400">
                            ~{s.estimated_monthly_searches.toLocaleString()} searches/mo
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-600 mt-2">{s.why_good_fit}</p>
                      {(s.suggested_keywords?.length ?? 0) > 0 && (
                        <div className="flex flex-wrap gap-1 mt-3">
                          {s.suggested_keywords.slice(0, 6).map((kw, j) => (
                            <span
                              key={j}
                              className="text-xs px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded"
                            >
                              {kw}
                            </span>
                          ))}
                          {s.suggested_keywords.length > 6 && (
                            <span className="text-xs text-slate-400">
                              +{s.suggested_keywords.length - 6} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <span className="text-xs font-medium text-slate-400">
                        Priority #{s.priority || i + 1}
                      </span>
                      {generated.has(s.service_name) ? (
                        <Button size="sm" disabled className="bg-green-600 text-white">
                          <CheckCircle className="w-4 h-4 mr-1" /> Generated
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => generateCampaign(s)}
                          disabled={generating !== null}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white"
                        >
                          {generating === s.service_name ? (
                            <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Creating...</>
                          ) : (
                            <><Rocket className="w-4 h-4 mr-1" /> Generate Campaign</>
                          )}
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!result && !loading && (
          <Card className="border-dashed border-2 border-slate-200">
            <CardContent className="py-16 text-center">
              <Zap className="w-14 h-14 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-600">
                Discover Your Growth Potential
              </h3>
              <p className="text-slate-400 mt-2 max-w-md mx-auto">
                AI will analyze your current services and suggest adjacent niches you can
                expand into. One click generates a full campaign for each.
              </p>
              <Button
                onClick={loadSuggestions}
                className="mt-6 bg-gradient-to-r from-purple-500 to-indigo-500 text-white px-8"
              >
                <Sparkles className="w-4 h-4 mr-2" /> Analyze My Business
              </Button>
            </CardContent>
          </Card>
        )}

        {result?.status === "no_suggestions" && (
          <Card className="border-dashed border-2 border-slate-200">
            <CardContent className="py-12 text-center">
              <Target className="w-12 h-12 text-slate-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-600">No suggestions available</h3>
              <p className="text-slate-400 mt-1">{result.message}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
