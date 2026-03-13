"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, Loader2 } from "lucide-react";

interface CSVExportButtonProps {
  entityType: string;
  days?: number;
  label?: string;
  variant?: "default" | "ghost" | "outline" | "secondary";
  size?: "default" | "sm" | "lg" | "icon";
  className?: string;
}

export function CSVExportButton({
  entityType,
  days = 30,
  label = "Export CSV",
  variant = "outline",
  size = "sm",
  className = "",
}: CSVExportButtonProps) {
  const [loading, setLoading] = useState(false);

  async function handleExport() {
    setLoading(true);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const res = await fetch(`/api/reports/export/csv?entity_type=${entityType}&days=${days}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${entityType}_${days}d.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error("CSV export error:", e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleExport}
      disabled={loading}
      className={`text-[13px] ${className}`}
    >
      {loading ? (
        <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Exporting...</>
      ) : (
        <><Download className="w-3.5 h-3.5 mr-1.5" /> {label}</>
      )}
    </Button>
  );
}
