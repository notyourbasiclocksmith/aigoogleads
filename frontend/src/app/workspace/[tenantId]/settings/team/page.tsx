"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Users, UserPlus, Shield, Trash2, ChevronDown } from "lucide-react";

interface Member {
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  joined_at: string;
}

interface Invite {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at: string;
}

export default function TeamManagementPage() {
  const params = useParams();
  const tenantId = params?.tenantId as string;
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("viewer");
  const [loading, setLoading] = useState(true);
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const myRole = typeof window !== "undefined" ? localStorage.getItem("tenant_role") || "viewer" : "viewer";
  const canManage = myRole === "owner" || myRole === "admin";

  useEffect(() => {
    if (tenantId) loadAll();
  }, [tenantId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [m, i] = await Promise.all([
        api.get(`/api/tenants/${tenantId}/members`),
        api.get(`/api/tenants/${tenantId}/invitations`),
      ]);
      setMembers(m);
      setInvites(i);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function sendInvite() {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setError("");
    setSuccess("");
    try {
      await api.post(`/api/tenants/${tenantId}/invite`, { email: inviteEmail, role: inviteRole });
      setSuccess(`Invitation sent to ${inviteEmail}`);
      setInviteEmail("");
      await loadAll();
    } catch (e: any) {
      setError(e.message || "Failed to send invitation");
    }
    setInviting(false);
  }

  async function changeRole(userId: string, newRole: string) {
    try {
      await api.post(`/api/tenants/${tenantId}/members/${userId}/role`, { role: newRole });
      await loadAll();
    } catch (e: any) {
      setError(e.message || "Failed to change role");
    }
  }

  async function removeMember(userId: string) {
    if (!confirm("Remove this member from the workspace?")) return;
    try {
      await api.delete(`/api/tenants/${tenantId}/members/${userId}`);
      await loadAll();
    } catch (e: any) {
      setError(e.message || "Failed to remove member");
    }
  }

  async function revokeInvite(inviteId: string) {
    try {
      await api.post(`/api/tenants/${tenantId}/invitations/${inviteId}/revoke`);
      await loadAll();
    } catch (e: any) {
      setError(e.message || "Failed to revoke invitation");
    }
  }

  const roleBadge: Record<string, string> = {
    owner: "bg-purple-100 text-purple-700",
    admin: "bg-blue-100 text-blue-700",
    analyst: "bg-green-100 text-green-700",
    viewer: "bg-slate-100 text-slate-600",
  };

  const roles = ["owner", "admin", "analyst", "viewer"];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Team Management</h1>
        <p className="text-slate-500 mt-1">Manage members and invitations for this workspace</p>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm p-3 rounded-lg">{error}</div>}
      {success && <div className="bg-green-50 border border-green-200 text-green-700 text-sm p-3 rounded-lg">{success}</div>}

      {/* Invite Form */}
      {canManage && (
        <div className="bg-white border border-slate-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <UserPlus className="w-5 h-5" /> Invite Team Member
          </h2>
          <div className="flex gap-3">
            <input
              type="email"
              placeholder="Email address"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white"
            >
              {roles.map((r) => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
            </select>
            <button
              onClick={sendInvite}
              disabled={inviting || !inviteEmail.trim()}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {inviting ? "Sending..." : "Send Invite"}
            </button>
          </div>
        </div>
      )}

      {/* Members Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-100">
          <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
            <Users className="w-5 h-5" /> Members ({members.length})
          </h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading...</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Name</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Email</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Role</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Joined</th>
                {canManage && <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.user_id} className="border-b border-slate-50 hover:bg-slate-25">
                  <td className="px-4 py-3 text-sm font-medium text-slate-900">{m.full_name || "—"}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{m.email}</td>
                  <td className="px-4 py-3">
                    {canManage ? (
                      <select
                        value={m.role}
                        onChange={(e) => changeRole(m.user_id, e.target.value)}
                        className={`text-xs px-2 py-1 rounded-full font-medium border-0 cursor-pointer ${roleBadge[m.role] || ""}`}
                      >
                        {roles.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    ) : (
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${roleBadge[m.role] || ""}`}>{m.role}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-400">{new Date(m.joined_at).toLocaleDateString()}</td>
                  {canManage && (
                    <td className="px-4 py-3">
                      <button
                        onClick={() => removeMember(m.user_id)}
                        className="text-slate-400 hover:text-red-500 transition-colors"
                        title="Remove member"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pending Invitations */}
      {invites.filter((i) => i.status === "pending").length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-slate-100">
            <h2 className="text-lg font-semibold text-slate-900">Pending Invitations</h2>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Email</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Role</th>
                <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Expires</th>
                {canManage && <th className="px-4 py-3 text-xs font-medium text-slate-500 uppercase">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {invites.filter((i) => i.status === "pending").map((inv) => (
                <tr key={inv.id} className="border-b border-slate-50">
                  <td className="px-4 py-3 text-sm text-slate-600">{inv.email}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${roleBadge[inv.role] || ""}`}>{inv.role}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-400">{new Date(inv.expires_at).toLocaleDateString()}</td>
                  {canManage && (
                    <td className="px-4 py-3">
                      <button
                        onClick={() => revokeInvite(inv.id)}
                        className="text-xs text-red-500 hover:text-red-700 font-medium"
                      >
                        Revoke
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
