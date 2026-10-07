"use client";

import useSWR from "swr";
import { useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import { plural, timeAgo, usd } from "@/lib/format";
import { useMe } from "@/lib/useMe";
import { Button, ErrorText, Notice, Panel, StatusPill } from "@/components/ui";


interface Pool { pool_balance_cents: number; monthly_fee_cents: number; active_subscribers: number; plan_ready: boolean }
interface Sub { status: string; approve_url: string }
interface Tx { id: string; amount: number; direction: string; source: string; created_at: string }

const SOURCE: Record<string, string> = {
  referral_slice: "Share of a paid invoice",
  subscription: "Monthly member fee",
  recovery: "Recovered when a late client paid",
  claim_payout: "Covered a member's unpaid invoice",
  founding: "Founding members' starting contribution",
};

export default function PoolPage() {
  const { me } = useMe();
  const { data: pool, mutate: refreshPool } = useSWR<Pool>("pool", () => apiGet<Pool>("/pool"));
  const { data: txs } = useSWR<Tx[]>("pool-tx", () => apiGet<Tx[]>("/pool/transactions"));
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
      <div>
        <h1 className="font-display text-3xl font-bold">Safety pool</h1>
        <p className="mt-2 max-w-prose text-muted">
          Shared money that covers members when a client never pays. It grows from a slice of every invoice and a small monthly fee.
        </p>
      </div>

      <section className="rounded-lg bg-seal-soft p-6 ring-1 ring-seal/20">
        <p className="font-display text-5xl font-bold tabular-nums">{usd(pool?.pool_balance_cents ?? 0)}</p>

        <p className="mt-2 text-sm text-muted">
          {pool?.active_subscribers ?? 0} {plural(pool?.active_subscribers ?? 0, "member contributes", "members contribute")}{" "}
          {usd(pool?.monthly_fee_cents ?? 0)} a month.
        </p>
      </section>

      <Panel title="Your membership">
        {me?.role === "admin" && pool && !pool.plan_ready ? (
          <Button disabled={busy} onClick={() => run(async () => { await apiPost("/pool/plan"); await refreshPool(); })}>
            Set up the monthly plan in PayPal
          </Button>
        ) : sub?.status === "active" ? (
          <p className="text-sm">You're contributing <StatusPill status="active" /></p>
        ) : sub?.status === "pending" ? (
          <div className="flex flex-wrap gap-2">
            <a href={sub.approve_url} target="_blank" rel="noreferrer" className="rounded-md bg-guild px-3.5 py-2 text-sm font-medium text-white">Approve in PayPal</a>
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
            <li key={t.id} className="flex items-center justify-between py-3 text-sm">
              <div>
                <p>{SOURCE[t.source] ?? t.source}</p>
                <p className="text-xs text-muted">{timeAgo(t.created_at)}</p>
              </div>
              <span className={`font-medium tabular-nums ${t.direction === "in" ? "text-guild" : "text-alert"}`}>
                {t.direction === "in" ? "+" : "−"}{usd(t.amount)}
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}