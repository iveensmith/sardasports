"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/clientApi";

/**
 * Load one admin endpoint (through the site's allow-listed proxy) and reload on demand.
 *
 * Returns `{ data, error, loading, reload }`. Every admin screen is a list that changes when an
 * action succeeds, so "do the action, then `reload()`" is the whole pattern.
 */
export function useAdminData<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    const result = await api<T>(`/api/engine/${path}`);
    if (result.ok) {
      setData(result.data);
      setError(null);
    } else {
      setError(result.error?.message ?? "Could not load this.");
    }
    setLoading(false);
  }, [path]);

  useEffect(() => {
    let alive = true;
    api<T>(`/api/engine/${path}`).then((result) => {
      if (!alive) return;
      if (result.ok) {
        setData(result.data);
        setError(null);
      } else {
        setError(result.error?.message ?? "Could not load this.");
      }
      setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [path]);

  return { data, error, loading, reload };
}
