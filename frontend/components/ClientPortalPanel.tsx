"use client";

import { useState } from "react";
import useSWR from "swr";
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
}

interface Status {
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

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    setErr(null);
    try {
      await fn();
      await mutate();
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
                  </div>
                  {canDeliver && delivering !== m.id && (
                    <Button variant="quiet" onClick={() => { setDelivering(m.id); setNote(""); }}>
                      {m.delivered_at ? "Deliver again" : "Mark as delivered"}
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
