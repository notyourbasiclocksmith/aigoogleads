"use client";

import { useState, useEffect } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Bell, Plus, Trash2, Send, History, Hash, Mail, Globe } from "lucide-react";
import { api } from "@/lib/api";

export default function NotificationsPage() {
  const [channels, setChannels] = useState<any[]>([]);
  const [rules, setRules] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [channelForm, setChannelForm] = useState({ type: "slack", name: "", config_key: "" });
  const [ruleForm, setRuleForm] = useState({ event_type: "", channel_id: "", min_severity: "warning" });
  const [loading, setLoading] = useState(false);
  const tenantId = typeof window !== "undefined" ? localStorage.getItem("tenant_id") || "" : "";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [ch, ru, hi] = await Promise.all([
        api.get(`/api/v2/notifications/channels?tenant_id=${tenantId}`),
        api.get(`/api/v2/notifications/rules?tenant_id=${tenantId}`),
        api.get(`/api/v2/notifications/history?tenant_id=${tenantId}&limit=30`),
      ]);
      setChannels(ch);
      setRules(ru);
      setHistory(hi);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function addChannel() {
    if (!channelForm.type) return;
    const config: any = {};
    if (channelForm.type === "slack") config.webhook_url = channelForm.config_key;
    else if (channelForm.type === "email") config.to_email = channelForm.config_key;
    else config.url = channelForm.config_key;

    await api.post("/api/v2/notifications/channels", {
      tenant_id: tenantId, type: channelForm.type,
      name: channelForm.name || channelForm.type, config,
    });
    setChannelForm({ type: "slack", name: "", config_key: "" });
    await loadAll();
  }

  async function deleteChannel(id: string) {
    await api.delete(`/api/v2/notifications/channels/${id}?tenant_id=${tenantId}`);
    await loadAll();
  }

  async function testChannel(id: string) {
    await api.post("/api/v2/notifications/test", { tenant_id: tenantId, channel_id: id });
    await loadAll();
  }

  async function addRule() {
    if (!ruleForm.event_type) return;
    await api.post("/api/v2/notifications/rules", {
      tenant_id: tenantId,
      event_type: ruleForm.event_type,
      channel_id: ruleForm.channel_id || null,
      min_severity: ruleForm.min_severity,
    });
    setRuleForm({ event_type: "", channel_id: "", min_severity: "warning" });
    await loadAll();
  }

  async function deleteRule(id: string) {
    await api.delete(`/api/v2/notifications/rules/${id}?tenant_id=${tenantId}`);
    await loadAll();
  }

  const channelIcon = (type: string) => {
    if (type === "slack") return <Hash className="w-4 h-4" />;
    if (type === "email") return <Mail className="w-4 h-4" />;
    return <Globe className="w-4 h-4" />;
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Notifications & Alerting</h1>
          <p className="text-slate-500 mt-1">Configure delivery channels, routing rules, and review notification history</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Channels */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Bell className="w-5 h-5" /> Channels ({channels.length})</CardTitle>
              <CardDescription>Where notifications are delivered</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-2">
                <select
                  className="border rounded-lg px-3 py-2 text-sm bg-white"
                  value={channelForm.type}
                  onChange={(e) => setChannelForm({ ...channelForm, type: e.target.value })}
                >
                  <option value="slack">Slack</option>
                  <option value="email">Email</option>
                  <option value="webhook">Webhook</option>
                </select>
                <Input placeholder="Channel Name" value={channelForm.name} onChange={(e) => setChannelForm({ ...channelForm, name: e.target.value })} />
                <Input
                  placeholder={channelForm.type === "slack" ? "Webhook URL" : channelForm.type === "email" ? "Email Address" : "Webhook URL"}
                  value={channelForm.config_key}
                  onChange={(e) => setChannelForm({ ...channelForm, config_key: e.target.value })}
                />
                <Button size="sm" onClick={addChannel}><Plus className="w-3 h-3 mr-1" /> Add Channel</Button>
              </div>

              {channels.length > 0 && (
                <div className="space-y-2 mt-3">
                  {channels.map((ch: any) => (
                    <div key={ch.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                      <div className="flex items-center gap-2">
                        {channelIcon(ch.type)}
                        <div>
                          <div className="text-sm font-medium">{ch.name}</div>
                          <div className="text-xs text-slate-400">{ch.type}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Badge variant={ch.enabled ? "default" : "secondary"} className="text-xs">
                          {ch.enabled ? "On" : "Off"}
                        </Badge>
                        <Button size="sm" variant="ghost" onClick={() => testChannel(ch.id)}>
                          <Send className="w-3 h-3" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => deleteChannel(ch.id)}>
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Rules */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2"><Bell className="w-5 h-5" /> Routing Rules ({rules.length})</CardTitle>
              <CardDescription>Which events go to which channels</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-2">
                <Input placeholder="Event type (e.g. budget_alert, rollback_trigger, *)" value={ruleForm.event_type} onChange={(e) => setRuleForm({ ...ruleForm, event_type: e.target.value })} />
                <select
                  className="border rounded-lg px-3 py-2 text-sm bg-white"
                  value={ruleForm.channel_id}
                  onChange={(e) => setRuleForm({ ...ruleForm, channel_id: e.target.value })}
                >
                  <option value="">Select channel...</option>
                  {channels.map((ch: any) => (
                    <option key={ch.id} value={ch.id}>{ch.name} ({ch.type})</option>
                  ))}
                </select>
                <select
                  className="border rounded-lg px-3 py-2 text-sm bg-white"
                  value={ruleForm.min_severity}
                  onChange={(e) => setRuleForm({ ...ruleForm, min_severity: e.target.value })}
                >
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                  <option value="critical">Critical</option>
                </select>
                <Button size="sm" onClick={addRule}><Plus className="w-3 h-3 mr-1" /> Add Rule</Button>
              </div>

              {rules.length > 0 && (
                <div className="space-y-2 mt-3">
                  {rules.map((r: any) => (
                    <div key={r.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg text-sm">
                      <div>
                        <span className="font-medium">{r.event_type}</span>
                        <span className="text-slate-400 mx-2">&rarr;</span>
                        <span className="text-slate-500">{channels.find((c: any) => c.id === r.channel_id)?.name || "any"}</span>
                        <Badge variant="outline" className="ml-2 text-xs">&ge; {r.min_severity}</Badge>
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => deleteRule(r.id)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* History */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><History className="w-5 h-5" /> Delivery History</CardTitle>
          </CardHeader>
          <CardContent>
            {history.length === 0 ? (
              <p className="text-sm text-slate-500">No notifications sent yet.</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {history.map((h: any) => (
                  <div key={h.id} className="flex items-center justify-between p-3 border-b text-sm">
                    <div className="flex items-center gap-2">
                      <Badge variant={h.status === "sent" ? "default" : "destructive"} className="text-xs">{h.status}</Badge>
                      <span className="font-medium">{h.event_type}</span>
                    </div>
                    <span className="text-xs text-slate-400">{new Date(h.sent_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
