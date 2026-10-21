"use client";

import useSWR from "swr";
import { useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import { plural, timeAgo, usd } from "@/lib/format";
import { useMe } from "@/lib/useMe";
import { Button, ErrorText, Notice, PageHeader, Panel, StatusPill, buttonCls } from "@/components/ui";
import { PoolBalance } from "@/components/PoolBalance";
import { PoolForecast } from "@/components/PoolForecast";
import { RecoveryCard } from "@/components/RecoveryCard";
import { AdvancesPanel } from "@/components/AdvancesPanel";

interface Pool { pool_balance_cents: number; monthly_fee_cents: number; active_subscribers: number; plan_ready: boolean }
interface Sub { status: string; approve_url: string }
interface Tx { id: string; amount: number; direction: string; source: string; created_at: string }

const SOURCE: Record<string, string> = {
  referral_slice: "Share of a paid invoice",
  subscription: "Monthly member fee",
  recovery: "Recovered when a late client paid",
  claim_payout: "Covered a member's unpaid invoice",
  founding: "Founding members' starting contribution",
  set_off: "Paid back from a member's payout",
  referral_fronted: "Paid a referrer early (client paid a member directly)",
  advance_paid: "Paid a member early (advance)",
  advance_repaid: "Advance paid back when the client paid",
  advance_fee: "Fee on an advance",
};

export default function PoolPage() {
  const { me } = useMe();
  const { data: pool, mutate: refreshPool } = useSWR<Pool>("pool", () => apiGet<Pool>("/pool"), {
    refreshInterval: 5000,
  });
  const { data: txs } = useSWR<Tx[]>("pool-tx", () => apiGet<Tx[]>("/pool/transactions"), {
    refreshInterval: 5000,
  });
  const { data: sub, mutate: refreshSub } = useSWR<Sub | null>("my-sub", () =>
    apiGet<Sub>("/pool/subscription").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(null); setNotice(null);
    try { await fn(); } catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong"); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Safety pool"
        description="Shared money that covers members when a client never pays. It grows from a slice of every invoice and a small monthly fee."
      />

      <section className="rounded-2xl bg-guild-deep p-6 text-white sm:p-8">
        <p className="text-sm text-seal-bright">In the pool now</p>
        <p className="mt-1 font-display text-5xl font-bold tabular-nums sm:text-6xl">
          <PoolBalance cents={pool?.pool_balance_cents} tagClassName="text-seal-bright" />
        </p>
        <p className="mt-3 text-sm text-white/70">
          {pool?.active_subscribers ?? 0} {plural(pool?.active_subscribers ?? 0, "member contributes", "members contribute")}{" "}
          {usd(pool?.monthly_fee_cents ?? 0)} a month.
        </p>
      </section>

      <PoolForecast isAdmin={me?.role === "admin"} />

      <AdvancesPanel isAdmin={me?.role === "admin"} />

      <RecoveryCard isAdmin={me?.role === "admin"} />

      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
      <Panel title="Your monthly contribution">
        {me?.role === "admin" && pool && !pool.plan_ready ? (
          <Button disabled={busy} onClick={() => run(async () => { await apiPost("/pool/plan"); await refreshPool(); })}>
            Set up the monthly plan in PayPal
          </Button>
        ) : sub?.status === "active" ? (
          <p className="flex items-center gap-2 text-sm">You&apos;re contributing <StatusPill status="active" /></p>
        ) : sub?.status === "pending" ? (
          <div className="flex flex-wrap gap-2">
            <a href={sub.approve_url} target="_blank" rel="noreferrer" className={buttonCls()}>Approve in PayPal</a>
            <Button variant="quiet" disabled={busy} onClick={() => run(async () => {
              const r = await apiPost<{ subscription_status: string }>("/pool/subscription/sync");
              setNotice(`Status: ${r.subscription_status}`);
              await refreshSub(); await refreshPool();
            })}>I've approved it</Button>
          </div>
        ) : (
          <Button disabled={busy || !pool?.plan_ready} onClick={() => run(async () => {
            const s = await apiPost<Sub>("/pool/subscribe");
            await refreshSub();
            window.open(s.approve_url, "_blank");
          })}>
            Contribute {usd(pool?.monthly_fee_cents ?? 0)} a month
          </Button>
        )}
        <ErrorText>{err}</ErrorText>
        <Notice>{notice}</Notice>
      </Panel>

      <Panel title="Pool history">
        {(txs ?? []).length === 0 && <p className="text-sm text-muted">No money in or out yet.</p>}
        <ul className="divide-y divide-line">
          {(txs ?? []).slice(0, 20).map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-4 py-3 text-sm first:pt-0 last:pb-0">
              <div className="min-w-0">
                <p>{SOURCE[t.source] ?? t.source}</p>
                <p className="text-xs text-muted">{timeAgo(t.created_at)}</p>
              </div>
              <span className={`shrink-0 font-medium tabular-nums ${t.direction === "in" ? "text-guild" : "text-alert"}`}>
                {t.direction === "in" ? "+" : "−"}{usd(t.amount)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
      </div>
    </div>
  );
}
