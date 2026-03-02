"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { ShieldCheck, Activity, Key, Filter } from "lucide-react";

interface AuditEvent {
  id: string;
  event_type: string;
  severity: string;
  user_id: string | null;
  metadata: Record<string, any>;
  ip_address: string | null;
  created_at: string;
}

export default function SecurityAuditPage() {
  const params = useParams();
  const tenantId = params?.tenantId as string;
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState("");

  useEffect(() => {
    if (tenantId) loadEvents();
  }, [tenantId, filterType]);

  async function loadEvents() {
    setLoading(true);
    try {
      let url = `/api/tenants/${tenantId}/audit?limit=100`;
      if (filterType) url += `&event_type=${filterType}`;
      const data = await api.get(url);
      setEvents(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  const severityColor: Record<string, string> = {
    info: "bg-blue-100 text-blue-700",
    warn: "bg-yellow-100 text-yellow-700",
    high: "bg-red-100 text-red-700",
  };

  const eventTypes = [
    "TENANT_SWITCH", "INVITE_SENT", "INVITE_ACCEPTED", "INVITE_REVOKED",
    "ROLE_CHANGED", "MEMBER_REMOVED", "TENANT_CREATED",
    "LOGIN", "LOGOUT", "PERMISSION_DENIED",
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Security & Audit Log</h1>
        <p className="text-slate-500 mt-1">Review security events, access changes, and workspace activity</p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-5 h-5 text-green-500" />
            <span className="text-sm font-medium text-slate-700">Tenant Isolation</span>
          </div>
          <div className="text-lg font-bold text-green-700">Active</div>
          <div className="text-xs text-slate-400">All queries enforced by tenant_id filter</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Key className="w-5 h-5 text-blue-500" />
            <span className="text-sm font-medium text-slate-700">Integration Tokens</span>
          </div>
          <div className="text-lg font-bold text-blue-700">Encrypted</div>
          <div className="text-xs text-slate-400">Fernet AES-128 at rest</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-5 h-5 text-indigo-500" />
            <span className="text-sm font-medium text-slate-700">Audit Events</span>
          </div>
          <div className="text-lg font-bold text-indigo-700">{events.length}</div>
          <div className="text-xs text-slate-400">Recent events logged</div>
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-slate-400" />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">All event types</option>
          {eventTypes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {/* Audit Events Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading audit log...</div>
        ) : events.length === 0 ? (
          <div className="p-8 text-center text-slate-400">No audit events found.</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Time</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Event</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Severity</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">IP</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Details</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-b border-slate-50 hover:bg-slate-25">
                  <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm font-mono font-medium text-slate-900">{e.event_type}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${severityColor[e.severity] || "bg-slate-100 text-slate-600"}`}>
                      {e.severity}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400 font-mono">{e.ip_address || "—"}</td>
                  <td className="px-4 py-3 text-xs text-slate-500 max-w-xs truncate">
                    {Object.keys(e.metadata || {}).length > 0
                      ? JSON.stringify(e.metadata)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
