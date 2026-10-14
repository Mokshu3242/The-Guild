"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { usd } from "@/lib/format";
import { AiThinking } from "./AiThinking";
import { Button, ErrorText } from "./ui";

interface Advice {
  verdict: "below_market" | "well_positioned" | "above_market" | "not_enough_data";
  message: string;
  my_rate_cents: number;
  median_cents: number | null;
  peer_count: number;
  basis: "skills" | "guild";
}

const BADGE: Record<Advice["verdict"], { cls: string; label: string }> = {
  below_market: { cls: "bg-seal-soft text-seal", label: "Below the guild" },
  well_positioned: { cls: "bg-guild-soft text-guild", label: "Fair rate" },
  above_market: { cls: "bg-paper text-ink", label: "Above the guild" },
  not_enough_data: { cls: "bg-paper text-muted", label: "Not enough peers yet" },
};

// savedRateCents: the rate stored on the server, not the input box.
// When it changes, the old advice is cleared so it never goes stale.
export function RateAdvisor({ savedRateCents }: { savedRateCents: number }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [forRate, setForRate] = useState<number | null>(null);

  const current = advice && forRate === savedRateCents ? advice : null;

  async function check() {
    setBusy(true);
    setErr(null);
    try {
      const a = await apiPost<Advice>("/me/rate-advice");
      setAdvice(a);
      setForRate(savedRateCents);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't check your rate");
    } finally {
      setBusy(false);
    }
  }

  const badge = current ? BADGE[current.verdict] : null;

  return (
    <div className="rounded-lg border border-line bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">Is my rate fair?</p>
        {!busy && (
          <Button variant="quiet" onClick={check}>
            {current ? "Check again" : "Compare with the guild"}
          </Button>
        )}
      </div>

      {busy && (
        <div className="mt-3">
          <AiThinking label="Comparing your rate with members who share your skills…" />
        </div>
      )}

      {!busy && current && badge && (
        <div className="mt-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded px-2 py-0.5 text-xs font-semibold ${badge.cls}`}>
              {badge.label}
            </span>
            {current.median_cents !== null && (
              <span className="text-xs text-muted">
                Typical {current.basis === "skills" ? "for your skills" : "in the guild"}:{" "}
{usd(current.median_cents)}/hr, from {current.peer_count} members
              </span>
            )}
          </div>
          <p className="mt-2 text-sm">{current.message}</p>
        </div>
      )}
      <ErrorText>{err}</ErrorText>
    </div>
  );
}