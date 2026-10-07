"use client";

import useSWR from "swr";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { usd } from "@/lib/format";
import { useMe } from "@/lib/useMe";
import { useGuild, useMembers } from "@/lib/useGuild";
import type { Job } from "@/components/JobsGrid";
import { SplitBar } from "@/components/SplitBar";
import { Button, ErrorText, Notice, Panel, StatusPill, inputCls } from "@/components/ui";

interface Milestone { id: string; title: string; scope: string; amount: number; status: string }
interface Invoice { id: string; milestone_id: string; status: string; pay_url: string; amount: number }
interface MatchPick { top_name: string; backup_name: string | null; reason: string; assigned: boolean }
interface SyncResult { status: string; paypal_status?: string; worker_cents?: number; recovered_cents?: number }

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const { me } = useMe();
  const { data: guild } = useGuild(me?.guild_id);
  const { data: members } = useMembers(me?.guild_id);
  const { data: job, mutate: refreshJob } = useSWR<Job>(["job", id], () => apiGet<Job>(`/jobs/${id}`));
  const { data: milestones, mutate: refreshMs } = useSWR<Milestone[]>(["milestones", id], () => apiGet<Milestone[]>(`/jobs/${id}/milestones`));
  const { data: invoices, mutate: refreshInv } = useSWR<Invoice[]>("invoices", () => apiGet<Invoice[]>("/invoices"));

  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pick, setPick] = useState<MatchPick | null>(null);
  const [claimFor, setClaimFor] = useState<string | null>(null);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key); setErr(null); setNotice(null);
    try { await fn(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong"); }
    finally { setBusy(null); }
  }
  const refreshAll = () => { refreshJob(); refreshMs(); refreshInv(); };

  if (!job || !me) return <p className="text-muted">Loading job…</p>;

  const nameOf = (mid: string | null) => members?.find((m) => m.id === mid)?.name ?? "Not assigned";
  const isOwner = job.referrer_id === me.id || me.role === "admin";
  const isWorker = job.worker_id === me.id;
  const hasReferrer = !!job.worker_id && job.referrer_id !== job.worker_id;
  const invoiceFor = (msId: string) => invoices?.find((i) => i.milestone_id === msId);

  const match = (assign: boolean) => run(assign ? "assign" : "suggest", async () => {
    const r = await apiPost<MatchPick>(`/jobs/${id}/match`, { auto_assign: assign });
    setPick(r);
    if (assign) refreshJob();
  });

  const addMilestone = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const d = Object.fromEntries(new FormData(form)) as Record<string, string>;
    run("milestone", async () => {
      await apiPost(`/jobs/${id}/milestones`, {
        title: d.title, scope: d.scope, amount_cents: Math.round(parseFloat(d.amount) * 100),
      });
      form.reset();
      refreshMs();
    });
  };

  const sendInvoice = (msId: string) => run(`send-${msId}`, async () => {
    await apiPost(`/invoices/milestones/${msId}/send`);
    setNotice("Invoice sent to the client through PayPal.");
    refreshAll();
  });

  const checkPayment = (invId: string) => run(`sync-${invId}`, async () => {
    const r = await apiPost<SyncResult>(`/invoices/${invId}/sync`);
    if (r.status === "processed") {
      setNotice(`Paid. ${usd(r.worker_cents ?? 0)} sent to the worker${r.recovered_cents ? `, and ${usd(r.recovered_cents)} returned to the pool` : ""}.`);
    } else if (r.status === "already_paid") {
      setNotice("Already paid and split.");
    } else {
      setNotice(`Not paid yet. PayPal says the invoice is ${r.paypal_status?.toLowerCase() ?? "waiting"}.`);
    }
    refreshAll();
  });

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-3xl font-bold">{job.client_name}</h1>
          <StatusPill status={job.status} />
        </div>
        <p className="mt-1 text-sm text-muted">Posted by {nameOf(job.referrer_id)}. Worker: {nameOf(job.worker_id)}.</p>
        {job.status === "disputed" && me.role === "admin" && (
          <a href="/claims" className="mt-2 inline-block text-sm text-alert hover:underline">
            A claim is waiting for your review
          </a>
        )}
      </div>

      <Panel title="What the client needs">
        <p className="max-w-prose leading-relaxed">{job.description}</p>
        {job.match_reason && (
          <p className="mt-4 rounded-md bg-guild-soft px-3 py-2 text-sm text-guild">
            <span className="font-medium">Why {nameOf(job.worker_id)}:</span> {job.match_reason}
          </p>
        )}
        {isOwner && ["open", "matched"].includes(job.status) && (
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="quiet" disabled={!!busy} onClick={() => match(false)}>
              {busy === "suggest" ? "Asking the AI…" : "Ask AI for a match"}
            </Button>
            <Button disabled={!!busy} onClick={() => match(true)}>
              {busy === "assign" ? "Matching…" : "Match and assign"}
            </Button>
          </div>
        )}
        {pick && (
          <div className="mt-4 rounded-md border border-line p-4 text-sm">
            <p><span className="font-medium">AI suggests {pick.top_name}</span>{pick.backup_name && <span className="text-muted">, backup {pick.backup_name}</span>}{pick.assigned && <span className="text-guild"> (assigned)</span>}</p>
            <p className="mt-1 text-muted">{pick.reason}</p>
          </div>
        )}
        <ErrorText>{err}</ErrorText>
        <Notice>{notice}</Notice>
      </Panel>

      <Panel title="Milestones">
        {(milestones ?? []).length === 0 && (
          <p className="text-sm text-muted">No milestones yet. Add one to invoice the client.</p>
        )}
        <ul className="space-y-4">
          {(milestones ?? []).map((m) => {
            const inv = invoiceFor(m.id);
            return (
              <li key={m.id} className="rounded-md border border-line p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{m.title} <span className="ml-1 tabular-nums text-muted">{usd(m.amount)}</span></p>
                    {m.scope && <p className="mt-0.5 text-sm text-muted">{m.scope}</p>}
                  </div>
                  <StatusPill status={inv?.status ?? m.status} />
                </div>

                {guild && job.worker_id && (
                  <div className="mt-3">
                    <SplitBar
                      amount={m.amount}
                      workerPct={guild.worker_pct}
                      referrerPct={guild.referrer_pct}
                      poolPct={guild.pool_pct}
                      hasReferrer={hasReferrer}
                      workerName={nameOf(job.worker_id)}
                      referrerName={nameOf(job.referrer_id)}
                    />
                  </div>
                )}

                <div className="mt-3 flex flex-wrap gap-2">
                  {!inv && (isOwner || isWorker) && (
                    <Button disabled={!job.worker_id || !!busy} onClick={() => sendInvoice(m.id)}
                      title={!job.worker_id ? "Assign a worker first" : undefined}>
                      {busy === `send-${m.id}` ? "Sending…" : "Send invoice"}
                    </Button>
                  )}
                  {inv?.status === "sent" && (
                    <>
                      {inv.pay_url && (
                        <a href={inv.pay_url} target="_blank" rel="noreferrer"
                          className="rounded-md border border-line bg-white px-3.5 py-2 text-sm font-medium hover:bg-paper">
                          Open client pay page
                        </a>
                      )}
                      <Button variant="quiet" disabled={!!busy} onClick={() => checkPayment(inv.id)}>
                        {busy === `sync-${inv.id}` ? "Checking…" : "Check payment"}
                      </Button>
                      {isWorker && job.status !== "disputed" && (
                        <Button variant="danger" disabled={!!busy} onClick={() => setClaimFor(claimFor === inv.id ? null : inv.id)}>
                          Client isn't paying
                        </Button>
                      )}
                    </>
                  )}
                </div>

                {claimFor === inv?.id && inv && (
                  <ClaimForm invoiceId={inv.id} onDone={(msg) => { setClaimFor(null); setNotice(msg); refreshAll(); }} />
                )}
              </li>
            );
          })}
        </ul>

        {isOwner && (
          <form onSubmit={addMilestone} className="mt-5 grid gap-3 border-t border-line pt-5 md:grid-cols-6">
            <input required name="title" placeholder="Milestone, like Homepage design" className={`${inputCls} md:col-span-2`} />
            <input name="scope" placeholder="What's included" className={`${inputCls} md:col-span-2`} />
            <input required name="amount" type="number" min="1" step="0.01" placeholder="Amount ($)" className={inputCls} />
            <Button disabled={!!busy}>{busy === "milestone" ? "Adding…" : "Add"}</Button>
          </form>
        )}
      </Panel>
    </div>
  );
}

