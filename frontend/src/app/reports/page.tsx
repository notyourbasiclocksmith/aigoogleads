"use client";

import { useEffect, useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { FileText, Download, RefreshCw } from "lucide-react";

export default function ReportsPage() {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/api/reports").then(setReports).catch(() => setReports([])).finally(() => setLoading(false));
  }, []);

  async function triggerReport() {
    try {
      await api.post("/api/reports/generate", { report_type: "weekly_digest" });
      alert("Report generation started. It will appear here shortly.");
      const updated = await api.get("/api/reports");
      setReports(updated);
    } catch (e) { console.error(e); }
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
            <p className="text-muted-foreground">AI-generated performance reports and insights</p>
          </div>
          <Button onClick={triggerReport}>
            <RefreshCw className="w-4 h-4 mr-2" /> Generate Report
          </Button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6"><div className="h-6 bg-slate-200 rounded w-64" /></CardContent>
              </Card>
            ))}
          </div>
        ) : reports.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <FileText className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No reports yet. Click Generate Report to create your first one.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {reports.map((r: any) => (
              <Card key={r.id}>
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-blue-600" />
                      </div>
                      <div>
                        <h3 className="font-medium">{r.report_type?.replace("_", " ") || "Report"}</h3>
                        <p className="text-sm text-muted-foreground">
                          {r.period_start && r.period_end
                            ? `${new Date(r.period_start).toLocaleDateString()} — ${new Date(r.period_end).toLocaleDateString()}`
                            : new Date(r.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant={r.status === "delivered" ? "success" : "secondary"} className="capitalize">
                        {r.status}
                      </Badge>
                      {r.pdf_url && (
                        <Button variant="ghost" size="sm" onClick={() => window.open(r.pdf_url, "_blank")}>
                          <Download className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  {r.summary_json && (
                    <div className="mt-3 p-3 rounded-lg bg-slate-50 border text-sm">
                      {typeof r.summary_json === "string" ? r.summary_json : (
                        <>
                          {r.summary_json.headline && <p className="font-medium mb-1">{r.summary_json.headline}</p>}
                          {r.summary_json.key_findings && (
                            <ul className="list-disc list-inside text-muted-foreground space-y-0.5">
                              {r.summary_json.key_findings.map((f: string, i: number) => (
                                <li key={i}>{f}</li>
                              ))}
                            </ul>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}
