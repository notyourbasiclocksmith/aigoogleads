"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import {
  Loader2, Rocket, Plus, X, Sparkles, CheckCircle,
  AlertCircle, Megaphone, Trash2,
} from "lucide-react";

interface BulkStatus {
  status: string;
  current?: number;
  total?: number;
  current_service?: string;
  completed?: number;
  errors?: number;
  progress_pct?: number;
  error?: string;
}

const EXAMPLE_VARIANTS: Record<string, string[]> = {
  "Automotive Locksmith": [
    "Jaguar Key Programming", "BMW Key Programming", "Mercedes Key Programming",
    "Audi Key Programming", "Land Rover Key Programming", "Porsche Key Programming",
    "Lexus Key Programming", "Tesla Key Programming", "Volvo Key Programming",
    "Range Rover Key Programming",
  ],
  "HVAC": [
    "AC Repair", "Furnace Repair", "Heat Pump Installation", "Duct Cleaning",
    "Thermostat Installation", "Indoor Air Quality", "Emergency HVAC",
    "Commercial HVAC", "Mini Split Installation", "HVAC Maintenance",
  ],
  "Plumbing": [
    "Emergency Plumber", "Drain Cleaning", "Water Heater Repair", "Sewer Line Repair",
    "Leak Detection", "Bathroom Remodel", "Kitchen Plumbing", "Pipe Repair",
    "Water Filtration", "Gas Line Repair",
  ],
};

export default function BulkGeneratePage() {
  const [basePrompt, setBasePrompt] = useState(
    "Create a Google Ads campaign for {service}. Target local customers searching for this service. Include emergency keywords, competitor displacement copy, and pain-trigger headlines."
  );
  const [variants, setVariants] = useState<string[]>([""]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<BulkStatus | null>(null);
  const [launching, setLaunching] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollStatus = useCallback(async (tid: string) => {
    try {
      const s = await api.get(`/api/v2/growth/bulk-generate/${tid}/status`);
      setStatus(s);
      if (s.status === "complete" || s.status === "failed") {
        if (pollingRef.current) clearInterval(pollingRef.current);
      }
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  function addVariant() {
    setVariants([...variants, ""]);
  }

  function removeVariant(i: number) {
    setVariants(variants.filter((_, idx) => idx !== i));
  }

  function updateVariant(i: number, val: string) {
    const updated = [...variants];
    updated[i] = val;
    setVariants(updated);
  }

  function loadTemplate(key: string) {
    setVariants(EXAMPLE_VARIANTS[key] || []);
  }

  async function launch() {
    const cleaned = variants.filter((v) => v.trim());
    if (!cleaned.length || !basePrompt.trim()) return;

    setLaunching(true);
    setStatus(null);
    try {
      const res = await api.post("/api/v2/growth/bulk-generate", {
        base_prompt: basePrompt,
        service_variants: cleaned,
      });
      setTaskId(res.task_id);
      setStatus({ status: "queued", total: cleaned.length, progress_pct: 0 });
      pollingRef.current = setInterval(() => pollStatus(res.task_id), 3000);
    } catch (e) {
      console.error(e);
    } finally {
      setLaunching(false);
    }
  }

  const cleanCount = variants.filter((v) => v.trim()).length;
  const isRunning = status && !["complete", "failed"].includes(status.status) && status.status !== undefined;

  return (
    <AppLayout>
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Megaphone className="w-6 h-6 text-orange-500" />
            Bulk Campaign Generator
          </h1>
          <p className="text-slate-500 mt-1">
            Generate 100+ winning campaigns at once — one click, AI does the rest
          </p>
        </div>

        {/* Base Prompt */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Base Campaign Prompt</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              value={basePrompt}
              onChange={(e) => setBasePrompt(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              placeholder='Use {service} as a placeholder. E.g., "Create a Google Ads campaign for {service} in Miami..."'
            />
            <p className="text-xs text-slate-400 mt-1">
              Use <code className="bg-slate-100 px-1 rounded">{"{service}"}</code> as a placeholder — it gets replaced with each variant below.
            </p>
          </CardContent>
        </Card>

        {/* Service Variants */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Service Variants ({cleanCount})</CardTitle>
              <div className="flex gap-2">
                {Object.keys(EXAMPLE_VARIANTS).map((key) => (
                  <Button
                    key={key}
                    size="sm"
                    variant="outline"
                    onClick={() => loadTemplate(key)}
                    className="text-xs"
                  >
                    Load {key}
                  </Button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
              {variants.map((v, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-slate-400 w-6 text-right">{i + 1}.</span>
                  <input
                    type="text"
                    value={v}
                    onChange={(e) => updateVariant(i, e.target.value)}
                    placeholder="e.g., BMW Key Programming"
                    className="flex-1 px-3 py-1.5 border border-slate-200 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                  <button
                    onClick={() => removeVariant(i)}
                    className="text-slate-300 hover:text-red-500 transition"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={addVariant}
              className="mt-3"
            >
              <Plus className="w-3 h-3 mr-1" /> Add Variant
            </Button>
          </CardContent>
        </Card>

        {/* Launch Button */}
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-500">
            {cleanCount > 0
              ? `Ready to generate ${cleanCount} campaign${cleanCount > 1 ? "s" : ""}`
              : "Add at least one service variant"}
          </p>
          <Button
            onClick={launch}
            disabled={launching || cleanCount === 0 || !!isRunning}
            className="bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white px-8 py-3 text-lg"
          >
            {launching ? (
              <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Launching...</>
            ) : (
              <><Rocket className="w-5 h-5 mr-2" /> Generate {cleanCount} Campaigns</>
            )}
          </Button>
        </div>

        {/* Progress */}
        {status && (
          <Card className={
            status.status === "complete"
              ? "border-green-200 bg-green-50/50"
              : status.status === "failed"
              ? "border-red-200 bg-red-50/50"
              : "border-blue-200 bg-blue-50/50"
          }>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  {status.status === "complete" ? (
                    <CheckCircle className="w-5 h-5 text-green-600" />
                  ) : status.status === "failed" ? (
                    <AlertCircle className="w-5 h-5 text-red-600" />
                  ) : (
                    <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
                  )}
                  <span className="font-medium text-slate-900">
                    {status.status === "complete"
                      ? "All campaigns generated!"
                      : status.status === "failed"
                      ? "Generation failed"
                      : status.status === "queued"
                      ? "Queued — starting shortly..."
                      : `Generating: ${status.current_service || "..."}`}
                  </span>
                </div>
                <span className="text-sm text-slate-500">
                  {status.completed || 0} / {status.total || cleanCount} complete
                  {(status.errors || 0) > 0 && (
                    <span className="text-red-600 ml-2">({status.errors} errors)</span>
                  )}
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    status.status === "complete"
                      ? "bg-green-500"
                      : status.status === "failed"
                      ? "bg-red-500"
                      : "bg-blue-500"
                  }`}
                  style={{ width: `${status.progress_pct || 0}%` }}
                />
              </div>
              <p className="text-xs text-slate-400 mt-2 text-right">
                {status.progress_pct || 0}%
              </p>

              {status.error && (
                <p className="text-sm text-red-600 mt-2">{status.error}</p>
              )}

              {status.status === "complete" && (
                <p className="text-sm text-green-700 mt-3">
                  All campaigns have been generated and saved. View them in Campaigns.
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