function ClaimForm({ invoiceId, onDone }: { invoiceId: string; onDone: (msg: string) => void }) {
  const [statement, setStatement] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await apiPost<{ claim: { ai_verdict: string }; ai_review: string }>("/claims", {
        invoice_id: invoiceId,
        statement,
        evidence_urls: evidence.split(",").map((s) => s.trim()).filter(Boolean),
      });
      onDone(r.ai_review === "done"
        ? `Claim filed. The AI recommends "${r.claim.ai_verdict.replaceAll("_", " ")}". An admin makes the final call.`
        : "Claim filed. The AI review didn't finish, so an admin will retry it.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't file the claim");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 space-y-3 rounded-md bg-alert-soft/50 p-4">
      <p className="text-sm">
        The safety pool can cover part of an unpaid invoice. Tell the guild what happened. The AI reviews it, then an admin decides.
      </p>
      <textarea required minLength={20} rows={4} value={statement} onChange={(e) => setStatement(e.target.value)}
        className={inputCls} placeholder="What did you deliver, when, and what has the client said since?" />
      <input value={evidence} onChange={(e) => setEvidence(e.target.value)} className={inputCls}
        placeholder="Evidence files, separated by commas (contract.pdf, approval_email.png)" />
      <ErrorText>{err}</ErrorText>
      <Button variant="danger" disabled={busy}>{busy ? "Filing and reviewing…" : "File claim"}</Button>
    </form>
  );
}