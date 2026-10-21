"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import { usd } from "@/lib/format";
import { Button, ErrorText, Notice, Panel, inputCls } from "@/components/ui";

interface Covered {
  claim_id: string;
  job_id: string;
  client: string;
  milestone: string;
  worker: string;
  covered_cents: number;
  recovered_cents: number;
  invoice_cents: number;
  invoice_status: string;
  covered_at: string;
  recovered_at: string | null;
  reminders_sent: number;
  state: "chasing" | "partial" | "whole" | "member_owes";
}
interface Debt {
  id: string;
  member: string;
  kind: string;
  amount_cents: number;
  repaid_cents: number;
  status: string;
  note: string;
  created_at: string;
}
interface Report {
  id: string;
  member: string;
  is_me: boolean;
  client: string;
  milestone: string;
  job_id: string;
  amount_cents: number;
  method: string;
  note: string;
  created_at: string;
  would_owe: { referrer_cents: number; pool_cents: number; claim_cents: number; advance_cents: number; owed_cents: number; has_referrer: boolean };
}
interface Recovery {
  covered_cents: number;
  recovered_cents: number;
  outstanding_cents: number;
  covered: Covered[];
  debts: Debt[];
  reports: Report[];
}

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const daysSince = (iso: string) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));
const METHOD: Record<string, string> = { bank: "bank transfer", cash: "cash", other: "another way" };

