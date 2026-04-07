"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Client component that checks for an auth token and redirects
 * logged-in users to the dashboard. Renders nothing visible —
 * the marketing page content shows immediately for SEO/crawlers
 * while this runs in the background for authenticated users.
 */
export default function AuthRedirect() {
  const router = useRouter();
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      router.replace("/dashboard");
    }
  }, [router]);
  return null;
}
