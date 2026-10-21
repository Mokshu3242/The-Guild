"use client";

import { Suspense } from "react";
import useSWR from "swr";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiGet } from "@/lib/api";
import { usd } from "@/lib/format";
import { ErrorText, Panel, Skeleton } from "@/components/ui";

type Flow = "in" | "out" | "hold" | "expect" | "owed" | "info";
interface TrailEvent {
  at: string;
  kind: string;
  title: string;
  detail: string;
  ids: [string, string][];
  amount_cents: number;
  flow: Flow;
}
interface Trail {
  invoice_id: string;
  job_id: string;
  paypal_invoice_id: string;
  amount_cents: number;
  status: string;
  client: string;
  milestone: string;
  worker: string;
  referrer: string;
  summary: { client_paid_cents: number; worker_cents: number; referrer_cents: number; pool_cents: number } | null;
  events: TrailEvent[];
}

const LABEL: Record<string, string> = {
  deposit: "Deposit",
  invoice: "Invoice",
  reminder: "Reminder",
  claim: "Claim",
  direct: "Paid directly",
  payment: "Client paid",
  split: "Split",
  payout: "Payout",
  advance: "Advance",
  debt: "Paid back",
};
const DOT: Record<Flow, string> = {
  in: "bg-guild",
  out: "bg-seal",
  hold: "bg-seal-bright",
  expect: "bg-ink",
  owed: "bg-alert",
  info: "bg-line",
};

function amount(e: TrailEvent) {
  if (!e.amount_cents) return null;
  const v = usd(e.amount_cents);
  if (e.flow === "in") return <span className="font-medium text-guild">+{v}</span>;
  if (e.flow === "out") return <span className="font-medium">−{v}</span>;
  if (e.flow === "owed") return <span className="font-medium text-alert">{v} owed</span>;
  return <span className="text-muted">{v}</span>;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <MoneyTrail />
    </Suspense>
  );
}

function MoneyTrail() {
  const id = useSearchParams().get("id") ?? "";
  const { data: t, error } = useSWR<Trail>(id ? ["trail", id] : null, () => apiGet<Trail>(`/invoices/${id}/trail`));

  if (!id) return <ErrorText>This link is missing the invoice.</ErrorText>;
  if (error) return <ErrorText>{error.message}</ErrorText>;
  if (!t) return <Skeleton className="h-64" />;
  const s = t.summary;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link href={`/jobs/view/?id=${t.job_id}`} className="text-sm text-muted hover:text-ink">
          Back to the job
        </Link>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">Money trail</h1>
        <p className="mt-1 text-muted">
          Where every dollar of this invoice went, in order, with the IDs PayPal gave each step.
        </p>
      </div>

      <section className="rounded-2xl bg-guild-deep p-6 text-white sm:p-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm text-seal-bright">{t.client}</p>
            <p className="mt-1 break-words font-medium">{t.milestone}</p>
            <p className="mt-1 text-xs text-white/60">
              {t.worker ? `Done by ${t.worker}` : "No worker yet"}
              {t.referrer ? ` · brought in by ${t.referrer}` : ""} · {t.status}
            </p>
          </div>
          <p className="font-display text-4xl font-bold tabular-nums">{usd(t.amount_cents)}</p>
        </div>
        {s && (
          <dl className="mt-6 grid grid-cols-3 gap-3 border-t border-white/15 pt-5 text-sm">
            <div>
              <dt className="text-white/60">Worker got</dt>
              <dd className="mt-0.5 font-display text-xl font-semibold tabular-nums">{usd(s.worker_cents)}</dd>
            </div>
            <div>
              <dt className="text-white/60">Referrer got</dt>
              <dd className="mt-0.5 font-display text-xl font-semibold tabular-nums">{usd(s.referrer_cents)}</dd>
            </div>
            <div>
              <dt className="text-white/60">Pool got</dt>
              <dd className="mt-0.5 font-display text-xl font-semibold tabular-nums">{usd(s.pool_cents)}</dd>
            </div>
          </dl>
        )}
      </section>

      <Panel title="Step by step">
        {t.events.length === 0 && <p className="text-sm text-muted">Nothing has happened to this invoice yet.</p>}
        <ol>
          {t.events.map((e, i) => (
            <li key={i} className="relative flex gap-4 pb-6 last:pb-0">
              {i < t.events.length - 1 && (
                <span className="absolute left-[5px] top-4 h-full w-px bg-line" aria-hidden="true" />
              )}
              <span className={`relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full ${DOT[e.flow]}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                  <p className="min-w-0 break-words font-medium">{e.title}</p>
                  <span className="tabular-nums">{amount(e)}</span>
                </div>
                <p className="text-xs text-muted">
                  {LABEL[e.kind] ?? e.kind} · {when(e.at)}
                </p>
                {e.detail && <p className="mt-1 text-sm text-muted">{e.detail}</p>}
                {e.ids.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {e.ids.map(([label, value]) => (
                      <span key={label + value} className="max-w-full break-all rounded bg-paper px-2 py-0.5 text-xs">
                        <span className="text-muted">{label} </span>
                        <code className="font-mono text-ink">{value}</code>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </Panel>

      <p className="pb-6 text-xs text-muted">
        Built from the guild&apos;s records and the split the payment code logged when it ran. No AI.{" "}
        <Link href={`/jobs/evidence/?id=${t.job_id}`} className="underline underline-offset-2 hover:text-ink">
          Full evidence pack for this job
        </Link>
      </p>
    </div>
  );
}
