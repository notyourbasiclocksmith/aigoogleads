"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Plug, Plus, RefreshCw, Trash2, Activity, Wifi, WifiOff } from "lucide-react";
import { api } from "@/lib/api";

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<any[]>([]);
  const [available, setAvailable] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [selectedConnector, setSelectedConnector] = useState<string | null>(null);
  const [connectForm, setConnectForm] = useState({ type: "", name: "", credential_key: "" });
  const [loading, setLoading] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [conns, avail] = await Promise.all([
        api.get(`/api/v2/connectors/list?tenant_id=${tenantId}`),
        api.get("/api/v2/connectors/available"),
      ]);
      setConnectors(conns);
      setAvailable(avail);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function connectNew() {
    if (!connectForm.type) return;
    const credentials: any = {};
    if (connectForm.type === "slack_webhook") credentials.webhook_url = connectForm.credential_key;
    else if (connectForm.type === "generic_webhook") credentials.url = connectForm.credential_key;
    else credentials.api_key = connectForm.credential_key;

    try {
      await api.post("/api/v2/connectors/connect", {
        tenant_id: tenantId, type: connectForm.type,
        name: connectForm.name || connectForm.type.replace("_", " "),
        credentials, config: {},
      });
      setConnectForm({ type: "", name: "", credential_key: "" });
      await loadAll();
    } catch (e) { console.error(e); }
  }

  async function syncConnector(id: string) {
    await api.post("/api/v2/connectors/sync", { tenant_id: tenantId, connector_id: id });
    await loadAll();
  }

  async function deleteConnector(id: string) {
    await api.delete(`/api/v2/connectors/${id}?tenant_id=${tenantId}`);
    await loadAll();
  }

  async function loadEvents(connectorId: string) {
    setSelectedConnector(connectorId);
    const evts = await api.get(`/api/v2/connectors/events?tenant_id=${tenantId}&connector_id=${connectorId}`);
    setEvents(evts);
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Connectors</h1>
          <p className="text-slate-500 mt-1">Connect external platforms — CRM, Slack, email, webhooks, and future ad channels</p>
        </div>

        {/* Add Connector */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Plus className="w-5 h-5" /> Add Connector</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <select
                className="border rounded-lg px-3 py-2 text-sm bg-white"
                value={connectForm.type}
                onChange={(e) => setConnectForm({ ...connectForm, type: e.target.value })}
              >
                <option value="">Select type...</option>
                {available.map((a: any) => (
                  <option key={a.type} value={a.type}>{a.label}{!a.implemented ? " (Coming Soon)" : ""}</option>
                ))}
              </select>
              <Input placeholder="Display Name" value={connectForm.name} onChange={(e) => setConnectForm({ ...connectForm, name: e.target.value })} />
              <Input placeholder="API Key / Webhook URL" value={connectForm.credential_key} onChange={(e) => setConnectForm({ ...connectForm, credential_key: e.target.value })} />
              <Button onClick={connectNew} disabled={!connectForm.type}>Connect</Button>
            </div>
          </CardContent>
        </Card>

        {/* Active Connectors */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Plug className="w-5 h-5" /> Active Connectors ({connectors.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {connectors.length === 0 ? (
              <p className="text-sm text-slate-500">No connectors configured. Add one above.</p>
            ) : (
              <div className="space-y-3">
                {connectors.map((c: any) => (
                  <div key={c.id} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center gap-3">
                      {c.status === "connected" ? (
                        <Wifi className="w-5 h-5 text-green-500" />
                      ) : (
                        <WifiOff className="w-5 h-5 text-slate-400" />
                      )}
                      <div>
                        <div className="font-medium text-sm">{c.name}</div>
                        <div className="text-xs text-slate-500">
                          {c.type} &bull; {c.last_sync_at ? `Last sync: ${new Date(c.last_sync_at).toLocaleDateString()}` : "Never synced"}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={c.status === "connected" ? "default" : c.status === "error" ? "destructive" : "secondary"}>
                        {c.status}
                      </Badge>
                      <Button size="sm" variant="outline" onClick={() => syncConnector(c.id)}>
                        <RefreshCw className="w-3 h-3 mr-1" /> Sync
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => loadEvents(c.id)}>
                        <Activity className="w-3 h-3 mr-1" /> Events
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => deleteConnector(c.id)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Event Log */}
        {selectedConnector && events.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Activity className="w-5 h-5" /> Connector Events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {events.map((e: any) => (
                  <div key={e.id} className="flex items-start gap-2 p-2 border-b text-sm">
                    <Badge variant={e.level === "error" ? "destructive" : e.level === "warning" ? "outline" : "secondary"} className="text-xs mt-0.5">
                      {e.level}
                    </Badge>
                    <div>
                      <div>{e.message}</div>
                      <div className="text-xs text-slate-400">{new Date(e.created_at).toLocaleString()}</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
