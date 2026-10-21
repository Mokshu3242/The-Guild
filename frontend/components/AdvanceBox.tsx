"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPost } from "@/lib/api";
import { usd } from "@/lib/format";
import { AiThinking } from "@/components/AiThinking";
import { Button, ErrorText, Skeleton } from "@/components/ui";

interface Quote {
  eligible: boolean;
  blocks: string[];
  invoice_cents: number;
  worker_share_cents: number;
  advance_cents: number;
  fee_cents: number;
  repay_cents: number;
  later_cents: number;
  pool_cents: number;
  client: string;
  client_risk: string;
  repay_days: number;
  current: { id: string; status: string; advance_cents: number; fee_cents: number; decision_note: string } | null;
}

const STATUS: Record<string, string> = {
  pending: "Waiting for an admin to approve it.",
  paid: "Paid to your PayPal. It comes back to the pool when the client pays.",
  repaid: "The client paid and the pool got its money back.",
  defaulted: "The client didn't pay in time, so it moved to what you owe the guild.",
  converted: "The client paid you directly, so it moved to what you owe the guild.",
};

/** "Get paid now": rules first (no AI), then the request. 12B. */
export function AdvanceBox({ invoiceId, onDone }: { invoiceId: string; onDone: (msg: string) => void }) {
  const { data: q, error, mutate } = useSWR<Quote>(["advance-quote", invoiceId], () =>
    apiGet<Quote>(`/advances/invoices/${invoiceId}/quote`),
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (error) return <ErrorText>{error.message}</ErrorText>;
  if (!q) return <Skeleton className="mt-4 h-24" />;

  async function ask() {
    setBusy(true);
    setErr(null);
    try {
      const r = await apiPost<{ advance_cents: number; mandate?: { status: string; set_by?: string } }>(
        `/advances/invoices/${invoiceId}/request`,
      );
      await mutate();
      onDone(
        r.mandate?.status === "paid"
          ? `Paid: ${usd(r.advance_cents)} is on its way to your PayPal, under the guild mandate set by ${r.mandate.set_by}.`
          : `Asked for ${usd(r.advance_cents)} now. An admin approves it, then it goes straight to your PayPal.`,
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't ask for the advance");
    } finally {
      setBusy(false);
    }
  }

  const cur = q.current && q.current.status !== "declined" ? q.current : null;

  return (
    <div className="mt-4 space-y-3 rounded-md bg-guild-soft/40 p-4 text-sm">
      {cur ? (
        <p>
          <span className="font-medium">
            {usd(cur.advance_cents)} paid early, {usd(cur.fee_cents)} fee.
          </span>{" "}
          {STATUS[cur.status] ?? cur.status}
        </p>
      ) : (
        <>
          <p>
            Don&apos;t wait for {q.client}. The pool can pay you part of your share now, and takes it back when the client
            pays.
          </p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
            <div>
              <dt className="text-muted">You get now</dt>
              <dd className="font-display text-xl font-semibold tabular-nums">{usd(q.advance_cents)}</dd>
            </div>
            <div>
              <dt className="text-muted">Fee to the pool</dt>
              <dd className="tabular-nums">{usd(q.fee_cents)}</dd>
            </div>
            <div>
              <dt className="text-muted">You get later</dt>
              <dd className="tabular-nums">{usd(q.later_cents)}</dd>
            </div>
            <div>
              <dt className="text-muted">Your full share</dt>
              <dd className="tabular-nums">{usd(q.worker_share_cents)}</dd>
            </div>
          </dl>
          <p className="text-muted">
            If {q.client} hasn&apos;t paid {q.repay_days} days after the advance, you owe {usd(q.repay_cents)} back from your
            next payouts. You also can&apos;t file a claim on this invoice, because you&apos;ve already been paid.
          </p>
          {q.current?.status === "declined" && (
            <p className="text-muted">
              Your last request was declined{q.current.decision_note ? `: "${q.current.decision_note}"` : "."}
            </p>
          )}
          {q.eligible ? (
            busy ? (
              <AiThinking label="Checking the rules and writing a note for the admin…" />
            ) : (
              <Button onClick={ask}>Ask for {usd(q.advance_cents)} now</Button>
            )
          ) : (
            <div>
              <p className="font-medium">Not yet, because:</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">
                {q.blocks.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      <ErrorText>{err}</ErrorText>
    </div>
  );
}
