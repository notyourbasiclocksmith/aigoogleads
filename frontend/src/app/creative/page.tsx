"use client";

import { useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Palette, Wand2, Image, Copy } from "lucide-react";

export default function CreativePage() {
  const [service, setService] = useState("");
  const [location, setLocation] = useState("");
  const [offer, setOffer] = useState("");
  const [tone, setTone] = useState("urgent");
  const [generatedCopy, setGeneratedCopy] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [imageJobId, setImageJobId] = useState<string | null>(null);
  const [imageStatus, setImageStatus] = useState<string | null>(null);

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
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Creative Studio</h1>
          <p className="text-muted-foreground">Generate ad copy and images powered by AI</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-base">Generate Ad Copy</CardTitle>
              <CardDescription>Fill in details to generate headlines, descriptions, and extensions</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Service</label>
                <Input value={service} onChange={(e) => setService(e.target.value)} placeholder="Emergency Lockout" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Location</label>
                <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Dallas, TX" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Offer (optional)</label>
                <Input value={offer} onChange={(e) => setOffer(e.target.value)} placeholder="$20 Off Any Service" />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Tone</label>
                <select
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  <option value="urgent">Urgent</option>
                  <option value="professional">Professional</option>
                  <option value="friendly">Friendly</option>
                  <option value="authoritative">Authoritative</option>
                </select>
              </div>
              <Button onClick={handleGenerateCopy} disabled={loading || !service} className="w-full">
                <Wand2 className="w-4 h-4 mr-2" />
                {loading ? "Generating..." : "Generate Copy"}
              </Button>
              <Button variant="outline" onClick={handleGenerateImage} disabled={!service} className="w-full">
                <Image className="w-4 h-4 mr-2" />
                Generate Image
              </Button>
              {imageStatus && (
                <p className="text-xs text-muted-foreground">
                  Image job: {imageJobId} — Status: {imageStatus}
                </p>
              )}
            </CardContent>
          </Card>

          <div className="lg:col-span-2 space-y-4">
            {generatedCopy ? (
              <>
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <Palette className="w-5 h-5 text-blue-500" /> Headlines
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {generatedCopy.headlines?.map((h: string, i: number) => (
                        <div key={i} className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 border">
                          <span className="text-sm font-medium">{h}</span>
                          <button onClick={() => copyToClipboard(h)} className="text-muted-foreground hover:text-primary">
                            <Copy className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Descriptions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {generatedCopy.descriptions?.map((d: string, i: number) => (
                        <div key={i} className="flex items-start justify-between p-2.5 rounded-lg bg-slate-50 border">
                          <span className="text-sm">{d}</span>
                          <button onClick={() => copyToClipboard(d)} className="text-muted-foreground hover:text-primary ml-2">
                            <Copy className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {generatedCopy.callouts && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Callout Extensions</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {generatedCopy.callouts.map((c: string, i: number) => (
                          <Badge key={i} variant="outline" className="text-sm py-1 px-3">{c}</Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {generatedCopy.sitelinks && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Sitelink Extensions</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-3">
                        {generatedCopy.sitelinks.map((sl: any, i: number) => (
                          <div key={i} className="border rounded-lg p-3">
                            <div className="font-medium text-blue-600 text-sm">{sl.text}</div>
                            <div className="text-xs text-muted-foreground mt-0.5">{sl.description}</div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : (
              <Card>
                <CardContent className="p-12 text-center">
                  <Palette className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">Fill in the details on the left and click Generate to create ad copy</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
