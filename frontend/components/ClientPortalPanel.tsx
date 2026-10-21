"use client";

import { useState } from "react";
import useSWR, { mutate as refreshKey } from "swr";
import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Button, ErrorText, Panel, inputCls } from "@/components/ui";

type Stage = "in_progress" | "review" | "changes_requested" | "approved" | "payment_due" | "paid";

interface Row {
  id: string;
  title: string;
  stage: Stage;
  delivered_at: string | null;
  approved_at: string | null;
  feedback: string;
  locked: boolean;
  in_agreement: boolean;
}

interface SignedRow {
  kind: "work" | "amendment";
  signer: string;
  accepted_at: string;
  hash: string;
}

interface FullAgreement {
  accepted: (SignedRow & { body: string; email: string })[];
}

interface Status {
  agreement: { needs_signature: boolean; new_titles: string[]; signed: SignedRow[] };
  enabled: boolean;
  path: string;
  created_at: string | null;
  can_manage: boolean;
  can_deliver: boolean;
  milestones: Row[];
}

const LABEL: Record<Stage, { text: string; cls: string }> = {
  in_progress: { text: "Working on it", cls: "bg-paper text-muted" },
  review: { text: "Waiting for client", cls: "bg-seal-soft text-seal" },
  changes_requested: { text: "Client wants changes", cls: "bg-alert-soft text-alert" },
  approved: { text: "Client approved", cls: "bg-guild-soft text-guild" },
  payment_due: { text: "Invoice sent", cls: "bg-seal-soft text-seal" },
  paid: { text: "Paid", cls: "bg-guild-soft text-guild" },
};

