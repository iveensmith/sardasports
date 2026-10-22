"use client";

/**
 * Whether the person looking is a premium member, and the predictions the public pages hide.
 *
 * The public pages are built once and shared (and cached), so they carry the same thing for
 * everyone: 15 predictions a day in full, and the rest with the prediction left out by the engine.
 * Nothing about who is looking is known when they are built. This provider asks the site who the
 * visitor is, in the browser, after the page has loaded (the way the header does), and for a
 * premium member it fetches the missing rows through an authenticated route and keeps them here.
 * Everyone else never receives them: the hidden data is not in the page to be found.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/clientApi";
import type { BoardRow } from "@/lib/board";
import type { Session } from "@/lib/session";

interface PremiumState {
  /** True or false once known; null while the page is still asking. */
  premium: boolean | null;
  /** Full rows fetched for a premium member, by match id. */
  rows: Record<number, BoardRow>;
  /** Ask for the full rows of these matches (does nothing unless the viewer is premium). */
  unlock: (ids: number[]) => void;
}

const PremiumContext = createContext<PremiumState>({
  premium: null,
  rows: {},
  unlock: () => {},
});

// The route allows a few hundred ids at a time; a card is rarely more than that.
const CHUNK = 200;

export function PremiumProvider({ children }: { children: ReactNode }) {
  const [premium, setPremium] = useState<boolean | null>(null);
  const [rows, setRows] = useState<Record<number, BoardRow>>({});
  const asked = useRef<Set<number>>(new Set());

  useEffect(() => {
    let live = true;
    api<Session>("/api/auth/me").then((result) => {
      if (live) setPremium(Boolean(result.ok && result.data?.entitlement?.premium));
    });
    return () => {
      live = false;
    };
  }, []);

  const unlock = useCallback(
    (ids: number[]) => {
      if (!premium) return;
      const fresh = ids.filter((id) => !asked.current.has(id));
      for (let start = 0; start < fresh.length; start += CHUNK) {
        const chunk = fresh.slice(start, start + CHUNK);
        chunk.forEach((id) => asked.current.add(id));
        api<{ rows: BoardRow[] }>(
          `/api/engine/premium/rows?ids=${chunk.join(",")}`,
        ).then((result) => {
          if (result.ok && result.data) {
            const got = result.data.rows;
            setRows((previous) => {
              const next = { ...previous };
              for (const row of got) next[row.match_id] = row;
              return next;
            });
          } else {
            // Try again next time something asks.
            chunk.forEach((id) => asked.current.delete(id));
          }
        });
      }
    },
    [premium],
  );

  const value = useMemo(() => ({ premium, rows, unlock }), [premium, rows, unlock]);
  return (
    <PremiumContext.Provider value={value}>{children}</PremiumContext.Provider>
  );
}

export function usePremium(): PremiumState {
  return useContext(PremiumContext);
}
