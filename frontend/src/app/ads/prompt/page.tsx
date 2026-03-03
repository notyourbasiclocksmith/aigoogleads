"use client";

import { useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Wand2, Send, Save, Rocket, ChevronDown, ChevronUp } from "lucide-react";

export default function PromptPage() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<any>(null);
  const [error, setError] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set([0]));

  async function handleGenerate() {
    if (!prompt.trim()) return;
    setError("");
    setLoading(true);
    try {
      const data = await api.post("/api/ads/prompt/generate", { prompt });
      setDraft(data);
    } catch (err: any) {
      setError(err.message || "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!draft) return;
    try {
      await api.post("/api/ads/prompt/save-draft", { draft });
      alert("Draft saved successfully!");
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleLaunch() {
    if (!draft) return;
    try {
      await api.post("/api/ads/prompt/approve-launch", { draft_id: draft.draft_id || "latest" });
      alert("Campaign approved and launching!");
    } catch (err: any) {
      setError(err.message);
    }
  }

  function toggleGroup(idx: number) {
    const next = new Set(expandedGroups);
    if (next.has(idx)) next.delete(idx);
    else next.add(idx);
    setExpandedGroups(next);
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Command Console</h1>
          <p className="text-muted-foreground">Describe what you want and let AI build your campaign</p>
        </div>

        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Example: Launch an emergency locksmith campaign targeting Dallas, Fort Worth, and Arlington. Focus on lockout services with a $50/day budget. Include our $20 off offer."
                className="w-full min-h-[120px] rounded-lg border border-input bg-background px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
              <div className="flex items-center gap-3">
                <Button onClick={handleGenerate} disabled={loading || !prompt.trim()}>
                  {loading ? (
                    <span className="flex items-center gap-2">Generating...</span>
                  ) : (
                    <span className="flex items-center gap-2">
                      <Wand2 className="w-4 h-4" /> Generate Campaign
                    </span>
                  )}
                </Button>
                <span className="text-xs text-muted-foreground">
                  AI will analyze your business profile, past performance, and industry learnings
                </span>
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </CardContent>
        </Card>

        {draft && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Campaign Preview</h2>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handleSave}>
                  <Save className="w-4 h-4 mr-2" /> Save Draft
                </Button>
                <Button onClick={handleLaunch}>
                  <Rocket className="w-4 h-4 mr-2" /> Approve & Launch
                </Button>
              </div>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">{draft.campaign?.name}</CardTitle>
                <CardDescription className="flex items-center gap-2">
                  <Badge variant="secondary">{draft.campaign?.type}</Badge>
                  <Badge variant="outline">{draft.campaign?.bidding_strategy}</Badge>
                  <span>${draft.campaign?.budget_daily}/day</span>
                </CardDescription>
              </CardHeader>
              <CardContent>
                {draft.reasoning && (
                  <div className="mb-4 p-3 rounded-lg bg-blue-50 border border-blue-100 text-sm">
                    <strong>AI Reasoning:</strong> {draft.reasoning.campaign_type_reason}
                    {draft.reasoning.learnings_applied > 0 && (
                      <span className="ml-2 text-blue-600">
                        ({draft.reasoning.learnings_applied} cross-tenant learnings applied)
                      </span>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {draft.ad_groups?.map((ag: any, idx: number) => (
              <Card key={idx}>
                <CardHeader className="cursor-pointer" onClick={() => toggleGroup(idx)}>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{ag.name}</CardTitle>
                    {expandedGroups.has(idx) ? (
                      <ChevronUp className="w-5 h-5 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="w-5 h-5 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>
                {expandedGroups.has(idx) && (
                  <CardContent className="space-y-4">
                    <div>
                      <h4 className="text-sm font-semibold mb-2">Keywords ({ag.keywords?.length || 0})</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {ag.keywords?.map((kw: any, ki: number) => (
                          <Badge key={ki} variant={kw.match_type === "EXACT" ? "default" : "secondary"}>
                            {kw.match_type === "EXACT" ? `[${kw.text}]` : kw.match_type === "PHRASE" ? `"${kw.text}"` : kw.text}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {ag.negatives && ag.negatives.length > 0 && (
                      <div>
                        <h4 className="text-sm font-semibold mb-2">Negatives ({ag.negatives.length})</h4>
                        <div className="flex flex-wrap gap-1.5">
                          {ag.negatives.slice(0, 15).map((n: any, ni: number) => (
                            <Badge key={ni} variant="destructive" className="text-xs">
                              -{n.text}
                            </Badge>
                          ))}
                          {ag.negatives.length > 15 && (
                            <span className="text-xs text-muted-foreground">+{ag.negatives.length - 15} more</span>
                          )}
                        </div>
                      </div>
                    )}

                    {ag.ads?.map((ad: any, ai: number) => (
                      <div key={ai} className="border rounded-lg p-4 bg-slate-50">
                        <h4 className="text-sm font-semibold mb-2">Responsive Search Ad</h4>
                        <div className="space-y-2">
                          <div>
                            <span className="text-xs text-muted-foreground">Headlines:</span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {ad.headlines?.map((h: string, hi: number) => (
                                <span key={hi} className="text-sm bg-white border rounded px-2 py-0.5">
                                  {h}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div>
                            <span className="text-xs text-muted-foreground">Descriptions:</span>
                            {ad.descriptions?.map((d: string, di: number) => (
                              <p key={di} className="text-sm mt-1 bg-white border rounded px-2 py-1">{d}</p>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </CardContent>
                )}
              </Card>
            ))}

            {draft.extensions && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Extensions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {draft.extensions.sitelinks && (
                    <div>
                      <h4 className="text-sm font-semibold mb-1">Sitelinks</h4>
                      <div className="grid grid-cols-2 gap-2">
                        {draft.extensions.sitelinks.map((sl: any, i: number) => (
                          <div key={i} className="text-sm border rounded p-2">
                            <div className="font-medium text-blue-600">{sl.text}</div>
                            <div className="text-xs text-muted-foreground">{sl.description}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {draft.extensions.callouts && (
                    <div>
                      <h4 className="text-sm font-semibold mb-1">Callouts</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {draft.extensions.callouts.map((c: string, i: number) => (
                          <Badge key={i} variant="outline">{c}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
