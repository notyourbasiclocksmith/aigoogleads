"use client";

import { useParams } from "next/navigation";

export default function WorkspaceDashboard() {
  const params = useParams();
  const tenantId = params?.tenantId as string;

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-1">Dashboard</h1>
      <p className="text-slate-500 text-sm mb-6">Workspace overview for this business</p>
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-400">
        Dashboard content renders here. All existing V1 dashboard components work with the tenant context from the workspace layout.
      </div>
    </div>
  );
}
