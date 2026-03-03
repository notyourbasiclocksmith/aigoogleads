"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { api } from "@/lib/api";
import { CheckCircle2, ArrowRight, ArrowLeft, Building2, Globe, Link2, Target, Settings2 } from "lucide-react";

const steps = [
  { label: "Business Info", icon: Building2 },
  { label: "Website & Social", icon: Globe },
  { label: "Connect Google Ads", icon: Link2 },
  { label: "Goals & Budget", icon: Target },
  { label: "Preferences", icon: Settings2 },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [tenantName, setTenantName] = useState("");
  const [industry, setIndustry] = useState("");
  const [phone, setPhone] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [description, setDescription] = useState("");
  const [facebookUrl, setFacebookUrl] = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [tiktokUrl, setTiktokUrl] = useState("");
  const [gbpLink, setGbpLink] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("");
  const [conversionGoal, setConversionGoal] = useState("calls");
  const [autonomyMode, setAutonomyMode] = useState("suggest");

  async function handleNext() {
    setError("");
    setLoading(true);
    try {
      if (step === 0) {
        const res = await api.post("/api/onboarding/step1", {
          tenant_name: tenantName,
          industry,
          phone,
        });
        // Save tenant-scoped token for subsequent steps
        if (res.access_token) {
          api.setToken(res.access_token);
        }
      } else if (step === 1) {
        await api.post("/api/onboarding/step2", {
          website_url: websiteUrl,
          description,
          social_links: {
            facebook: facebookUrl,
            instagram: instagramUrl,
            tiktok: tiktokUrl,
          },
          gbp_link: gbpLink,
        });
      } else if (step === 2) {
        // Skip OAuth for now — user can connect later
      } else if (step === 3) {
        await api.post("/api/onboarding/step4", {
          monthly_budget: parseInt(monthlyBudget) || 1000,
          conversion_goal: conversionGoal,
        });
      } else if (step === 4) {
        await api.post("/api/onboarding/step5", {
          autonomy_mode: autonomyMode,
        });
        router.push("/dashboard");
        return;
      }
      setStep(step + 1);
    } catch (err: any) {
      setError(err.message || "Failed to save step");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-900">Set Up Your Account</h1>
          <p className="text-muted-foreground mt-2">
            Step {step + 1} of {steps.length}: {steps[step].label}
          </p>
        </div>

        <div className="flex items-center justify-center gap-2 mb-8">
          {steps.map((s, i) => {
            const Icon = s.icon;
            return (
              <div key={i} className="flex items-center">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                    i < step
                      ? "bg-green-500 text-white"
                      : i === step
                      ? "bg-blue-600 text-white"
                      : "bg-slate-200 text-slate-500"
                  }`}
                >
                  {i < step ? <CheckCircle2 className="w-5 h-5" /> : <Icon className="w-5 h-5" />}
                </div>
                {i < steps.length - 1 && (
                  <div className={`w-8 h-0.5 mx-1 ${i < step ? "bg-green-500" : "bg-slate-200"}`} />
                )}
              </div>
            );
          })}
        </div>

        <Card>
          <CardContent className="p-6 space-y-4">
            {step === 0 && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Business Name</label>
                  <Input value={tenantName} onChange={(e) => setTenantName(e.target.value)} placeholder="Ace Locksmith Dallas" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Industry</label>
                  <select
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="">Select industry...</option>
                    <option value="locksmith">Locksmith</option>
                    <option value="roofing">Roofing</option>
                    <option value="hvac">HVAC</option>
                    <option value="plumbing">Plumbing</option>
                    <option value="auto_repair">Auto Repair</option>
                    <option value="electrical">Electrical</option>
                    <option value="pest_control">Pest Control</option>
                    <option value="landscaping">Landscaping</option>
                    <option value="cleaning">Cleaning</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Phone Number</label>
                  <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="(214) 555-0123" />
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Website URL</label>
                  <Input value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} placeholder="https://www.yourbusiness.com" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Business Description</label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Brief description of your services..."
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm min-h-[80px]"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Facebook Page URL</label>
                  <Input value={facebookUrl} onChange={(e) => setFacebookUrl(e.target.value)} placeholder="https://facebook.com/yourbiz" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Instagram URL</label>
                  <Input value={instagramUrl} onChange={(e) => setInstagramUrl(e.target.value)} placeholder="https://instagram.com/yourbiz" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">TikTok URL</label>
                  <Input value={tiktokUrl} onChange={(e) => setTiktokUrl(e.target.value)} placeholder="https://tiktok.com/@yourbiz" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Google Business Profile Link</label>
                  <Input value={gbpLink} onChange={(e) => setGbpLink(e.target.value)} placeholder="https://g.page/yourbiz" />
                </div>
              </>
            )}

            {step === 2 && (
              <div className="text-center py-8 space-y-4">
                <div className="w-16 h-16 mx-auto rounded-full bg-blue-100 flex items-center justify-center">
                  <Link2 className="w-8 h-8 text-blue-600" />
                </div>
                <h3 className="text-lg font-semibold">Connect Google Ads</h3>
                <p className="text-muted-foreground max-w-md mx-auto">
                  Connect your Google Ads account to enable campaign management, performance monitoring, and AI-powered optimizations.
                </p>
                <Button variant="outline" size="lg" onClick={() => window.open("/api/onboarding/step3/oauth-url", "_blank")}>
                  Connect Google Ads Account
                </Button>
                <p className="text-xs text-muted-foreground">You can also connect later from Settings</p>
              </div>
            )}

            {step === 3 && (
              <>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Monthly Ad Budget ($)</label>
                  <Input type="number" value={monthlyBudget} onChange={(e) => setMonthlyBudget(e.target.value)} placeholder="1000" />
                  <p className="text-xs text-muted-foreground">Approximate monthly Google Ads spend</p>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Primary Conversion Goal</label>
                  <select
                    value={conversionGoal}
                    onChange={(e) => setConversionGoal(e.target.value)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="calls">Phone Calls</option>
                    <option value="forms">Form Submissions</option>
                    <option value="bookings">Online Bookings</option>
                    <option value="purchases">Purchases</option>
                  </select>
                </div>
              </>
            )}

            {step === 4 && (
              <>
                <h3 className="text-lg font-semibold">Autonomy Mode</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Choose how much control Ignite Ads AI has over your campaigns.
                </p>
                {[
                  { mode: "suggest", title: "Suggest Only", desc: "AI analyzes and recommends. You approve every change." },
                  { mode: "semi_auto", title: "Semi-Autopilot", desc: "AI applies low-risk changes automatically. You approve medium/high-risk changes." },
                  { mode: "full_auto", title: "Full Autopilot", desc: "AI applies all safe changes automatically. You approve only high-risk changes." },
                ].map((opt) => (
                  <button
                    key={opt.mode}
                    onClick={() => setAutonomyMode(opt.mode)}
                    className={`w-full text-left p-4 rounded-lg border-2 transition-colors ${
                      autonomyMode === opt.mode ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className="font-medium">{opt.title}</div>
                    <div className="text-sm text-muted-foreground mt-1">{opt.desc}</div>
                  </button>
                ))}
              </>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
          <CardFooter className="flex justify-between">
            <Button variant="ghost" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
            <Button onClick={handleNext} disabled={loading}>
              {loading ? "Saving..." : step === steps.length - 1 ? "Finish Setup" : "Continue"}
              {step < steps.length - 1 && <ArrowRight className="w-4 h-4 ml-2" />}
            </Button>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
