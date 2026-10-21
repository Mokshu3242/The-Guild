"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import { usd } from "@/lib/format";
import { Button, ErrorText, Notice, Panel, inputCls } from "@/components/ui";

interface Row {
  id: string;
  member: string;
  is_me: boolean;
  job_id: string;
  client: string;
  milestone: string;
  invoice_cents: number;
  advance_cents: number;
  fee_cents: number;
  status: string;
  explanation: string;
  explained_by: string;
  decided_by: string;
  decision_note: string;
  created_at: string;
  paid_at: string | null;
  due_at: string | null;
  blocks: string[];
}
interface Data {
  advances: Row[];
  pending: number;
}

const LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: "Waiting", cls: "text-muted" },
  paid: { text: "Paid early", cls: "text-ink" },
  repaid: { text: "Paid back", cls: "text-guild" },
  declined: { text: "Declined", cls: "text-muted" },
  defaulted: { text: "Moved to debt", cls: "text-alert" },
  converted: { text: "Moved to debt", cls: "text-muted" },
};
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** 12B. Admins approve requests here. Members see their own advances. */
export function AdvancesPanel({ isAdmin }: { isAdmin: boolean }) {
  const { data, mutate } = useSWR<Data>("advances", () => apiGet<Data>("/advances"), { refreshInterval: 15000 });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  if (!data || data.advances.length === 0) return null;
  const pending = data.advances.filter((a) => a.status === "pending");
  const rest = data.advances.filter((a) => a.status !== "pending");

  async function act(a: Row, action: "approve" | "decline") {
    setBusy(`${action}-${a.id}`);
    setErr(null);
    setNotice(null);
    try {
      await apiPost(`/advances/${a.id}/${action}`, action === "decline" ? { note: notes[a.id] ?? "" } : undefined);
      setNotice(action === "approve" ? `${usd(a.advance_cents)} sent to ${a.member}'s PayPal.` : "Request declined.");
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
    <Panel title={isAdmin ? "Paid on day one" : "Your early payments"}>
      <p className="text-sm text-muted">
        Members can be paid part of an approved invoice right away. The pool gets it back, plus a 2% fee, when the
        client pays.
      </p>

      {pending.length > 0 && (
        <ul className="mt-4 space-y-3">
          {pending.map((a) => (
            <li key={a.id} className="rounded-lg border border-line p-4 text-sm">
              <p>
                <span className="font-medium">{a.member}</span> asks for {usd(a.advance_cents)} now on{" "}
                <Link href={`/jobs/view/?id=${a.job_id}`} className="underline-offset-2 hover:underline">
                  {a.client} · {a.milestone}
                </Link>{" "}
                <span className="text-muted">
                  ({usd(a.invoice_cents)} invoice, {usd(a.fee_cents)} fee)
                </span>
              </p>
              <p className="mt-2">
                <span className="mr-1.5 rounded bg-guild-soft px-1.5 py-0.5 text-xs font-medium text-guild">
                  {a.explained_by === "ai" ? "AI note" : "Rules"}
                </span>
                {a.explanation}
              </p>
              {a.blocks.length > 0 && (
                <p className="mt-2 text-alert">Can&apos;t pay it now: {a.blocks[0]}</p>
              )}
              {isAdmin && !a.is_me && (
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <Button disabled={!!busy || a.blocks.length > 0} onClick={() => act(a, "approve")} className="shrink-0">
                    {busy === `approve-${a.id}` ? "Paying…" : `Pay ${usd(a.advance_cents)} now`}
                  </Button>
                  <input
                    value={notes[a.id] ?? ""}
                    onChange={(e) => setNotes({ ...notes, [a.id]: e.target.value })}
                    maxLength={500}
                    placeholder="Why not? (optional)"
                    className={inputCls}
                  />
                  <Button variant="quiet" disabled={!!busy} onClick={() => act(a, "decline")} className="shrink-0">
                    Decline
                  </Button>
                </div>
              )}
              {isAdmin && a.is_me && (
                <p className="mt-2 text-muted">This is your own request, so another admin has to approve it.</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {rest.length > 0 && (
        <ul className="mt-4 divide-y divide-line">
          {rest.map((a) => {
            const l = LABEL[a.status] ?? { text: a.status, cls: "text-muted" };
            return (
              <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2.5 text-sm">
                <span>
                  {isAdmin && <span className="font-medium">{a.member} · </span>}
                  {usd(a.advance_cents)} on {a.client} · {a.milestone}
                  {a.status === "paid" && a.due_at && (
                    <span className="text-muted"> · back by {day(a.due_at)}</span>
                  )}
                </span>
                <span className={`text-xs font-medium ${l.cls}`}>{l.text}</span>
              </li>
            );
          })}
        </ul>
      )}

      <ErrorText>{err}</ErrorText>
      {notice && <Notice>{notice}</Notice>}
    </Panel>
  );
}
