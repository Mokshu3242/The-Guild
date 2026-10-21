"use client";

import { Suspense } from "react";
import useSWR from "swr";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiGet } from "@/lib/api";
import { usd } from "@/lib/format";
import { Button, ErrorText, Skeleton } from "@/components/ui";

interface Ev {
  generated_at: string;
  guild: string;
  job: {
    id: string;
    client_name: string;
    client_email: string;
    description: string;
    status: string;
    created_at: string;
    worker: string;
    referrer: string;
  };
  agreements: {
    kind: string;
    template: string;
    signer: string;
    email: string;
    accepted_at: string;
    ip: string;
    sha256: string;
    hash_matches: boolean;
    milestones: number;
    total_cents: number;
    body: string;
  }[];
  milestones: {
    title: string;
    scope: string;
    amount_cents: number;
    status: string;
    created_at: string | null;
    delivered_at: string | null;
    delivery_note: string;
    approved_at: string | null;
    approved_by: string;
    changes_requested_at: string | null;
    client_feedback: string;
    invoices: {
      paypal_invoice_id: string;
      amount_cents: number;
      status: string;
      sent_at: string | null;
      paid_at: string | null;
      reminders: { tier: number; sent_at: string | null; subject: string; days_overdue: number }[];
    }[];
    deposits: {
      status: string;
      amount_cents: number;
      paypal_order_id: string;
      paypal_authorization_id: string;
      paypal_capture_id: string;
      authorized_at: string | null;
      captured_at: string | null;
      voided_at: string | null;
    }[];
  }[];
  payouts: { to: string; kind: string; amount_cents: number; status: string; paypal_batch_id: string; at: string }[];
  claims: {
    status: string;
    filed_at: string;
    by: string;
    ai_verdict: string;
    ai_confidence: number;
    admin_decision: string;
    admin_note: string;
  }[];
  timeline: { at: string; action: string; inputs: Record<string, unknown>; result: Record<string, unknown> }[];
}

