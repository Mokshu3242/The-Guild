"use client";

import useSWR, { mutate } from "swr";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
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

export default function JobPageWrapper() {
  return (
    <Suspense fallback={<p className="text-muted">Loading job…</p>}>
      <JobPage />
    </Suspense>
  );
}

function JobPage() {
  const id = useSearchParams().get("id") ?? "";
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

      {isOwner && (milestones ?? []).length === 0 && ["open", "matched"].includes(job.status) && (
        <Panel title="Turn the client's brief into milestones">
          <ScopeBuilder jobId={id} onApplied={() => { refreshMs(); setNotice("Milestones added. Review the split below, then send the first invoice."); }} />
        </Panel>
      )}

      {!job.worker_id && (milestones ?? []).length > 0 && (
        <p className="mb-4 rounded-md bg-seal-soft px-3 py-2 text-sm text-seal">
          Assign a worker to see how each payment splits and to send invoices.
        </p>
      )}

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
                  {!inv && isOwner && (
                    <Button
                      variant="danger"
                      disabled={!!busy}
                      onClick={() => {
                        if (!window.confirm(`Remove "${m.title}"? This can't be undone.`)) return;
                        run(`remove-${m.id}`, async () => {
                          await apiDelete(`/jobs/${id}/milestones/${m.id}`);
                          setNotice(`Removed "${m.title}".`);
                          refreshMs();
                        });
                      }}
                    >
                      {busy === `remove-${m.id}` ? "Removing…" : "Remove"}
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
                      {me.role === "admin" && (
                        <Button variant="quiet" disabled={!!busy} onClick={() => run(`remind-${inv.id}`, async () => {
                          const r = await apiPost<{ status: string; tier?: number; subject?: string; days_overdue?: number }>(`/invoices/${inv.id}/remind`);
                          const msg: Record<string, string> = {
                            sent: `Reminder ${r.tier} of 3 sent: "${r.subject}"`,
                            not_due: `No reminder due yet. The invoice is ${r.days_overdue} days old.`,
                            already_paid: "The client already paid. Payout sent instead.",
                            paypal_failed: "PayPal didn't accept the reminder. Try again shortly.",
                          };
                          setNotice(msg[r.status] ?? `Status: ${r.status}`);
                          mutate(["reminders", inv.id]);
                          refreshAll();
                        })}>
                          {busy === `remind-${inv.id}` ? "Writing reminder…" : "Send reminder"}
                        </Button>
                      )}
                      {isWorker && job.status !== "disputed" && (
                        <Button variant="danger" disabled={!!busy} onClick={() => setClaimFor(claimFor === inv.id ? null : inv.id)}>
                          Client isn't paying
                        </Button>
                      )}
                    </>
                  )}
                </div>

                {inv && <ReminderHistory invoiceId={inv.id} />}

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

interface Reminder { id: string; tier: number; subject: string; body: string; days_overdue: number; sent_at: string | null; written_by: string }

const TIER_LABEL: Record<number, string> = { 1: "Friendly check-in", 2: "Firm reminder", 3: "Final notice" };

function ReminderHistory({ invoiceId }: { invoiceId: string }) {
  const { data } = useSWR<Reminder[]>(["reminders", invoiceId], () => apiGet<Reminder[]>(`/invoices/${invoiceId}/reminders`));
  if (!data || data.length === 0) return null;
  return (
    <details className="mt-3 rounded-md border border-line bg-paper p-3 text-sm">
      <summary className="cursor-pointer font-medium">Reminders sent to the client ({data.length})</summary>
      <ol className="mt-3 space-y-3">
        {data.map((r) => (
          <li key={r.id} className="rounded-md bg-white p-3 ring-1 ring-line">
            <p className="text-xs text-muted">
              <span className="font-semibold text-seal">{TIER_LABEL[r.tier]}</span>, sent when {r.days_overdue} days overdue
              {r.written_by === "ai" ? ", written by AI" : ""}
            </p>
            <p className="mt-1 font-medium">{r.subject}</p>
            <p className="mt-1 whitespace-pre-line text-muted">{r.body}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

interface DraftMilestone { title: string; scope: string; amount_cents: number }
interface ScopeDraft { summary: string; budget_cents: number | null; pricing_basis: string; milestones: DraftMilestone[] }
interface EditRow { title: string; scope: string; amount: string }

const toCents = (s: string) => Math.round(parseFloat(s || "0") * 100);

function ScopeBuilder({ jobId, onApplied }: { jobId: string; onApplied: () => void }) {
  const [brief, setBrief] = useState("");
  const [draft, setDraft] = useState<ScopeDraft | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [busy, setBusy] = useState<"draft" | "apply" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function runDraft() {
    setBusy("draft"); setErr(null);
    try {
      const r = await apiPost<ScopeDraft>(`/jobs/${jobId}/scope/draft`, { brief });
      setDraft(r);
      setRows(r.milestones.map((m) => ({ title: m.title, scope: m.scope, amount: (m.amount_cents / 100).toFixed(2) })));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't draft milestones");
    } finally { setBusy(null); }
  }

  async function apply() {
    setBusy("apply"); setErr(null);
    try {
      await apiPost(`/jobs/${jobId}/scope/apply`, {
        milestones: rows.map((r) => ({ title: r.title, scope: r.scope, amount_cents: toCents(r.amount) })),
      });
      setDraft(null); setRows([]); setBrief("");
      onApplied();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't add milestones");
    } finally { setBusy(null); }
  }

  const edit = (i: number, patch: Partial<EditRow>) =>
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const total = rows.reduce((sum, r) => sum + toCents(r.amount), 0);
  const budget = draft?.budget_cents ?? null;
  const offBudget = budget !== null && total !== budget;

  if (!draft) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">Paste what the client sent. The AI splits it into milestones you can review and edit before anything is created.</p>
        <textarea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)} className={inputCls}
          placeholder="Paste the client's email, message, or notes…" />
        <Button disabled={brief.trim().length < 30 || busy === "draft"} onClick={runDraft}>
          {busy === "draft" ? "Reading the brief…" : "Draft milestones"}
        </Button>
        <ErrorText>{err}</ErrorText>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md bg-guild-soft px-3 py-2 text-sm text-guild">
        <p><span className="rounded bg-white/60 px-1.5 py-0.5 text-xs font-semibold">AI</span> {draft.summary}</p>
        <p className="mt-1 text-xs">{draft.pricing_basis}</p>
      </div>

      <ul className="space-y-3">
        {rows.map((r, i) => (
          <li key={i} className="rounded-md border border-line p-3">
            <div className="flex flex-wrap items-center gap-2">
              <input aria-label="Milestone title" value={r.title} onChange={(e) => edit(i, { title: e.target.value })}
                className={`${inputCls} min-w-[180px] flex-1`} />
              <label className="flex items-center gap-1 text-sm text-muted">$
                <input aria-label="Amount in dollars" inputMode="decimal" value={r.amount}
                  onChange={(e) => edit(i, { amount: e.target.value.replace(/[^0-9.]/g, "") })}
                  className={`${inputCls} w-28`} />
              </label>
              <button type="button" onClick={() => setRows((p) => p.filter((_, idx) => idx !== i))}
                className="text-sm text-alert hover:underline">Remove</button>
            </div>
            <textarea aria-label="What's included" rows={2} value={r.scope}
              onChange={(e) => edit(i, { scope: e.target.value })} className={`${inputCls} mt-2`} />
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          Total <span className="font-semibold tabular-nums">{usd(total)}</span>
          {budget !== null && (
            <span className={offBudget ? "ml-2 text-alert" : "ml-2 text-muted"}>
              {offBudget ? `(client's budget is ${usd(budget)})` : "(matches the client's budget)"}
            </span>
          )}
        </p>
        <div className="flex gap-2">
          <Button variant="quiet" onClick={() => { setDraft(null); setRows([]); }}>Start over</Button>
          <Button disabled={rows.length === 0 || busy === "apply"} onClick={apply}>
            {busy === "apply" ? "Adding…" : `Add ${rows.length} milestone${rows.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      </div>
      <ErrorText>{err}</ErrorText>
    </div>
  );
}