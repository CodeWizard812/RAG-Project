// frontend/hooks/useKeepAlive.ts
//
// Pings /api/health/ every 10 minutes while the user is authenticated.
// Prevents Render's free tier from spinning down during an active session.
// Runs only in the browser — SSR-safe.

import { useEffect } from "react";
import { fetchHealth, getToken } from "@/lib/api";

const PING_INTERVAL_MS = 10 * 60 * 1000;  // 10 minutes

export function useKeepAlive(): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!getToken()) return;

    // Ping immediately on mount so we know the server is warm
    fetchHealth().catch(() => {
      // Ignore errors — server may still be waking up
    });

    const interval = setInterval(() => {
      if (!getToken()) return;   // stop pinging if user logged out
      fetchHealth().catch(() => {});
    }, PING_INTERVAL_MS);

    return () => clearInterval(interval);
  }, []);
}