const when = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "Not yet";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <Evidence />
    </Suspense>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-3 py-1 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid rounded-xl border border-line bg-white p-5 print:rounded-none print:border-0 print:border-t print:p-0 print:pt-4">
      <h2 className="font-display text-lg font-semibold">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Evidence() {
  const id = useSearchParams().get("id") ?? "";
  const { data, error } = useSWR<Ev>(id ? ["evidence", id] : null, () => apiGet<Ev>(`/jobs/${id}/evidence`), {
    revalidateOnFocus: false,
  });

  if (error) return <ErrorText>{error.message}</ErrorText>;
  if (!data) return <Skeleton className="h-64" />;
  const j = data.job;

  return (
    <div className="mx-auto max-w-3xl space-y-5 print:max-w-none print:space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href={`/jobs/view/?id=${j.id}`} className="text-sm text-muted hover:text-ink">
          Back to the job
        </Link>
        <Button onClick={() => window.print()}>Print or save as PDF</Button>
      </div>

      <header>
        <p className="text-sm text-muted">{data.guild} · Evidence pack</p>
        <h1 className="mt-1 font-display text-3xl font-bold tracking-tight">{j.client_name}</h1>
        <p className="mt-1 text-sm text-muted">
          Made {when(data.generated_at)} from The Guild&apos;s records. Facts only, no AI.
        </p>
      </header>

      <Section title="The job">
        <dl>
          <Row label="Client">{j.client_name} ({j.client_email})</Row>
          <Row label="Done by">{j.worker || "Not assigned"}</Row>
          <Row label="Brought in by">{j.referrer}</Row>
          <Row label="Posted">{when(j.created_at)}</Row>
          <Row label="Status">{j.status.replaceAll("_", " ")}</Row>
          <Row label="What was asked">{j.description}</Row>
        </dl>
      </Section>

      <Section title="Agreements">
        {data.agreements.length === 0 && <p className="text-sm text-muted">No work agreement was accepted for this job.</p>}
        <div className="space-y-4">
          {data.agreements.map((a, i) => (
            <div key={i} className="rounded-lg border border-line p-4 print:border-0 print:p-0">
              <dl>
                <Row label="Type">{a.kind === "amendment" ? "Update (new work added)" : "Work agreement"} · {a.template}</Row>
                <Row label="Accepted by">
                  {a.signer} ({a.email})
                </Row>
                <Row label="When">{when(a.accepted_at)}</Row>
                <Row label="From IP">{a.ip || "Not recorded"}</Row>
                <Row label="Covers">
                  {a.milestones} milestone{a.milestones === 1 ? "" : "s"}, {usd(a.total_cents)}
                </Row>
                <Row label="Fingerprint">
                  <span className="font-mono text-xs">{a.sha256}</span>{" "}
                  <span className={a.hash_matches ? "text-guild" : "font-medium text-alert"}>
                    {a.hash_matches ? "matches the text below" : "does NOT match the text below"}
                  </span>
                </Row>
              </dl>
              <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-paper p-3 font-sans text-xs leading-relaxed print:max-h-none print:bg-transparent print:p-0">
                {a.body}
              </pre>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Milestones">
        <div className="space-y-4">
          {data.milestones.map((m, i) => (
            <div key={i} className="break-inside-avoid rounded-lg border border-line p-4 print:border-0 print:p-0">
              <p className="font-medium">
                {m.title} <span className="font-normal tabular-nums text-muted">{usd(m.amount_cents)}</span>
              </p>
              {m.scope && <p className="text-sm text-muted">{m.scope}</p>}
              <dl className="mt-2">
                <Row label="Delivered">{when(m.delivered_at)}</Row>
                {m.delivery_note && <Row label="Delivery note">{m.delivery_note}</Row>}
                {m.changes_requested_at && (
                  <Row label="Changes asked">
                    {when(m.changes_requested_at)}
                    {m.client_feedback ? `: "${m.client_feedback}"` : ""}
                  </Row>
                )}
                <Row label="Approved">
                  {m.approved_at
                    ? `${when(m.approved_at)}${m.approved_by === "silence" ? " (no reply within 5 business days)" : " by the client"}`
                    : "Not yet"}
                </Row>
                {m.deposits.map((d, k) => (
                  <Row key={`d${k}`} label="Deposit hold">
                    {usd(d.amount_cents)}, {d.status}. Order {d.paypal_order_id || "none"}
                    {d.paypal_authorization_id ? `, authorization ${d.paypal_authorization_id}` : ""}
                    {d.paypal_capture_id ? `, capture ${d.paypal_capture_id}` : ""}
                  </Row>
                ))}
                {m.invoices.map((inv, k) => (
                  <Row key={`i${k}`} label="Invoice">
                    {usd(inv.amount_cents)}, {inv.status}. PayPal {inv.paypal_invoice_id}. Sent {when(inv.sent_at)}
                    {inv.paid_at ? `, paid ${when(inv.paid_at)}` : ""}.
                    {inv.reminders.length > 0 && (
                      <ul className="mt-1 list-disc pl-5 text-muted">
                        {inv.reminders.map((r) => (
                          <li key={r.tier}>
                            Reminder {r.tier} of 3, {when(r.sent_at)}, {r.days_overdue} days after sending: &quot;{r.subject}&quot;
                          </li>
                        ))}
                      </ul>
                    )}
                  </Row>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </Section>

      {(data.payouts.length > 0 || data.claims.length > 0) && (
        <Section title="Money out">
          <ul className="space-y-1 text-sm">
            {data.payouts.map((p, i) => (
              <li key={i}>
                {when(p.at)}: {usd(p.amount_cents)} to {p.to} ({p.kind}), {p.status}
                {p.paypal_batch_id ? `. PayPal batch ${p.paypal_batch_id}` : ""}
              </li>
            ))}
            {data.claims.map((c, i) => (
              <li key={`c${i}`}>
                Claim by {c.by}, filed {when(c.filed_at)}: {c.status}. AI said {c.ai_verdict.replaceAll("_", " ") || "nothing yet"}
                {c.ai_confidence ? ` (${Math.round(c.ai_confidence * 100)}% sure)` : ""}. Admin: {c.admin_decision}
                {c.admin_note ? `, "${c.admin_note}"` : ""}.
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Timeline">
        <ol className="space-y-1 text-sm">
          {data.timeline.map((t, i) => (
            <li key={i} className="grid grid-cols-[10rem_1fr] gap-3">
              <span className="text-muted">{when(t.at)}</span>
              <span className="font-mono text-xs leading-5">{t.action}</span>
            </li>
          ))}
        </ol>
      </Section>

      <p className="pb-6 text-xs text-muted">
        Each fingerprint is a SHA-256 hash of the exact agreement text. If anyone changed the text after it was accepted,
        the fingerprint would no longer match.
      </p>
    </div>
  );
}
