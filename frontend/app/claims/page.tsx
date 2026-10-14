"use client";

import useSWR from "swr";
import { useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useMe } from "@/lib/useMe";
import { useMembers } from "@/lib/useGuild";
import { Button, ErrorText, PageHeader, StatusPill, inputCls } from "@/components/ui";

interface Claim {
  id: string; member_id: string; status: string; statement: string; evidence_urls: string[];
  ai_verdict: string; ai_confidence: number; ai_reason: string;
  admin_decision: string; admin_note: string; created_at: string;
}

const VERDICT: Record<string, string> = {
  approve: "text-guild", reject: "text-alert", needs_more_info: "text-seal",
};

export default function ClaimsPage() {
  const { me } = useMe();
  const isAdmin = me?.role === "admin";
  const { data: members } = useMembers(me?.guild_id);
  const { data, mutate, error } = useSWR<Claim[]>(me ? ["claims", isAdmin] : null,
    () => apiGet<Claim[]>(isAdmin ? "/claims" : "/claims/mine"));

  return (
    <div className="space-y-6">
      <PageHeader
        title={isAdmin ? "Claims to review" : "Your claims"}
        description="When a client never pays, the worker can ask the safety pool to cover part of the invoice. The AI reviews every claim first. A person always decides."
      />
      {error && <ErrorText>{error.message}</ErrorText>}
      {data?.length === 0 && (
        <div className="rounded-xl border border-dashed border-line bg-white px-6 py-10 text-center">
          <p className="font-medium">No claims</p>
          <p className="mt-1 text-sm text-muted">Nobody has been ghosted yet. If a client stops paying, open the job and choose "Client isn't paying".</p>
        </div>
      )}
      {(data ?? []).map((c) => (
        <ClaimCard key={c.id} c={c} isAdmin={!!isAdmin} meId={me?.id}
          memberName={members?.find((m) => m.id === c.member_id)?.name ?? "A member"} onChange={() => mutate()} />
      ))}
    </div>
  );
}

function ClaimCard({ c, isAdmin, meId, memberName, onChange }:
  { c: Claim; isAdmin: boolean; meId?: string; memberName: string; onChange: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const open = c.status === "ai_reviewed" || c.status === "submitted";
  const canDecide = isAdmin && open && c.member_id !== meId;

  async function act(path: string, body?: unknown) {
    setBusy(true); setErr(null);
    try { await apiPost(path, body); setNote(""); onChange(); }
    catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong"); }
    finally { setBusy(false); }
  }

  return (
    <article className="rounded-xl border border-line bg-white p-5 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">{memberName} <span className="font-normal text-muted">filed {timeAgo(c.created_at)}</span></p>
        <StatusPill status={c.status} />
      </header>

      <blockquote className="mt-3 max-w-prose border-l-2 border-line pl-3 text-sm leading-relaxed">{c.statement}</blockquote>
      {c.evidence_urls.length > 0 && <p className="mt-2 text-xs text-muted">Evidence: {c.evidence_urls.join(", ")}</p>}

      {c.ai_verdict && (
        <div className="mt-4 rounded-lg bg-paper p-4 text-sm">
          <p>
            <span className="rounded bg-guild-soft px-1.5 py-0.5 text-xs font-semibold text-guild">AI</span>{" "}
            recommends <span className={`font-semibold ${VERDICT[c.ai_verdict] ?? ""}`}>{c.ai_verdict.replaceAll("_", " ")}</span>
            <span className="text-muted">, {Math.round(c.ai_confidence * 100)}% confident</span>
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
            {c.ai_reason.split(" | ").map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {c.admin_note && <p className="mt-3 text-sm"><span className="font-medium">Admin note:</span> {c.admin_note}</p>}

      {canDecide && (
        <div className="mt-4 space-y-2">
          <input value={note} onChange={(e) => setNote(e.target.value)} className={inputCls}
            placeholder={c.ai_verdict === "approve" ? "Note (required only if you reject)" : "Note (required to approve, since the AI didn't)"} />
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => act(`/claims/${c.id}/decide`, { decision: "approve", note })}>
              {busy ? "Working…" : "Approve and pay from pool"}
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => act(`/claims/${c.id}/decide`, { decision: "reject", note })}>Reject</Button>
            <Button variant="quiet" disabled={busy} onClick={() => act(`/claims/${c.id}/review`)}>Ask AI again</Button>
          </div>
        </div>
      )}
      <ErrorText>{err}</ErrorText>
    </article>
  );
}