"use client";

import { Suspense, useState } from "react";
import useSWR from "swr";
import { useSearchParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { usd } from "@/lib/format";

// Same base URL the rest of the app uses (see lib/api.ts). The portal is public, so no auth header.
const API = process.env.NEXT_PUBLIC_API_URL ?? "";

type Stage = "in_progress" | "review" | "changes_requested" | "approved" | "payment_due" | "paid";

interface Ms {
  id: string;
  title: string;
  scope: string;
  amount_cents: number;
  stage: Stage;
  can_review: boolean;
  delivered_at: string | null;
  delivery_note: string;
  approved_at: string | null;
  feedback: string;
  invoice: { status: string; pay_url: string; days_open: number } | null;
  deposit: { state: "needs_approval" | "on_hold"; amount_cents: number; approve_url: string } | null;
}

interface View {
  guild_name: string;
  client_name: string;
  worker_name: string;
  description: string;
  total_cents: number;
  paid_cents: number;
  milestones: Ms[];
}

const STAGE: Record<Stage, { label: string; cls: string }> = {
  in_progress: { label: "In progress", cls: "bg-paper text-muted" },
  review: { label: "Ready for your review", cls: "bg-seal-soft text-seal" },
  changes_requested: { label: "Changes requested", cls: "bg-seal-soft text-seal" },
  approved: { label: "Approved", cls: "bg-guild-soft text-guild" },
  payment_due: { label: "Payment due", cls: "bg-seal-soft text-seal" },
  paid: { label: "Paid", cls: "bg-guild-soft text-guild" },
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json" },
    referrerPolicy: "no-referrer",
  });
  if (!res.ok) {
    let msg = res.status === 404 ? "This link is not active anymore." : `Something went wrong (${res.status}).`;
    try {
      const d = await res.json();
      if (typeof d?.detail === "string") msg = d.detail;
    } catch {
      /* keep default */
    }
    throw new Error(msg);
  }
  return res.json();
}

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function Page() {
  return (
    <Suspense fallback={<Shell><p className="text-muted">Loading your project…</p></Shell>}>
      <Portal />
    </Suspense>
  );
}

function Shell({ children, guild }: { children: React.ReactNode; guild?: string }) {
  return (
    <main className="min-h-screen bg-paper">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-4 sm:px-6">
          <Logo className="h-8 w-auto" title="The Guild" />
          <span className="text-sm text-muted">{guild ? `${guild} · client page` : "Client page"}</span>
        </div>
      </header>
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">{children}</div>
    </main>
  );
}

