"use client";

import useSWR from "swr";
import { apiGet } from "@/lib/api";
import { timeAgo, usd } from "@/lib/format";

interface Action {
  id: string;
  action: string;
  inputs: Record<string, any>;
  result: Record<string, any>;
  created_at: string;
}

const WHO: Record<string, { tag: string; cls: string }> = {
  "job.match": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "claim.review": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "claim.paid": { tag: "Human", cls: "bg-ink text-white" },
  "claim.rejected": { tag: "Human", cls: "bg-ink text-white" },
  "invoice.paid.split": { tag: "Rule", cls: "bg-seal-soft text-seal" },
  "pool.credit": { tag: "Rule", cls: "bg-seal-soft text-seal" },
  "scope.drafted": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "scope.applied": { tag: "Human", cls: "bg-ink text-white" },
    "milestone.removed": { tag: "Human", cls: "bg-ink text-white" },
};

function describe(a: Action): string {
  const r = a.result ?? {};
  const i = a.inputs ?? {};
  switch (a.action) {
    case "job.match":
      return `Matched ${r.top_name ?? "a member"} to a job${r.backup_name ? `, with ${r.backup_name} as backup` : ""}. ${r.reason ?? ""}`;
    case "invoice.paid.split":
      return `Split a ${usd(i.amount ?? 0)} payment: ${usd(r.worker_cents ?? 0)} to the worker, ${usd(r.referrer_cents ?? 0)} referral fee, ${usd(r.pool_cents ?? 0)} to the pool${r.recovered_cents ? `, and ${usd(r.recovered_cents)} recovered for the pool` : ""}.`;
    case "claim.review":
      return `Reviewed a claim and recommended "${String(r.verdict ?? "").replaceAll("_", " ")}" (${Math.round((r.confidence ?? 0) * 100)}% confident).`;
    case "claim.paid":
      return `${i.approved_by ?? "An admin"} approved a claim. The pool paid ${usd(r.amount_cents ?? 0)}.${i.override ? ` Went against the AI: "${i.admin_note}"` : ""}`;
    case "claim.rejected":
      return `${i.rejected_by ?? "An admin"} rejected a claim.${i.override ? ` Went against the AI: "${i.admin_note}"` : ""}`;
    case "pool.credit":
      return `The pool received ${usd(r.amount_cents ?? 0)} from a monthly member fee.`;
    case "scope.drafted":
      return `Split a client brief into ${r.milestone_count} milestones totaling ${usd(r.total_cents ?? 0)}. ${r.pricing_basis ?? ""}`;
    case "scope.applied":
      return `${i.by ?? "A member"} reviewed and added ${i.count} milestones (${usd(r.total_cents ?? 0)}).`;
          case "milestone.removed":
      return `${i.by ?? "A member"} removed the milestone "${r.title}" (${usd(r.amount_cents ?? 0)}) before invoicing.`;
    default:
      return a.action;
  }
}

export function AgentFeed({ limit = 6, showRaw = false }: { limit?: number; showRaw?: boolean }) {
  const { data, error } = useSWR<Action[]>(["agent", limit], () => apiGet<Action[]>(`/agent/actions?limit=${limit}`));
  if (error) return <p className="text-sm text-alert">{error.message}</p>;
  if (!data) return <p className="text-sm text-muted">Loading activity…</p>;
  if (data.length === 0) return <p className="text-sm text-muted">Nothing yet. Post a job and ask the AI for a match.</p>;

  return (
    <ol className="divide-y divide-line">
      {data.map((a) => {
        const who = WHO[a.action] ?? { tag: "System", cls: "bg-paper text-muted" };
        return (
          <li key={a.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
            <span className={`h-fit rounded px-1.5 py-0.5 text-xs font-semibold ${who.cls}`}>{who.tag}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm">{describe(a)}</p>
              <p className="mt-0.5 text-xs text-muted">{timeAgo(a.created_at)}</p>
              {showRaw && (
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-muted hover:text-ink">Show what the system saw</summary>
                  <pre className="mt-2 overflow-x-auto rounded-md bg-paper p-3">{JSON.stringify({ inputs: a.inputs, result: a.result }, null, 2)}</pre>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}