"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { Building2, Plus } from "lucide-react";

export default function TenantSelectPage() {
  const router = useRouter();
  const [tenants, setTenants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/auth/tenants").then((data) => {
      setTenants(Array.isArray(data) ? data : []);
    }).catch(() => setTenants([])).finally(() => setLoading(false));
  }, []);

  async function selectTenant(tenantId: string) {
    try {
      const data = await api.post("/api/auth/select-tenant", { tenant_id: tenantId });
      api.setToken(data.access_token);
      localStorage.setItem("tenant_id", tenantId);
      router.push("/dashboard");
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">Select Account</h1>
          <p className="text-muted-foreground mt-2">Choose which business account to manage</p>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6"><div className="h-10 bg-slate-200 rounded" /></CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {tenants.map((t: any) => (
              <Card
                key={t.tenant_id || t.id}
                className="cursor-pointer hover:border-blue-300 transition-colors"
                onClick={() => selectTenant(t.tenant_id || t.id)}
              >
                <CardContent className="p-5 flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-blue-100 flex items-center justify-center">
                    <Building2 className="w-6 h-6 text-blue-600" />
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold">{t.name || t.tenant_name}</h3>
                    <p className="text-sm text-muted-foreground">{t.industry || "Business"}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
            <Button
              variant="outline"
              className="w-full"
              onClick={() => router.push("/onboarding")}
            >
              <Plus className="w-4 h-4 mr-2" /> Add New Business
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
