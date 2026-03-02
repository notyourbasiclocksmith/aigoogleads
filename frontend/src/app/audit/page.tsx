"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { ClipboardCheck, AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";

interface AuditItem {
  category: string;
  check: string;
  status: "pass" | "warn" | "fail";
  message: string;
  recommendation?: string;
}

export default function AuditPage() {
  const [auditResults, setAuditResults] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    api.get("/api/diagnostics/audit").then((data) => {
      setAuditResults(Array.isArray(data) ? data : []);
    }).catch(() => setAuditResults([])).finally(() => setLoading(false));
  }, []);

  async function runAudit() {
    setRunning(true);
    try {
      const data = await api.post("/api/diagnostics/audit/run");
      setAuditResults(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
    finally { setRunning(false); }
  }

  const passes = auditResults.filter((a) => a.status === "pass").length;
  const warns = auditResults.filter((a) => a.status === "warn").length;
  const fails = auditResults.filter((a) => a.status === "fail").length;

  const statusIcon = (status: string) => {
    if (status === "pass") return <CheckCircle2 className="w-5 h-5 text-green-500" />;
    if (status === "warn") return <AlertCircle className="w-5 h-5 text-yellow-500" />;
    return <AlertCircle className="w-5 h-5 text-red-500" />;
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Account Audit</h1>
            <p className="text-muted-foreground">Comprehensive health check of your Google Ads account</p>
          </div>
          <Button onClick={runAudit} disabled={running}>
            <RefreshCw className={`w-4 h-4 mr-2 ${running ? "animate-spin" : ""}`} />
            {running ? "Running..." : "Run Audit"}
          </Button>
        </div>

        {!loading && auditResults.length > 0 && (
          <div className="grid grid-cols-3 gap-4">
            <Card>
              <CardContent className="p-5 flex items-center gap-3">
                <CheckCircle2 className="w-8 h-8 text-green-500" />
                <div>
                  <div className="text-2xl font-bold text-green-600">{passes}</div>
                  <div className="text-sm text-muted-foreground">Passed</div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5 flex items-center gap-3">
                <AlertCircle className="w-8 h-8 text-yellow-500" />
                <div>
                  <div className="text-2xl font-bold text-yellow-600">{warns}</div>
                  <div className="text-sm text-muted-foreground">Warnings</div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5 flex items-center gap-3">
                <AlertCircle className="w-8 h-8 text-red-500" />
                <div>
                  <div className="text-2xl font-bold text-red-600">{fails}</div>
                  <div className="text-sm text-muted-foreground">Failed</div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6"><div className="h-6 bg-slate-200 rounded w-80" /></CardContent>
              </Card>
            ))}
          </div>
        ) : auditResults.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <ClipboardCheck className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No audit results yet. Click Run Audit to check your account health.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {auditResults.map((item, i) => (
              <Card key={i}>
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    {statusIcon(item.status)}
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-medium text-sm">{item.check}</span>
                        <Badge variant="outline" className="text-xs">{item.category}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{item.message}</p>
                      {item.recommendation && item.status !== "pass" && (
                        <p className="text-xs text-blue-600 mt-1">Recommendation: {item.recommendation}</p>
                      )}
                    </div>
                    <Badge
                      variant={item.status === "pass" ? "success" : item.status === "warn" ? "warning" : "destructive"}
                      className="capitalize"
                    >
                      {item.status}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