function Portal() {
  const token = useSearchParams().get("t") ?? "";
  const key = token ? ["portal", token] : null;
  const { data, error, mutate } = useSWR<View>(key, () => call<View>(`/portal/${token}`), {
    shouldRetryOnError: false,
    revalidateOnFocus: true,
  });

  if (!token) return <Shell><p className="text-muted">This link is missing a part. Please open it again from your email.</p></Shell>;
  if (error) return <Shell><p className="text-muted">{error.message}</p></Shell>;
  if (!data) return <Shell><p className="text-muted">Loading your project…</p></Shell>;

  const pct = data.total_cents ? Math.round((data.paid_cents / data.total_cents) * 100) : 0;

  return (
    <Shell guild={data.guild_name}>
      <p className="text-sm text-muted">Hi {data.client_name}</p>
      <h1 className="mt-1 font-display text-3xl font-bold tracking-tight">Your project</h1>
      <p className="mt-3 leading-relaxed">{data.description}</p>
      {data.worker_name && (
        <p className="mt-2 text-sm text-muted">
          Done by <span className="font-medium text-ink">{data.worker_name}</span> from {data.guild_name}
        </p>
      )}

      {data.total_cents > 0 && (
        <div className="mt-6 rounded-xl border border-line bg-white p-5">
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-muted">Paid so far</span>
            <span className="tabular-nums">
              <span className="font-semibold">{usd(data.paid_cents)}</span>
              <span className="text-muted"> of {usd(data.total_cents)}</span>
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-paper">
            <div className="h-full rounded-full bg-guild transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      <h2 className="mt-8 font-display text-xl font-semibold">Milestones</h2>
      {data.milestones.length === 0 && (
        <p className="mt-2 text-sm text-muted">The plan for this project is still being written.</p>
      )}
      <ul className="mt-3 space-y-4">
        {data.milestones.map((m) => (
          <MilestoneCard key={m.id} m={m} token={token} onChange={(v) => mutate(v, { revalidate: false })} />
        ))}
      </ul>

      <p className="mt-10 text-center text-xs text-muted">
        Payments are handled by PayPal. This page is private to you. Please don&apos;t share the link.
      </p>
    </Shell>
  );
}

function MilestoneCard({ m, token, onChange }: { m: Ms; token: string; onChange: (v: View) => void }) {
  const [mode, setMode] = useState<"idle" | "changes">("idle");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const s = STAGE[m.stage];

  async function act(path: string, body: unknown) {
    setBusy(true);
    setErr(null);
    try {
      onChange(await call<View>(`/portal/${token}/milestones/${m.id}/${path}`, { method: "POST", body: JSON.stringify(body) }));
      setMode("idle");
      setText("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-xl border border-line bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{m.title}</p>
          {m.scope && <p className="mt-1 text-sm text-muted">{m.scope}</p>}
        </div>
        <div className="text-right">
          <p className="font-semibold tabular-nums">{usd(m.amount_cents)}</p>
          <span className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>
        </div>
      </div>

      {m.delivered_at && (
        <div className="mt-4 rounded-lg bg-paper px-4 py-3 text-sm">
          <p className="text-xs text-muted">Delivered {day(m.delivered_at)}</p>
          {m.delivery_note && <p className="mt-1 whitespace-pre-line">{m.delivery_note}</p>}
        </div>
      )}

      {m.feedback && (
        <p className="mt-3 text-sm text-muted">
          <span className="font-medium text-ink">You asked for:</span> {m.feedback}
        </p>
      )}
      {m.approved_at && <p className="mt-3 text-sm text-guild">You approved this on {day(m.approved_at)}. Thank you.</p>}

      {m.deposit?.state === "needs_approval" && m.deposit.approve_url && (
        <PayBox
          text={`A deposit of ${usd(m.deposit.amount_cents)} is requested. PayPal holds it, and it's only taken once you have the work.`}
          href={m.deposit.approve_url}
          cta="Hold deposit with PayPal"
        />
      )}
      {m.deposit?.state === "on_hold" && (
        <p className="mt-3 text-sm text-muted">Deposit of {usd(m.deposit.amount_cents)} is on hold with PayPal.</p>
      )}
      {m.stage === "payment_due" && m.invoice?.pay_url && (
        <PayBox
          text={m.invoice.days_open > 0 ? `Invoice sent ${m.invoice.days_open} days ago.` : "Invoice sent today."}
          href={m.invoice.pay_url}
          cta="Pay with PayPal"
        />
      )}

      {m.can_review && mode === "idle" && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            disabled={busy}
            onClick={() => act("approve", {})}
            className="rounded-lg bg-guild px-4 py-2 text-sm font-medium text-white hover:bg-guild-deep disabled:opacity-50"
          >
            {busy ? "Saving…" : "Approve this work"}
          </button>
          <button
            disabled={busy}
            onClick={() => setMode("changes")}
            className="rounded-lg border border-line bg-white px-4 py-2 text-sm font-medium hover:bg-paper"
          >
            Ask for changes
          </button>
        </div>
      )}

      {mode === "changes" && (
        <div className="mt-4 space-y-2">
          <textarea
            rows={3}
            value={text}
            maxLength={1500}
            onChange={(e) => setText(e.target.value)}
            placeholder="What would you like changed? Be as specific as you can."
            className="w-full rounded-lg border border-line px-3 py-2 text-sm focus:border-guild focus:outline-none"
          />
          <div className="flex items-center gap-3">
            <button
              disabled={busy || text.trim().length < 15}
              onClick={() => act("changes", { feedback: text })}
              className="rounded-lg bg-guild px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? "Sending…" : "Send"}
            </button>
            <button onClick={() => setMode("idle")} className="text-sm text-muted hover:text-ink">
              Cancel
            </button>
            {text.trim().length > 0 && text.trim().length < 15 && (
              <span className="text-xs text-muted">A little more detail, please.</span>
            )}
          </div>
        </div>
      )}

      {err && <p className="mt-3 text-sm text-alert">{err}</p>}
    </li>
  );
}

function PayBox({ text, href, cta }: { text: string; href: string; cta: string }) {
  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-seal/20 bg-seal-soft/40 px-4 py-3">
      <p className="text-sm">{text}</p>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="rounded-lg bg-guild-deep px-4 py-2 text-sm font-medium text-white hover:bg-guild"
      >
        {cta}
      </a>
    </div>
  );
}
