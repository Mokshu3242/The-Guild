"use client";

import useSWR, { mutate } from "swr";
import { Suspense, useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useSearchParams } from "next/navigation";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { timeAgo, usd } from "@/lib/format";
import { useMe } from "@/lib/useMe";
import { useGuild, useMembers } from "@/lib/useGuild";
import type { Job } from "@/components/JobsGrid";
import { SplitBar } from "@/components/SplitBar";
import { MoneyFlow, type SplitData } from "@/components/MoneyFlow";
import { AiThinking } from "@/components/AiThinking";
import {
  Button,
  ErrorText,
  Notice,
  Panel,
  StatusPill,
  inputCls,
} from "@/components/ui";

interface Milestone {
  id: string;
  title: string;
  scope: string;
  amount: number;
  status: string;
}
interface Invoice {
  id: string;
  milestone_id: string;
  status: string;
  pay_url: string;
  amount: number;
}
interface MatchPick {
  top_name: string;
  backup_name: string | null;
  reason: string;
  assigned: boolean;
}
interface SyncResult {
  status: string;
  paypal_status?: string;
  worker_cents?: number;
  recovered_cents?: number;
}
interface DepositRow {
  id: string;
  milestone_id: string;
  amount_cents: number;
  approve_url: string;
  status: "created" | "authorized" | "captured" | "voided";
  ai_verdict: string;
  ai_reason: string;
  created_at: string;
}

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
  const { data: job, mutate: refreshJob } = useSWR<Job>(["job", id], () =>
    apiGet<Job>(`/jobs/${id}`),
  );
  const { data: milestones, mutate: refreshMs } = useSWR<Milestone[]>(
    ["milestones", id],
    () => apiGet<Milestone[]>(`/jobs/${id}/milestones`),
  );
  const { data: invoices, mutate: refreshInv } = useSWR<Invoice[]>(
    "invoices",
    () => apiGet<Invoice[]>("/invoices"),
  );
  const { data: deposits, mutate: refreshDeposits } = useSWR<DepositRow[]>(
    ["deposits", id],
    () => apiGet<DepositRow[]>(`/deposits/for-job/${id}`),
  );

  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pick, setPick] = useState<MatchPick | null>(null);
  const [claimFor, setClaimFor] = useState<string | null>(null);
  const [splitOverlay, setSplitOverlay] = useState<SplitData | null>(null);

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setErr(null);
    setNotice(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }
  const refreshAll = () => {
    refreshJob();
    refreshMs();
    refreshInv();
    refreshDeposits();
  };

  if (!job || !me) return <p className="text-muted">Loading job…</p>;

  const nameOf = (mid: string | null) =>
    members?.find((m) => m.id === mid)?.name ?? "Not assigned";
  const isOwner = job.referrer_id === me.id || me.role === "admin";
  const isWorker = job.worker_id === me.id;
  const hasReferrer = !!job.worker_id && job.referrer_id !== job.worker_id;
  // Same 85 / 10 / 5 math as the split bar. The backend still does the real split.
  const splitFor = (
    amount: number,
    source: SplitData["source"],
    recoveredCents = 0,
  ): SplitData | null => {
    if (!guild || !job.worker_id) return null;
    const frac = (p: number) => (p > 1 ? p / 100 : p);
    const poolCents = Math.floor(amount * frac(guild.pool_pct));
    const referrerCents = hasReferrer
      ? Math.floor(amount * frac(guild.referrer_pct))
      : 0;
    return {
      amountCents: amount,
      workerCents: amount - poolCents - referrerCents,
      referrerCents,
      poolCents,
      recoveredCents,
      workerName: nameOf(job.worker_id),
      referrerName: nameOf(job.referrer_id),
      source,
    };
  };
  const invoiceFor = (msId: string) =>
    invoices?.find((i) => i.milestone_id === msId);
  const depositFor = (msId: string) =>
    deposits?.find((d) => d.milestone_id === msId && d.status !== "voided");
  const hasActiveDeposit = (msId: string) =>
    ["created", "authorized"].includes(depositFor(msId)?.status ?? "");

  const match = (assign: boolean) =>
    run(assign ? "assign" : "suggest", async () => {
      const r = await apiPost<MatchPick>(`/jobs/${id}/match`, {
        auto_assign: assign,
      });
      setPick(r);
      if (assign) refreshJob();
    });

  const addMilestone = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const d = Object.fromEntries(new FormData(form)) as Record<string, string>;
    run("milestone", async () => {
      await apiPost(`/jobs/${id}/milestones`, {
        title: d.title,
        scope: d.scope,
        amount_cents: Math.round(parseFloat(d.amount) * 100),
      });
      form.reset();
      refreshMs();
    });
  };

  const sendInvoice = (msId: string) =>
    run(`send-${msId}`, async () => {
      await apiPost(`/invoices/milestones/${msId}/send`);
      setNotice("Invoice sent to the client through PayPal.");
      refreshAll();
    });

  const checkPayment = (invId: string) =>
    run(`sync-${invId}`, async () => {
      const r = await apiPost<SyncResult>(`/invoices/${invId}/sync`);
      if (r.status === "processed") {
        const inv = invoices?.find((i) => i.id === invId);
        const ms = milestones?.find((x) => x.id === inv?.milestone_id);
        if (ms) setSplitOverlay(splitFor(ms.amount, "invoice", r.recovered_cents ?? 0));
        setNotice(
          `Paid. ${usd(r.worker_cents ?? 0)} sent to the worker${r.recovered_cents ? `, and ${usd(r.recovered_cents)} returned to the pool` : ""}.`,
        );
      } else if (r.status === "already_paid") {
        setNotice("Already paid and split.");
      } else {
        setNotice(
          `Not paid yet. PayPal says the invoice is ${r.paypal_status?.toLowerCase() ?? "waiting"}.`,
        );
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
        <p className="mt-1 text-sm text-muted">
          Posted by {nameOf(job.referrer_id)}. Worker: {nameOf(job.worker_id)}.
        </p>
        {job.status === "disputed" && me.role === "admin" && (
          <a
            href="/claims/"
            className="mt-2 inline-block text-sm text-alert hover:underline"
          >
            A claim is waiting for your review
          </a>
        )}
      </div>

      <Panel title="What the client needs">
        <p className="max-w-prose leading-relaxed">{job.description}</p>
        {job.match_reason && (
          <p className="mt-4 rounded-md bg-guild-soft px-3 py-2 text-sm text-guild">
            <span className="font-medium">Why {nameOf(job.worker_id)}:</span>{" "}
            {job.match_reason}
          </p>
        )}
        {isOwner && ["open", "matched"].includes(job.status) && (
          <div className="mt-5 flex flex-wrap gap-2">
            <Button
              variant="quiet"
              disabled={!!busy}
              onClick={() => match(false)}
            >
              {busy === "suggest" ? "Asking the AI…" : "Ask AI for a match"}
            </Button>
            <Button disabled={!!busy} onClick={() => match(true)}>
              {busy === "assign" ? "Matching…" : "Match and assign"}
            </Button>
          </div>
        )}
        {(busy === "suggest" || busy === "assign") && (
          <div className="mt-4">
            <AiThinking label="Reading the job and picking the best member…" />
          </div>
        )}
        {pick && (
          <div className="mt-4 rounded-md border border-line p-4 text-sm">
            <p>
              <span className="font-medium">AI suggests {pick.top_name}</span>
              {pick.backup_name && (
                <span className="text-muted">, backup {pick.backup_name}</span>
              )}
              {pick.assigned && <span className="text-guild"> (assigned)</span>}
            </p>
            <p className="mt-1 text-muted">{pick.reason}</p>
          </div>
        )}
        <ErrorText>{err}</ErrorText>
        <Notice>{notice}</Notice>
      </Panel>

      {isOwner &&
        (milestones ?? []).length === 0 &&
        ["open", "matched"].includes(job.status) && (
          <Panel title="Turn the client's brief into milestones">
            <ScopeBuilder
              jobId={id}
              onApplied={() => {
                refreshMs();
                setNotice(
                  "Milestones added. Review the split below, then send the first invoice.",
                );
              }}
            />
          </Panel>
        )}

      {!job.worker_id && (milestones ?? []).length > 0 && (
        <p className="mb-4 rounded-md bg-seal-soft px-3 py-2 text-sm text-seal">
          Assign a worker to see how each payment splits and to send invoices.
        </p>
      )}

      <Panel title="Milestones">
        {(milestones ?? []).length === 0 && (
          <p className="text-sm text-muted">
            No milestones yet. Add one to invoice the client.
          </p>
        )}
        <ul className="space-y-4">
          {(milestones ?? []).map((m) => {
            const inv = invoiceFor(m.id);
            const held = hasActiveDeposit(m.id);
            return (
              <li key={m.id} className="rounded-md border border-line p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">
                      {m.title}{" "}
                      <span className="ml-1 tabular-nums text-muted">
                        {usd(m.amount)}
                      </span>
                    </p>
                    {m.scope && (
                      <p className="mt-0.5 text-sm text-muted">{m.scope}</p>
                    )}
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

                {guild && job.worker_id && (
                  <DepositPanel
                    key={depositFor(m.id)?.id ?? "none"}
                    jobId={id}
                    milestone={m}
                    deposit={depositFor(m.id)}
                    canRequest={isOwner && !inv && m.status === "pending"}
                    isAdmin={me.role === "admin"}
                    onChange={refreshAll}
                    onCaptured={() => setSplitOverlay(splitFor(m.amount, "deposit"))}
                  />
                )}

                <div className="mt-3 flex flex-wrap gap-2">
                  {!inv && !held && (isOwner || isWorker) && (
                    <Button
                      disabled={!job.worker_id || !!busy}
                      onClick={() => sendInvoice(m.id)}
                      title={
                        !job.worker_id ? "Assign a worker first" : undefined
                      }
                    >
                      {busy === `send-${m.id}` ? "Sending…" : "Send invoice"}
                    </Button>
                  )}
                  {!inv && !held && isOwner && (
                    <Button
                      variant="danger"
                      disabled={!!busy}
                      onClick={() => {
                        if (
                          !window.confirm(
                            `Remove "${m.title}"? This can't be undone.`,
                          )
                        )
                          return;
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
                        <a
                          href={inv.pay_url}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-md border border-line bg-white px-3.5 py-2 text-sm font-medium hover:bg-paper"
                        >
                          Open client pay page
                        </a>
                      )}
                      <Button
                        variant="quiet"
                        disabled={!!busy}
                        onClick={() => checkPayment(inv.id)}
                      >
                        {busy === `sync-${inv.id}`
                          ? "Checking…"
                          : "Check payment"}
                      </Button>
                      {me.role === "admin" && (
                        <Button
                          variant="quiet"
                          disabled={!!busy}
                          onClick={() =>
                            run(`remind-${inv.id}`, async () => {
                              const r = await apiPost<{
                                status: string;
                                tier?: number;
                                subject?: string;
                                days_overdue?: number;
                              }>(`/invoices/${inv.id}/remind`);
                              const msg: Record<string, string> = {
                                sent: `Reminder ${r.tier} of 3 sent: "${r.subject}"`,
                                not_due: `No reminder due yet. The invoice is ${r.days_overdue} days old.`,
                                already_paid:
                                  "The client already paid. Payout sent instead.",
                                paypal_failed:
                                  "PayPal didn't accept the reminder. Try again shortly.",
                              };
                              setNotice(msg[r.status] ?? `Status: ${r.status}`);
                              mutate(["reminders", inv.id]);
                              refreshAll();
                            })
                          }
                        >
                          {busy === `remind-${inv.id}`
                            ? "Writing reminder…"
                            : "Send reminder"}
                        </Button>
                      )}
                      {isWorker && job.status !== "disputed" && (
                        <Button
                          variant="danger"
                          disabled={!!busy}
                          onClick={() =>
                            setClaimFor(claimFor === inv.id ? null : inv.id)
                          }
                        >
                          Client isn't paying
                        </Button>
                      )}
                    </>
                  )}
                </div>

                {inv && <ReminderHistory invoiceId={inv.id} />}

                {claimFor === inv?.id && inv && (
                  <ClaimForm
                    invoiceId={inv.id}
                    onDone={(msg) => {
                      setClaimFor(null);
                      setNotice(msg);
                      refreshAll();
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>

        {isOwner && (
          <form
            onSubmit={addMilestone}
            className="mt-5 grid gap-3 border-t border-line pt-5 md:grid-cols-6"
          >
            <input
              required
              name="title"
              placeholder="Milestone, like Homepage design"
              className={`${inputCls} md:col-span-2`}
            />
            <input
              name="scope"
              placeholder="What's included"
              className={`${inputCls} md:col-span-2`}
            />
            <input
              required
              name="amount"
              type="number"
              min="1"
              step="0.01"
              placeholder="Amount ($)"
              className={inputCls}
            />
            <Button disabled={!!busy}>
              {busy === "milestone" ? "Adding…" : "Add"}
            </Button>
          </form>
        )}
      </Panel>

      {(isOwner || isWorker) &&
        ["open", "matched", "in_progress"].includes(job.status) && (
          <Panel title="Watch for scope creep">
            <ScopeWatch
              jobId={id}
              canDecide={isOwner}
              onAdded={() => {
                refreshMs();
                setNotice(
                  "Add-on milestone created. Send its invoice when the work is done.",
                );
              }}
            />
          </Panel>
        )}

      <MoneyFlow data={splitOverlay} onDone={() => setSplitOverlay(null)} />
    </div>
  );
}

/* ---------------- Deposit hold ---------------- */

const DEPOSIT_LABEL: Record<string, { text: string; cls: string }> = {
  created: {
    text: "Waiting for the client to approve",
    cls: "bg-paper text-muted",
  },
  authorized: { text: "On hold, not charged yet", cls: "bg-seal-soft text-seal" },
  opening: { text: "Captured", cls: "bg-guild-soft text-guild" },
  released: { text: "Released, not charged", cls: "bg-paper text-muted" },
};

const SEAL_EASE = [0.22, 1, 0.36, 1] as const;

// A small padlock. The shackle lifts and tilts when it opens.
function LockIcon({ open, reduce }: { open: boolean; reduce: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
      <motion.path
        d="M8 11V7a4 4 0 0 1 8 0v4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        style={{ originX: "8px", originY: "11px" }}
        initial={false}
        animate={open ? { y: -3, rotate: -18 } : { y: 0, rotate: 0 }}
        transition={reduce ? { duration: 0 } : { duration: 0.35, ease: SEAL_EASE }}
      />
      <rect x="5" y="11" width="14" height="10" rx="2" fill="currentColor" />
    </svg>
  );
}

function StatusSeal({
  phase,
  dropIn,
  reduce,
}: {
  phase: "created" | "authorized" | "opening" | "released";
  dropIn: boolean;
  reduce: boolean;
}) {
  if (phase === "created") {
    return (
      <motion.span
        className="block h-2 w-2 rounded-full bg-gray-400"
        animate={reduce ? undefined : { opacity: [0.35, 1, 0.35] }}
        transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        aria-hidden="true"
      />
    );
  }
  const color =
    phase === "opening" ? "text-guild" : phase === "released" ? "text-muted" : "text-seal";
  return (
    <motion.span
      className={`block transition-colors duration-300 ${color}`}
      initial={dropIn && !reduce ? { y: -24, opacity: 0, scale: 0.5 } : false}
      animate={{ y: 0, opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 340, damping: 18, mass: 0.7 }}
    >
      <LockIcon open={phase !== "authorized"} reduce={reduce} />
    </motion.span>
  );
}

function DepositPanel({
  jobId,
  milestone,
  deposit,
  canRequest,
  isAdmin,
  onChange,
  onCaptured,
}: {
  jobId: string;
  milestone: Milestone;
  deposit?: DepositRow;
  canRequest: boolean;
  isAdmin: boolean;
  onChange: () => void;
  onCaptured?: () => void;
}) {
  const reduce = !!useReducedMotion();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState("");
  // Local phases play an animation before the server data catches up.
  const [local, setLocal] = useState<"opening" | "released" | null>(null);

  // Only drop the lock and glow when we watched it go from created to authorized.
  // Reloading a page that is already on hold stays calm.
  const prevStatus = useRef(deposit?.status);
  const [justAuthorized, setJustAuthorized] = useState(false);
  useEffect(() => {
    if (prevStatus.current === "created" && deposit?.status === "authorized") {
      setJustAuthorized(true);
    }
    prevStatus.current = deposit?.status;
  }, [deposit?.status]);

  const wait = (ms: number) =>
    new Promise((r) => setTimeout(r, reduce ? 0 : ms));

  async function act(key: string, fn: () => Promise<void>, refresh = true) {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      if (refresh) onChange();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }

  const capture = () =>
    act(
      "capture",
      async () => {
        await apiPost(`/deposits/${deposit!.id}/capture`);
        setLocal("opening");
        await wait(450); // let the lock open before the overlay covers it
        onCaptured?.();
        onChange();
      },
      false,
    );

  const release = () =>
    act(
      "void",
      async () => {
        await apiPost(`/deposits/${deposit!.id}/void`);
        setLocal("released");
        await wait(900); // show the strip, then collapse
        onChange();
      },
      false,
    );

  if (deposit?.status === "captured") {
    return (
      <motion.p
        initial={reduce ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="mt-3 flex items-center gap-2 text-sm text-guild"
      >
        <LockIcon open reduce />
        Paid from the deposit hold and split automatically.
      </motion.p>
    );
  }

  if (!deposit) {
    if (!canRequest) return null;
    return (
      <motion.div
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mt-3 rounded-md border border-dashed border-line p-3"
      >
        <p className="text-sm text-muted">
          Want security before starting? Hold {usd(milestone.amount)} on the
          client&apos;s PayPal now. Nothing is charged until the work is
          accepted.
        </p>
        <Button
          variant="quiet"
          className="mt-2"
          disabled={!!busy}
          onClick={() =>
            act("request", async () => {
              const d = await apiPost<DepositRow>(
                `/jobs/${jobId}/milestones/${milestone.id}/deposit`,
              );
              if (d.approve_url) window.open(d.approve_url, "_blank");
            })
          }
        >
          {busy === "request" ? "Setting up…" : "Request a deposit hold"}
        </Button>
        <ErrorText>{err}</ErrorText>
      </motion.div>
    );
  }

  const phase =
    local ?? (deposit.status === "authorized" ? "authorized" : "created");
  const label = DEPOSIT_LABEL[phase];
  const glow = justAuthorized && !reduce && phase === "authorized";

  return (
    <motion.div
      className="mt-3 overflow-hidden rounded-md border border-seal/30 bg-seal-soft/30 text-sm"
      initial={false}
      animate={
        local === "released"
          ? { opacity: 0, height: 0, marginTop: 0 }
          : glow
            ? {
                boxShadow: [
                  "0 0 0 0 rgba(168,122,31,0)",
                  "0 0 0 8px rgba(168,122,31,0.18)",
                  "0 0 0 0 rgba(168,122,31,0)",
                ],
              }
            : undefined
      }
      transition={
        local === "released"
          ? { duration: reduce ? 0 : 0.5, delay: reduce ? 0 : 0.4, ease: "easeInOut" }
          : { duration: 1.1, ease: "easeOut" }
      }
    >
      <div className="p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <StatusSeal phase={phase} dropIn={justAuthorized} reduce={reduce} />
            <span
              className={`rounded px-1.5 py-0.5 text-xs font-semibold ${label.cls}`}
            >
              {label.text}
            </span>
          </div>
          <span className="tabular-nums text-muted">
            {usd(deposit.amount_cents)} deposit
          </span>
        </div>

        {phase === "created" && (
          <div className="mt-3 flex flex-wrap gap-2">
            {deposit.approve_url && (
              <a
                href={deposit.approve_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-line bg-white px-3.5 py-2 text-sm font-medium hover:bg-paper"
              >
                Open client approval page
              </a>
            )}
            <Button
              variant="quiet"
              disabled={!!busy}
              onClick={() =>
                act("refresh", () =>
                  apiPost(`/deposits/${deposit.id}/refresh`).then(() => {}),
                )
              }
            >
              {busy === "refresh" ? "Checking PayPal…" : "Check approval"}
            </Button>
            {isAdmin && (
              <Button variant="danger" disabled={!!busy} onClick={release}>
                {busy === "void" ? "Cancelling…" : "Cancel request"}
              </Button>
            )}
          </div>
        )}

        {phase === "authorized" && isAdmin && (
          <>
            <p className="mt-3 text-muted">
              The client&apos;s money is on hold. Check the work, then capture
              it to pay everyone, or release the hold.
            </p>
            <textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className={`${inputCls} mt-2`}
              placeholder="Optional: describe what was delivered, and the AI will check it against the scope"
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {note.trim().length >= 15 && (
                <Button
                  variant="quiet"
                  disabled={!!busy}
                  onClick={() =>
                    act("review", () =>
                      apiPost(`/deposits/${deposit.id}/review`, { note }).then(
                        () => {},
                      ),
                    )
                  }
                >
                  {busy === "review" ? "Checking…" : "Ask AI to check the work"}
                </Button>
              )}
              <Button disabled={!!busy} onClick={capture}>
                {busy === "capture" ? "Capturing…" : "Accept work and capture"}
              </Button>
              <Button
                variant="danger"
                disabled={!!busy}
                onClick={() => {
                  if (
                    !window.confirm(
                      "Release the hold? The client won't be charged.",
                    )
                  )
                    return;
                  release();
                }}
              >
                {busy === "void" ? "Releasing…" : "Release hold"}
              </Button>
            </div>
            {busy === "review" && (
              <div className="mt-3">
                <AiThinking label="Comparing the delivery note to the scope…" />
              </div>
            )}
          </>
        )}

        {phase === "authorized" && !isAdmin && (
          <p className="mt-3 text-muted">
            The client&apos;s money is on hold. A guild admin captures it once
            the work is accepted.
          </p>
        )}

        {deposit.ai_verdict && local !== "released" && (
          <p className="mt-3 rounded-md border border-line bg-white p-3 text-xs">
            <span className="font-semibold text-guild">AI:</span>{" "}
            {deposit.ai_verdict}. {deposit.ai_reason}
          </p>
        )}
        <ErrorText>{err}</ErrorText>
      </div>
    </motion.div>
  );
}

/* ---------------- Claims ---------------- */

function ClaimForm({
  invoiceId,
  onDone,
}: {
  invoiceId: string;
  onDone: (msg: string) => void;
}) {
  const [statement, setStatement] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await apiPost<{
        claim: { ai_verdict: string };
        ai_review: string;
      }>("/claims", {
        invoice_id: invoiceId,
        statement,
        evidence_urls: evidence
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      onDone(
        r.ai_review === "done"
          ? `Claim filed. The AI recommends "${r.claim.ai_verdict.replaceAll("_", " ")}". An admin makes the final call.`
          : "Claim filed. The AI review didn't finish, so an admin will retry it.",
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't file the claim");
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="mt-4 space-y-3 rounded-md bg-alert-soft/50 p-4"
    >
      <p className="text-sm">
        The safety pool can cover part of an unpaid invoice. Tell the guild what
        happened. The AI reviews it, then an admin decides.
      </p>
      <textarea
        required
        minLength={20}
        rows={4}
        value={statement}
        onChange={(e) => setStatement(e.target.value)}
        className={inputCls}
        placeholder="What did you deliver, when, and what has the client said since?"
      />
      <input
        value={evidence}
        onChange={(e) => setEvidence(e.target.value)}
        className={inputCls}
        placeholder="Evidence files, separated by commas (contract.pdf, approval_email.png)"
      />
      <ErrorText>{err}</ErrorText>
      <Button variant="danger" disabled={busy}>
        {busy ? "Filing and reviewing…" : "File claim"}
      </Button>
    </form>
  );
}

/* ---------------- Reminders ---------------- */

interface Reminder {
  id: string;
  tier: number;
  subject: string;
  body: string;
  days_overdue: number;
  sent_at: string | null;
  written_by: string;
}

const TIER_LABEL: Record<number, string> = {
  1: "Friendly check-in",
  2: "Firm reminder",
  3: "Final notice",
};

function ReminderHistory({ invoiceId }: { invoiceId: string }) {
  const { data } = useSWR<Reminder[]>(["reminders", invoiceId], () =>
    apiGet<Reminder[]>(`/invoices/${invoiceId}/reminders`),
  );
  if (!data || data.length === 0) return null;
  return (
    <details className="mt-3 rounded-md border border-line bg-paper p-3 text-sm">
      <summary className="cursor-pointer rounded-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40">
        Reminders sent to the client ({data.length})
      </summary>
      <ol className="mt-3 space-y-3">
        {data.map((r) => (
          <li key={r.id} className="rounded-md bg-white p-3 ring-1 ring-line">
            <p className="text-xs text-muted">
              <span className="font-semibold text-seal">
                {TIER_LABEL[r.tier]}
              </span>
              , sent when {r.days_overdue} days overdue
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

/* ---------------- Scope builder ---------------- */

interface DraftMilestone {
  title: string;
  scope: string;
  amount_cents: number;
}
interface ScopeDraft {
  summary: string;
  budget_cents: number | null;
  pricing_basis: string;
  milestones: DraftMilestone[];
}
interface EditRow {
  title: string;
  scope: string;
  amount: string;
}

const toCents = (s: string) => Math.round(parseFloat(s || "0") * 100);

function ScopeBuilder({
  jobId,
  onApplied,
}: {
  jobId: string;
  onApplied: () => void;
}) {
  const [brief, setBrief] = useState("");
  const [draft, setDraft] = useState<ScopeDraft | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [busy, setBusy] = useState<"draft" | "apply" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function runDraft() {
    setBusy("draft");
    setErr(null);
    try {
      const r = await apiPost<ScopeDraft>(`/jobs/${jobId}/scope/draft`, {
        brief,
      });
      setDraft(r);
      setRows(
        r.milestones.map((m) => ({
          title: m.title,
          scope: m.scope,
          amount: (m.amount_cents / 100).toFixed(2),
        })),
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't draft milestones");
    } finally {
      setBusy(null);
    }
  }

  async function apply() {
    setBusy("apply");
    setErr(null);
    try {
      await apiPost(`/jobs/${jobId}/scope/apply`, {
        milestones: rows.map((r) => ({
          title: r.title,
          scope: r.scope,
          amount_cents: toCents(r.amount),
        })),
      });
      setDraft(null);
      setRows([]);
      setBrief("");
      onApplied();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't add milestones");
    } finally {
      setBusy(null);
    }
  }

  const edit = (i: number, patch: Partial<EditRow>) =>
    setRows((prev) =>
      prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    );

  const total = rows.reduce((sum, r) => sum + toCents(r.amount), 0);
  const budget = draft?.budget_cents ?? null;
  const offBudget = budget !== null && total !== budget;

  if (!draft) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">
          Paste what the client sent. The AI splits it into milestones you can
          review and edit before anything is created.
        </p>
        <textarea
          rows={5}
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          className={inputCls}
          placeholder="Paste the client's email, message, or notes…"
        />
        <Button
          disabled={brief.trim().length < 30 || busy === "draft"}
          onClick={runDraft}
        >
          {busy === "draft" ? "Reading the brief…" : "Draft milestones"}
        </Button>
        {busy === "draft" && (
          <AiThinking label="Turning the brief into priced milestones…" />
        )}
        <ErrorText>{err}</ErrorText>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-md bg-guild-soft px-3 py-2 text-sm text-guild">
        <p>
          <span className="rounded bg-white/60 px-1.5 py-0.5 text-xs font-semibold">
            AI
          </span>{" "}
          {draft.summary}
        </p>
        <p className="mt-1 text-xs">{draft.pricing_basis}</p>
      </div>

      <ul className="space-y-3">
        {rows.map((r, i) => (
          <li key={i} className="rounded-md border border-line p-3">
            <div className="flex flex-wrap items-center gap-2">
              <input
                aria-label="Milestone title"
                value={r.title}
                onChange={(e) => edit(i, { title: e.target.value })}
                className={`${inputCls} min-w-[180px] flex-1`}
              />
              <label className="flex items-center gap-1 text-sm text-muted">
                $
                <input
                  aria-label="Amount in dollars"
                  inputMode="decimal"
                  value={r.amount}
                  onChange={(e) =>
                    edit(i, { amount: e.target.value.replace(/[^0-9.]/g, "") })
                  }
                  className={`${inputCls} w-28`}
                />
              </label>
              <button
                type="button"
                onClick={() => setRows((p) => p.filter((_, idx) => idx !== i))}
                className="text-sm text-alert hover:underline"
              >
                Remove
              </button>
            </div>
            <textarea
              aria-label="What's included"
              rows={2}
              value={r.scope}
              onChange={(e) => edit(i, { scope: e.target.value })}
              className={`${inputCls} mt-2`}
            />
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          Total <span className="font-semibold tabular-nums">{usd(total)}</span>
          {budget !== null && (
            <span className={offBudget ? "ml-2 text-alert" : "ml-2 text-muted"}>
              {offBudget
                ? `(client's budget is ${usd(budget)})`
                : "(matches the client's budget)"}
            </span>
          )}
        </p>
        <div className="flex gap-2">
          <Button
            variant="quiet"
            onClick={() => {
              setDraft(null);
              setRows([]);
            }}
          >
            Start over
          </Button>
          <Button
            disabled={rows.length === 0 || busy === "apply"}
            onClick={apply}
          >
            {busy === "apply"
              ? "Adding…"
              : `Add ${rows.length} milestone${rows.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      </div>
      <ErrorText>{err}</ErrorText>
    </div>
  );
}

/* ---------------- Scope creep ---------------- */

interface ScopeFlagRow {
  id: string;
  client_message: string;
  checked_by: string;
  reason: string;
  verdict: "in_scope" | "out_of_scope" | "unclear";
  suggested_title: string;
  suggested_scope: string;
  suggested_amount_cents: number;
  status: "flagged" | "noted" | "added" | "dismissed";
  created_at: string;
}

const VERDICT: Record<string, { label: string; cls: string }> = {
  in_scope: { label: "Already agreed", cls: "bg-guild-soft text-guild" },
  out_of_scope: { label: "New work", cls: "bg-seal-soft text-seal" },
  unclear: { label: "Unclear", cls: "bg-paper text-muted" },
};

const flagMeta = (f: ScopeFlagRow) =>
  [
    f.status === "added"
      ? "added as a milestone"
      : f.status === "dismissed"
        ? "done for free"
        : null,
    f.checked_by ? `checked by ${f.checked_by}` : null,
    timeAgo(f.created_at),
  ]
    .filter(Boolean)
    .join(", ");

function ScopeWatch({
  jobId,
  canDecide,
  onAdded,
}: {
  jobId: string;
  canDecide: boolean;
  onAdded: () => void;
}) {
  const { data: flags, mutate: refresh } = useSWR<ScopeFlagRow[]>(
    ["scope-flags", jobId],
    () => apiGet<ScopeFlagRow[]>(`/jobs/${jobId}/scope/flags`),
  );
  const [message, setMessage] = useState("");
  const [edits, setEdits] = useState<
    Record<string, { title: string; amount: string }>
  >({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(null);
    }
  }

  const editOf = (f: ScopeFlagRow) =>
    edits[f.id] ?? {
      title: f.suggested_title,
      amount: (f.suggested_amount_cents / 100).toFixed(2),
    };
  const setEdit = (
    f: ScopeFlagRow,
    patch: Partial<{ title: string; amount: string }>,
  ) => setEdits((prev) => ({ ...prev, [f.id]: { ...editOf(f), ...patch } }));

  const open = (flags ?? []).filter((f) => f.status === "flagged");
  const history = (flags ?? []).filter((f) => f.status !== "flagged");

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Paste what the client just asked for. The AI checks it against the
        agreed milestones and flags anything that should be paid extra.
      </p>
      <textarea
        rows={3}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        className={inputCls}
        placeholder="Paste the client's latest message…"
      />
      <Button
        disabled={message.trim().length < 15 || !!busy}
        onClick={() =>
          act("check", async () => {
            await apiPost(`/jobs/${jobId}/scope/check`, { message });
            setMessage("");
          })
        }
      >
        {busy === "check" ? "Checking…" : "Check against scope"}
      </Button>
      {busy === "check" && (
        <div className="mt-3">
          <AiThinking label="Checking the message against the agreed scope…" />
        </div>
      )}
      <ErrorText>{err}</ErrorText>

      {open.map((f) => {
        const e = editOf(f);
        return (
          <div
            key={f.id}
            className="rounded-md border border-seal/30 bg-seal-soft/40 p-4"
          >
            <p className="text-xs text-muted">
              <span
                className={`rounded px-1.5 py-0.5 font-semibold ${VERDICT[f.verdict].cls}`}
              >
                {VERDICT[f.verdict].label}
              </span>{" "}
              {flagMeta(f)}
            </p>
            <blockquote className="mt-2 border-l-2 border-line pl-3 text-sm">
              {f.client_message}
            </blockquote>
            <p className="mt-2 text-sm">
              <span className="font-semibold text-guild">AI:</span> {f.reason}
            </p>

            <div className="mt-3 rounded-md border border-line bg-white p-3">
              <p className="text-xs text-muted">
                Suggested add-on. Edit before adding if you like.
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  aria-label="Add-on title"
                  value={e.title}
                  disabled={!canDecide}
                  onChange={(ev) => setEdit(f, { title: ev.target.value })}
                  className={`${inputCls} min-w-[180px] flex-1`}
                />
                <label className="flex items-center gap-1 text-sm text-muted">
                  $
                  <input
                    aria-label="Add-on price"
                    inputMode="decimal"
                    value={e.amount}
                    disabled={!canDecide}
                    onChange={(ev) =>
                      setEdit(f, {
                        amount: ev.target.value.replace(/[^0-9.]/g, ""),
                      })
                    }
                    className={`${inputCls} w-28`}
                  />
                </label>
              </div>
              {f.suggested_scope && (
                <p className="mt-2 text-sm text-muted">{f.suggested_scope}</p>
              )}
            </div>

            {canDecide ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  disabled={!!busy}
                  onClick={() =>
                    act(`add-${f.id}`, async () => {
                      await apiPost(`/jobs/${jobId}/scope/flags/${f.id}/add`, {
                        title: e.title.trim(),
                        amount_cents: Math.round(
                          parseFloat(e.amount || "0") * 100,
                        ),
                      });
                      onAdded();
                    })
                  }
                >
                  {busy === `add-${f.id}` ? "Adding…" : "Add as paid milestone"}
                </Button>
                <Button
                  variant="quiet"
                  disabled={!!busy}
                  onClick={() =>
                    act(`dismiss-${f.id}`, () =>
                      apiPost(
                        `/jobs/${jobId}/scope/flags/${f.id}/dismiss`,
                      ).then(() => {}),
                    )
                  }
                >
                  {busy === `dismiss-${f.id}`
                    ? "Dismissing…"
                    : "Do it for free"}
                </Button>
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted">
                The job&apos;s poster or a guild admin decides whether to charge
                for this.
              </p>
            )}
          </div>
        );
      })}

      {history.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer rounded-sm text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40">
            Earlier checks ({history.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {history.map((f) => (
              <li
                key={f.id}
                className="rounded-md border border-line bg-paper p-3"
              >
                <p className="text-xs text-muted">
                  <span
                    className={`rounded px-1.5 py-0.5 font-semibold ${VERDICT[f.verdict].cls}`}
                  >
                    {VERDICT[f.verdict].label}
                  </span>{" "}
                  {flagMeta(f)}
                </p>
                <p className="mt-1">{f.reason}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}