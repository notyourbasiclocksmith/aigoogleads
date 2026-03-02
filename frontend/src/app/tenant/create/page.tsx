"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Building2, ArrowRight } from "lucide-react";

export default function TenantCreatePage() {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [tz, setTz] = useState("America/Chicago");
  const [website, setWebsite] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  async function handleCreate() {
    if (!name.trim()) { setError("Business name is required"); return; }
    setLoading(true);
    setError("");
    try {
      const result = await api.post("/api/tenants", {
        name: name.trim(),
        industry: industry || null,
        timezone: tz,
        website: website || null,
      });
      if (result.access_token) {
        api.setToken(result.access_token);
        if (typeof window !== "undefined") {
          localStorage.setItem("tenant_id", result.tenant.id);
          localStorage.setItem("tenant_role", "owner");
        }
      }
      router.push(`/workspace/${result.tenant.id}/dashboard`);
    } catch (e: any) {
      setError(e.message || "Failed to create workspace");
    }
    setLoading(false);
  }

  const industries = [
    "Plumbing", "HVAC", "Roofing", "Electrical", "Locksmith",
    "Landscaping", "Pest Control", "Cleaning", "Legal", "Dental",
    "Auto Repair", "Real Estate", "Home Services", "Other",
  ];

  const timezones = [
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Phoenix", "Pacific/Honolulu",
    "Europe/London", "Europe/Berlin", "Asia/Tokyo", "Australia/Sydney",
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center font-bold text-white text-lg mx-auto mb-4">
            IA
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Create New Business</h1>
          <p className="text-slate-500 mt-1">Set up a new workspace for your business</p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm p-3 rounded-lg">{error}</div>
          )}

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Business Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Not Your Basic Locksmith"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Industry</label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
            >
              <option value="">Select industry...</option>
              {industries.map((i) => <option key={i} value={i.toLowerCase()}>{i}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Timezone</label>
            <select
              value={tz}
              onChange={(e) => setTz(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
            >
              {timezones.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Website (optional)</label>
            <input
              type="url"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="https://example.com"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <button
            onClick={handleCreate}
            disabled={loading || !name.trim()}
            className="w-full bg-blue-600 text-white py-2.5 rounded-lg font-medium hover:bg-blue-700 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {loading ? (
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <>Create Workspace <ArrowRight className="w-4 h-4" /></>
            )}
          </button>
        </div>

        <button
          onClick={() => router.push("/tenant/select")}
          className="w-full mt-4 text-center text-sm text-slate-500 hover:text-slate-700"
        >
          Back to workspace list
        </button>
      </div>
    </div>
  );
}
