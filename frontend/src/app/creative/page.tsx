"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Palette, Wand2, Image, Copy, Rocket, Loader2, CheckCircle2 } from "lucide-react";

export default function CreativePage() {
  const [service, setService] = useState("");
  const [location, setLocation] = useState("");
  const [offer, setOffer] = useState("");
  const [tone, setTone] = useState("urgent");
  const [generatedCopy, setGeneratedCopy] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [imageJobId, setImageJobId] = useState<string | null>(null);
  const [imageStatus, setImageStatus] = useState<string | null>(null);

  // Deploy state
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

  async function handleGenerateImage() {
    try {
      const data = await api.post("/api/creative/image/generate", {
        template: "service_ad_banner",
        service,
        text_overlay: offer || service,
      });
      setImageJobId(data.job_id);
      setImageStatus(data.status);
    } catch (e: any) {
      console.error(e);
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
  }

  return (
    <AppLayout>
      <div className="space-y-8">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">Creative Studio</h1>
          <p className="text-[13px] text-slate-400 mt-0.5">Generate ad copy and images powered by AI</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-1 border-0">
            <CardHeader className="pb-2">
              <CardTitle className="text-[15px] tracking-tight">Generate Ad Copy</CardTitle>
              <CardDescription className="text-[12px]">Fill in details to generate headlines, descriptions, and extensions</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-slate-500">Service</label>
                <Input value={service} onChange={(e: any) => setService(e.target.value)} placeholder="Emergency Lockout" className="rounded-xl border-slate-200 text-[13px] h-10" />
              </div>
              <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-slate-500">Location</label>
                <Input value={location} onChange={(e: any) => setLocation(e.target.value)} placeholder="Dallas, TX" className="rounded-xl border-slate-200 text-[13px] h-10" />
              </div>
              <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-slate-500">Offer (optional)</label>
                <Input value={offer} onChange={(e: any) => setOffer(e.target.value)} placeholder="$20 Off Any Service" className="rounded-xl border-slate-200 text-[13px] h-10" />
              </div>
              <div className="space-y-1.5">
                <label className="text-[12px] font-medium text-slate-500">Tone</label>
                <select
                  value={tone}
                  onChange={(e: any) => setTone(e.target.value)}
                  className="flex h-10 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-600 cursor-pointer hover:border-slate-300 transition-colors"
                >
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
              <Button variant="outline" onClick={handleGenerateImage} disabled={!service} className="w-full h-10 text-[13px] rounded-xl">
                <Image className="w-4 h-4 mr-2" />
                Generate Image
              </Button>
              {imageStatus && (
                <p className="text-[11px] text-slate-400">
                  Image job: {imageJobId} — Status: {imageStatus}
                </p>
              )}
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
                          <div key={i} className="border border-slate-100/60 rounded-2xl p-4 hover:premium-shadow-lg transition-all duration-200">
                            <div className="font-medium text-blue-600 text-[13px]">{sl.text}</div>
                            <div className="text-[12px] text-slate-400 mt-1">{sl.description}</div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* ── Deploy to Google Ads ─────────────────────── */}
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
                            <label className="text-[12px] font-medium text-slate-500">Account</label>
                            <select className="flex h-10 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-600" value={selectedAccount} onChange={(e: any) => setSelectedAccount(e.target.value)}>
                              <option value="">Select account...</option>
                              {accounts.map((a: any) => (
                                <option key={a.id} value={a.id}>{a.name || a.customer_id}</option>
                              ))}
                            </select>
                          </div>
                        )}
                        <div className="space-y-1.5">
                          <label className="text-[12px] font-medium text-slate-500">Campaign</label>
                          <select className="flex h-10 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-600" value={selectedCampaign} onChange={(e: any) => setSelectedCampaign(e.target.value)}>
                            <option value="">Select campaign...</option>
                            {campaigns.map((c: any) => (
                              <option key={c.campaign_id || c.id} value={c.campaign_id || c.id}>{c.name}</option>
                            ))}
                          </select>
                        </div>
                        {adGroups.length > 0 && (
                          <div className="space-y-1.5">
                            <label className="text-[12px] font-medium text-slate-500">Ad Group</label>
                            <select className="flex h-10 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-600" value={selectedAdGroup} onChange={(e: any) => setSelectedAdGroup(e.target.value)}>
                              <option value="">Select ad group...</option>
                              {adGroups.map((ag: any) => (
                                <option key={ag.ad_group_id || ag.id} value={ag.ad_group_id || ag.id}>{ag.name}</option>
                              ))}
                            </select>
                          </div>
                        )}
                        <div className="space-y-1.5">
                          <label className="text-[12px] font-medium text-slate-500">Landing Page URL</label>
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
      </div>
    </AppLayout>
  );
}