function Bar({ part, whole }: { part: number; whole: number }) {
  const pct = whole ? Math.min(100, Math.round((part / whole) * 100)) : 0;
  return (
    <div className="h-2 overflow-hidden rounded-full bg-paper" aria-label={`${pct}% back in the pool`}>
      <div className="h-full rounded-full bg-guild transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

function stateLine(c: Covered) {
  if (c.state === "whole") return `Paid back in full${c.recovered_at ? ` on ${day(c.recovered_at)}` : ""}. The pool is whole again.`;
  if (c.state === "member_owes") return `The client paid ${c.worker} directly. ${c.worker} pays the pool back from their next payouts.`;
  if (c.state === "partial") return `${usd(c.recovered_cents)} back so far. Still chasing the rest.`;
  return `Still chasing. ${c.reminders_sent} of 3 reminders sent, ${daysSince(c.covered_at)} days since the pool covered it.`;
}

export function RecoveryCard({ isAdmin }: { isAdmin: boolean }) {
  const { data, mutate } = useSWR<Recovery>("recovery", () => apiGet<Recovery>("/recovery"), { refreshInterval: 15000 });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  if (!data) return null;
  const openDebts = data.debts.filter((d) => d.status === "open");
  if (data.covered.length === 0 && data.debts.length === 0 && data.reports.length === 0) return null;

  async function act(key: string, path: string, body: object, done: string) {
    setBusy(key);
    setErr(null);
    setNotice(null);
    try {
      await apiPost(path, body);
      setNotice(done);
      await mutate();
      globalMutate("pool");
      globalMutate("pool-tx");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel title="Getting the money back">
      <p className="text-sm text-muted">
        When the pool covers an unpaid invoice, the guild takes over the debt. Reminders keep going, and when the client
        pays, the pool is refilled before anyone else.
      </p>

      {data.covered.length > 0 && (
        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span>
              <span className="font-semibold tabular-nums">{usd(data.recovered_cents)}</span>
              <span className="text-muted"> of {usd(data.covered_cents)} covered is back in the pool</span>
            </span>
            {data.outstanding_cents > 0 && (
              <span className="text-muted tabular-nums">{usd(data.outstanding_cents)} still out</span>
            )}
          </div>
          <div className="mt-2">
            <Bar part={data.recovered_cents} whole={data.covered_cents} />
          </div>

          <ul className="mt-4 divide-y divide-line">
            {data.covered.map((c) => (
              <li key={c.claim_id} className="py-3 text-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <Link href={`/jobs/view/?id=${c.job_id}`} className="font-medium hover:underline">
                    {c.client} · {c.milestone}
                  </Link>
                  <span className="tabular-nums text-muted">
                    {usd(c.recovered_cents)} / {usd(c.covered_cents)}
                  </span>
                </div>
                <p className={`mt-0.5 ${c.state === "whole" ? "text-guild" : "text-muted"}`}>{stateLine(c)}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.reports.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <h3 className="font-medium">Paid outside PayPal ({data.reports.length} to check)</h3>
          <ul className="mt-2 space-y-3">
            {data.reports.map((r) => (
              <li key={r.id} className="rounded-lg border border-line p-4 text-sm">
                <p>
                  <span className="font-medium">{r.member}</span> says {r.client} paid {usd(r.amount_cents)} by{" "}
                  {METHOD[r.method] ?? r.method} for &quot;{r.milestone}&quot;.
                </p>
                {r.note && <p className="mt-1 text-muted">&quot;{r.note}&quot;</p>}
                <p className="mt-2 text-muted">
                  If you settle it, {r.member} owes the guild {usd(r.would_owe.owed_cents)}
                  {": "}
                  {[
                    r.would_owe.has_referrer && `${usd(r.would_owe.referrer_cents)} referral fee (the pool pays it now)`,
                    `${usd(r.would_owe.pool_cents)} pool slice`,
                    r.would_owe.claim_cents > 0 && `${usd(r.would_owe.claim_cents)} the pool already covered`,
                    r.would_owe.advance_cents > 0 && `${usd(r.would_owe.advance_cents)} paid early, with its fee`,
                  ]
                    .filter(Boolean)
                    .join(", ")}
                  . It comes off their next payouts.
                </p>
                {r.is_me ? (
                  <p className="mt-2 text-muted">This is your own report, so another admin has to settle it.</p>
                ) : (
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                    <Button
                      disabled={!!busy}
                      onClick={() =>
                        act(`s-${r.id}`, `/recovery/direct/${r.id}/settle`, {}, `Settled. The invoice is closed and ${r.member} owes ${usd(r.would_owe.owed_cents)}.`)
                      }
                    >
                      {busy === `s-${r.id}` ? "Settling…" : "Settle it"}
                    </Button>
                    <input
                      value={notes[r.id] ?? ""}
                      onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })}
                      maxLength={500}
                      placeholder="Why not? (optional)"
                      className={inputCls}
                    />
                    <Button
                      variant="quiet"
                      disabled={!!busy}
                      onClick={() => act(`r-${r.id}`, `/recovery/direct/${r.id}/reject`, { note: notes[r.id] ?? "" }, "Report rejected.")}
                      className="shrink-0"
                    >
                      Reject
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.debts.length > 0 && (
        <div className="mt-5 border-t border-line pt-4">
          <h3 className="font-medium">{isAdmin ? "Owed to the guild" : "What you owe the guild"}</h3>
          {!isAdmin && openDebts.length > 0 && (
            <p className="mt-1 text-sm text-muted">This is taken from your next payouts. You don&apos;t need to do anything.</p>
          )}
          <ul className="mt-2 divide-y divide-line">
            {data.debts.map((d) => (
              <li key={d.id} className="py-3 text-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span>
                    {isAdmin && <span className="font-medium">{d.member} · </span>}
                    {d.note || (d.kind === "advance" ? "Advance" : "Direct payment")}
                  </span>
                  <span className="tabular-nums text-muted">
                    {usd(d.repaid_cents)} / {usd(d.amount_cents)}{" "}
                    {d.status === "repaid" ? "· repaid" : d.status === "written_off" ? "· written off" : ""}
                  </span>
                </div>
                <div className="mt-2">
                  <Bar part={d.repaid_cents} whole={d.amount_cents} />
                </div>
                {isAdmin && d.status === "open" && (
                  <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                    <input
                      value={notes[d.id] ?? ""}
                      onChange={(e) => setNotes({ ...notes, [d.id]: e.target.value })}
                      maxLength={500}
                      placeholder="Reason to write it off"
                      className={inputCls}
                    />
                    <Button
                      variant="quiet"
                      disabled={!!busy || (notes[d.id] ?? "").trim().length < 5}
                      onClick={() => act(`w-${d.id}`, `/recovery/debts/${d.id}/write-off`, { note: notes[d.id] ?? "" }, "Written off.")}
                      className="shrink-0"
                    >
                      Write off
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ErrorText>{err}</ErrorText>
      {notice && <Notice>{notice}</Notice>}
    </Panel>
  );
}