export function ClientPortalPanel({ jobId, onScopeFlag }: { jobId: string; onScopeFlag?: () => void }) {
  const key = ["client-portal", jobId];
  const { data, mutate } = useSWR<Status>(key, () => apiGet<Status>(`/jobs/${jobId}/portal`), {
    refreshInterval: 15_000,
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [delivering, setDelivering] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [showText, setShowText] = useState(false);
  const { data: full } = useSWR<FullAgreement>(showText ? ["job-agreement", jobId] : null, () =>
    apiGet<FullAgreement>(`/jobs/${jobId}/agreement`),
  );

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    setErr(null);
    try {
      await fn();
      await mutate();
      refreshKey(["milestones", jobId]); // so "Send invoice" on the job page updates too
      return true;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    if (!data?.path) return;
    await navigator.clipboard.writeText(`${window.location.origin}${data.path}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  if (!data) return null;
  const hasFeedback = data.milestones.some((m) => m.feedback);
  const ag = data.agreement;
  const lastSigned = ag.signed[ag.signed.length - 1];
  const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <Panel
      title="Client page"
      action={
        data.can_manage ? (
          data.enabled ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={copy}>{copied ? "Link copied" : "Copy client link"}</Button>
              <Button
                variant="quiet"
                disabled={!!busy}
                onClick={() => {
                  if (window.confirm("Make a new link? The old one stops working right away."))
                    run("rotate", () => apiPost(`/jobs/${jobId}/portal/rotate`, {}));
                }}
              >
                New link
              </Button>
              <Button
                variant="quiet"
                disabled={!!busy}
                onClick={() => {
                  if (window.confirm("Turn off the client page? The link stops working."))
                    run("off", () => apiDelete(`/jobs/${jobId}/portal`));
                }}
              >
                Turn off
              </Button>
            </div>
          ) : (
            <Button disabled={!!busy} onClick={() => run("on", () => apiPost(`/jobs/${jobId}/portal/enable`, {}))}>
              {busy === "on" ? "Creating…" : "Create client link"}
            </Button>
          )
        ) : undefined
      }
    >
      <p className="text-sm text-muted">
        {data.enabled
          ? `The client can follow progress, approve work and ask for changes. No login needed. Link made ${data.created_at ? timeAgo(data.created_at) : ""}.`
          : "Give the client one private link to follow progress, approve work and ask for changes. It's also added to every invoice email."}
      </p>

      {data.milestones.length > 0 && (
        <div
          className={`mt-3 rounded-lg px-3 py-2 text-sm ${ag.needs_signature ? "border border-seal/30 bg-seal-soft/50" : "bg-guild-soft/60"}`}
        >
          {ag.needs_signature ? (
            <p>
              <span className="font-medium text-seal">
                {lastSigned ? "New work needs the client's OK: " : "Waiting for the client to accept the work agreement. "}
              </span>
              {lastSigned
                ? `${ag.new_titles.join(", ")}.`
                : "Invoices and deposit holds unlock once they accept it on the client page."}
            </p>
          ) : lastSigned ? (
            <p className="flex flex-wrap items-center justify-between gap-2">
              <span>
                <span className="font-medium text-guild-deep">Agreement accepted</span>{" "}
                <span className="text-muted">by {lastSigned.signer} on {day(lastSigned.accepted_at)}.</span>
              </span>
              <button className="text-xs font-medium text-guild-deep hover:underline" onClick={() => setShowText((s) => !s)}>
                {showText ? "Hide agreement" : "View agreement"}
              </button>
            </p>
          ) : null}
          {showText && full?.accepted?.length ? (
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-white p-3 font-sans text-xs leading-relaxed">
              {full.accepted[full.accepted.length - 1].body}
              {`\n\nAccepted by ${full.accepted[full.accepted.length - 1].signer} (${full.accepted[full.accepted.length - 1].email}). SHA-256: ${full.accepted[full.accepted.length - 1].hash}`}
            </pre>
          ) : null}
        </div>
      )}

      {data.milestones.length > 0 && (
        <ul className="mt-4 divide-y divide-line">
          {data.milestones.map((m) => {
            const l = LABEL[m.stage];
            const canDeliver = data.can_deliver && !m.locked && m.stage !== "approved" && m.stage !== "review";
            return (
              <li key={m.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="font-medium">{m.title}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${l.cls}`}>{l.text}</span>
                    {!m.in_agreement && !m.locked && m.stage !== "payment_due" && (
                      <span className="rounded-full border border-dashed border-seal/40 px-2 py-0.5 text-xs text-seal">
                        Not agreed yet
                      </span>
                    )}
                  </div>
                  {canDeliver && delivering !== m.id && (
                    <Button variant="quiet" onClick={() => { setDelivering(m.id); setNote(""); }}>
                      {m.delivered_at ? "Deliver again" : m.stage === "payment_due" ? "Add delivery note" : "Mark as delivered"}
                    </Button>
                  )}
                </div>
                {m.feedback && (
                  <p className="mt-2 rounded-lg bg-alert-soft/50 px-3 py-2 text-sm">
                    <span className="font-medium">Client:</span> {m.feedback}
                  </p>
                )}
                {delivering === m.id && (
                  <div className="mt-2 space-y-2">
                    <textarea
                      rows={2}
                      value={note}
                      maxLength={1500}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="What did you deliver? Links, files, what changed. The client sees this."
                      className={inputCls}
                    />
                    <div className="flex gap-2">
                      <Button
                        disabled={!!busy}
                        onClick={async () => {
                          const ok = await run(`d-${m.id}`, () =>
                            apiPost(`/jobs/${jobId}/milestones/${m.id}/delivered`, { note }),
                          );
                          if (ok) setDelivering(null);
                        }}
                      >
                        {busy === `d-${m.id}` ? "Saving…" : "Send to client"}
                      </Button>
                      <Button variant="quiet" onClick={() => setDelivering(null)}>Cancel</Button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {hasFeedback && onScopeFlag && (
        <p className="mt-3 text-xs text-muted">
          The AI checks every client request against the agreed scope. New work shows up as a flag below.{" "}
          <button className="underline hover:text-ink" onClick={onScopeFlag}>Refresh flags</button>
        </p>
      )}
      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}

