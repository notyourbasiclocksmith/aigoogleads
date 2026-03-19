"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api } from "@/lib/api";

// Pages that don't require onboarding completion
const UNGUARDED_PATHS = [
  "/login",
  "/register",
  "/onboarding",
  "/tenant/select",
  "/tenant/create",
];

/**
 * Hook that checks onboarding status and redirects incomplete users.
 * Returns { ready, loading } — `ready` is true when the user can view the page.
 */
export function useOnboardingGuard() {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Skip guard for unprotected pages
    if (UNGUARDED_PATHS.some((p) => pathname?.startsWith(p))) {
      setReady(true);
      setLoading(false);
      return;
    }

    // No token = not logged in
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (!token) {
      setReady(true);
      setLoading(false);
      return;
    }

    let cancelled = false;

    api
      .get("/api/onboarding/status")
      .then((status: any) => {
        if (cancelled) return;
        if (!status?.complete) {
          router.replace("/onboarding");
        } else {
          setReady(true);
        }
      })
      .catch(() => {
        // If the status check fails (e.g. no tenant yet), allow through
        if (!cancelled) setReady(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  return { ready, loading };
}
