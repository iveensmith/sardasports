"use client";

/**
 * What stands where a locked match's prediction would be.
 *
 * Everyone is sent the lock card (the engine withheld the prediction, so there is nothing else to
 * send). A premium member's browser then asks for the real thing through an authenticated route and
 * swaps it in, using the same body the open predictions use.
 */

import { useEffect, useState } from "react";
import { FootballBody } from "@/components/match/FootballBody";
import { StatsComparison } from "@/components/match/StatsComparison";
import { LockCard } from "@/components/premium/LockCard";
import { usePremium } from "@/components/premium/PremiumProvider";
import { api } from "@/lib/clientApi";
import type { FootballPrediction } from "@/lib/types";

type Loaded = FootballPrediction | "failed" | null;

export function MemberMatchView({
  matchId,
  view,
}: {
  matchId: number;
  view: "tips" | "stats";
}) {
  const { premium } = usePremium();
  const [data, setData] = useState<Loaded>(null);

  useEffect(() => {
    if (premium !== true) return;
    let live = true;
    api<FootballPrediction & { locked?: boolean }>(
      `/api/engine/predict/${matchId}`,
    ).then((result) => {
      if (!live) return;
      setData(result.ok && result.data && !result.data.locked ? result.data : "failed");
    });
    return () => {
      live = false;
    };
  }, [premium, matchId]);

  if (premium === true) {
    if (data === "failed") {
      return (
        <LockCard
          title="Could not load this prediction"
          note="Please refresh the page. If it keeps happening, sign out and back in."
        />
      );
    }
    if (data === null) {
      return (
        <div
          aria-busy="true"
          className="h-56 animate-pulse rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]"
        />
      );
    }
    return view === "tips" ? (
      <FootballBody p={data} />
    ) : (
      <StatsComparison
        expectedGoalsHome={data.expected_goals_home}
        expectedGoalsAway={data.expected_goals_away}
        score={data.match_score}
        actual={data.actual_stats}
      />
    );
  }
  return <LockCard />;
}
