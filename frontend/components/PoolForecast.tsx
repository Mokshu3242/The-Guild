"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPost } from "@/lib/api";
import { timeAgo, usd } from "@/lib/format";
import { AiThinking } from "./AiThinking";
import { Button, ErrorText, Panel } from "./ui";

export interface Forecast {
  verdict: "healthy" | "watch" | "underfunded";
  message: string;
  written_by: "ai" | "template";
  balance_cents: number;
  monthly_income_cents: number;
  monthly_payouts_cents: number;
  typical_claim_cents: number;
  waiting_claims: number;
  claims_covered: number | null;
  current_pool_pct: number;
  suggested_pool_pct: number;
  created_at: string;
}

const BADGE: Record<Forecast["verdict"], { label: string; cls: string }> = {
  healthy: { label: "Healthy", cls: "bg-guild-soft text-guild" },
  watch: { label: "Keep an eye on it", cls: "bg-seal-soft text-seal" },
  underfunded: { label: "Underfunded", cls: "bg-alert-soft text-alert" },
};

export function PoolForecast({ isAdmin }: { isAdmin: boolean }) {
  const { data, mutate, error } = useSWR<{ forecast: Forecast | null }>("pool-forecast", () =>
    apiGet<{ forecast: Forecast | null }>("/pool/forecast"),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const f = await apiPost<Forecast>("/pool/forecast");
      await mutate({ forecast: f }, { revalidate: false });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't check the pool");
    } finally {
      setBusy(false);
    }
  }

  const f = data?.forecast ?? null;
  const b = f ? BADGE[f.verdict] ?? BADGE.healthy : null;

  return (
    <Panel
      title="Pool health"
      action={
        isAdmin && f && !busy ? (
          <Button variant="quiet" onClick={run}>Check again</Button>
        ) : undefined
      }
    >
      {error && <ErrorText>{error.message}</ErrorText>}

      {!f && !busy && !error && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-prose text-sm text-muted">
            See how many more claims the pool can cover, and whether money coming in keeps up with money going out.
          </p>
          {isAdmin ? (
            <Button className="shrink-0" onClick={run}>Check pool health</Button>
          ) : (
            <p className="text-sm text-muted">An admin can run this check.</p>
          )}
        </div>
      )}

      {busy && <AiThinking label="Adding up money in, money out, and waiting claims…" />}

      {f && b && !busy && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-sm font-medium ${b.cls}`}>{b.label}</span>
            <span className="text-sm text-muted">
              {f.claims_covered === null
                ? "No claims yet to size against"
                : `Covers about ${f.claims_covered} more claim${f.claims_covered === 1 ? "" : "s"}`}
              {f.waiting_claims > 0 && `, after ${f.waiting_claims} waiting`}
            </span>
          </div>

          <p className="mt-3 text-sm leading-relaxed">{f.message}</p>

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line pt-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted">In per month</dt>
              <dd className="font-medium tabular-nums text-guild">{usd(f.monthly_income_cents)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Out per month</dt>
              <dd className="font-medium tabular-nums text-alert">{usd(f.monthly_payouts_cents)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Typical claim</dt>
              <dd className="font-medium tabular-nums">{usd(f.typical_claim_cents)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Pool cut</dt>
              <dd className="font-medium tabular-nums">
                {f.current_pool_pct}%
                {f.suggested_pool_pct !== f.current_pool_pct && (
                  <span className="ml-1 text-seal">suggest {f.suggested_pool_pct}%</span>
                )}
              </dd>
            </div>
          </dl>

          <p className="mt-3 text-xs text-muted">
            Checked {timeAgo(f.created_at)}, based on the last 90 days
            {f.written_by === "template" ? ". Written without AI." : "."}
          </p>
        </>
      )}
      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}