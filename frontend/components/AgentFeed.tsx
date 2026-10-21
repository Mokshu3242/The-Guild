"use client";

import { useRef } from "react";
import useSWR from "swr";
import { motion, useReducedMotion } from "motion/react";
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
  "scope.creep_flagged": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "scope.addon_added": { tag: "Human", cls: "bg-ink text-white" },
  "scope.flag_dismissed": { tag: "Human", cls: "bg-ink text-white" },
  "deposit.requested": { tag: "Human", cls: "bg-ink text-white" },
  "claim.mediated": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "rate.advised": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "deposit.held": { tag: "PayPal", cls: "bg-seal-soft text-seal" },
  "digest.published": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "deposit.reviewed": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "deposit.captured": { tag: "Human", cls: "bg-ink text-white" },
  "deposit.voided": { tag: "Human", cls: "bg-ink text-white" },
  "client.risk_scored": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "autopilot.scan": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "member.reputation_summary": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "reminder.sent": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "skill.gap_checked": { tag: "AI", cls: "bg-guild-soft text-guild" },
  "job.removed": { tag: "Human", cls: "bg-ink text-white" },
  "pool.forecast": { tag: "AI", cls: "bg-guild-soft text-guild" },
   "portal.enabled": { tag: "Human", cls: "bg-ink text-white" },
   "portal.rotated": { tag: "Human", cls: "bg-ink text-white" },
   "portal.disabled": { tag: "Human", cls: "bg-ink text-white" },
   "milestone.delivered": { tag: "Human", cls: "bg-ink text-white" },
   "portal.client_approved": { tag: "Client", cls: "bg-guild-soft text-guild" },
   "portal.client_changes": { tag: "Client", cls: "bg-seal-soft text-seal" },
  "agreement.accepted": { tag: "Client", cls: "bg-guild-soft text-guild" },
  "pledge.signed": { tag: "Human", cls: "bg-ink text-white" },
};

function describe(a: Action): string {
  const r = a.result ?? {};
  const i = a.inputs ?? {};
  switch (a.action) {
    case "job.match":
      return `Matched ${r.top_name ?? "a member"} to a job${r.backup_name ? `, with ${r.backup_name} as backup` : ""}. ${r.reason ?? ""}`;
    case "digest.published":
      return "Wrote the weekly digest.";
    case "agreement.accepted":
      return r.kind === "amendment"
        ? `${i.by} accepted an update to the work agreement for ${i.client} (${r.milestones} milestones, ${usd(r.total_cents ?? 0)}).`
        : `${i.by} accepted the work agreement for ${i.client}: ${r.milestones} milestone${r.milestones === 1 ? "" : "s"}, ${usd(r.total_cents ?? 0)}. Fingerprint ${r.hash}.`;
    case "pledge.signed":
      return `${i.by} signed the Member Pledge.`;
     case "portal.enabled":
     return `${i.by} made a client link for ${r.client}.`;
   case "portal.rotated":
     return `${i.by} replaced the client link for ${r.client}. The old link stopped working.`;
   case "portal.disabled":
     return `${i.by} turned off the client link for ${r.client}.`;
   case "milestone.delivered":
     return `${i.by} delivered "${r.milestone}"${i.again ? " again, after changes" : ""}.`;
   case "portal.client_approved":
     return `${i.by} approved "${r.milestone}".`;
   case "portal.client_changes":
     return `${i.by} asked for changes on "${r.milestone}": "${r.feedback}"`;
    case "job.removed":
      return `${i.by ?? "A member"} deleted the job for ${r.client ?? "a client"}${r.milestones ? ` and its ${r.milestones} milestone${r.milestones === 1 ? "" : "s"}` : ""}.`;
    case "invoice.paid.split":
      return `Split a ${usd(i.amount ?? 0)} payment: ${usd(r.worker_cents ?? 0)} to the worker, ${usd(r.referrer_cents ?? 0)} referral fee, ${usd(r.pool_cents ?? 0)} to the pool${r.recovered_cents ? `, and ${usd(r.recovered_cents)} recovered for the pool` : ""}.`;
    case "claim.review":
      return `Reviewed a claim and recommended "${String(r.verdict ?? "").replaceAll("_", " ")}" (${Math.round((r.confidence ?? 0) * 100)}% confident).`;
    case "claim.paid":
      return `${i.approved_by ?? "An admin"} approved a claim. The pool paid ${usd(r.amount_cents ?? 0)}${i.partial ? `, part of the ${usd(i.cap_cents ?? 0)} cap` : ""}.${i.override ? ` Went against the AI: "${i.admin_note}"` : ""}`;
    case "pool.forecast":
      return `Checked the safety pool: ${r.verdict === "underfunded" ? "underfunded" : r.verdict === "watch" ? "worth watching" : "healthy"}. ${r.message ?? ""}`;
    case "claim.rejected":
      return `${i.rejected_by ?? "An admin"} rejected a claim.${i.override ? ` Went against the AI: "${i.admin_note}"` : ""}`;
    case "skill.gap_checked": {
      if (r.coverage === "full") {
        return `Checked the skills for ${i.client ?? "a job"}. The guild already has everything it needs.`;
      }
      const missing =
        Array.isArray(r.uncovered_skills) && r.uncovered_skills.length
          ? ` Missing: ${r.uncovered_skills.join(", ")}.`
          : "";
      const invite = r.proposed_role
        ? ` Who to invite: ${r.proposed_role}.`
        : "";
      return `Checked the skills for ${i.client ?? "a job"}. ${r.coverage === "none" ? "Nobody in the guild has them." : "Partly covered."}${missing}${invite}`;
    }
    case "pool.credit":
      return `The pool received ${usd(r.amount_cents ?? 0)} from a monthly member fee.`;
    case "scope.drafted":
      return `Split a client brief into ${r.milestone_count} milestones totaling ${usd(r.total_cents ?? 0)}. ${r.pricing_basis ?? ""}`;
    case "scope.applied":
      return `${i.by ?? "A member"} reviewed and added ${i.count} milestones (${usd(r.total_cents ?? 0)}).`;
    case "milestone.removed":
      return `${i.by ?? "A member"} removed the milestone "${r.title}" (${usd(r.amount_cents ?? 0)}) before invoicing.`;
    case "scope.creep_flagged":
      return r.verdict === "out_of_scope"
        ? `Spotted new work in a client message: "${r.suggested_title}", suggested at ${usd(r.suggested_amount_cents ?? 0)}. ${r.reason}`
        : `Checked a client message: ${String(r.verdict).replaceAll("_", " ")}. ${r.reason}`;
    case "scope.addon_added":
      return `${i.by ?? "A member"} added "${r.title}" as a paid add-on (${usd(r.amount_cents ?? 0)})${i.edited ? `, changed from the AI's ${usd(r.ai_suggested_cents ?? 0)}` : ""}.`;
    case "scope.flag_dismissed":
      return `${i.by ?? "A member"} decided "${r.title}" wasn't worth charging for.`;
    case "deposit.requested":
      return `${i.by ?? "A member"} asked the client to hold ${usd(r.amount_cents ?? 0)} before work starts on "${i.milestone}".`;
    case "claim.mediated":
      return `Suggested the pool pays ${usd(r.amount_cents ?? 0)} (${r.percent_of_cap}% of the cap). ${r.reason ?? ""}`;
    case "autopilot.scan":
      return `${i.by ?? "An admin"} ran the autopilot. It found ${r.found ?? 0} thing${r.found === 1 ? "" : "s"} to look at.`;
    case "member.reputation_summary":
      return `Wrote a reputation summary for ${i.member ?? "a member"}. ${r.summary ?? ""}`;
    case "deposit.held":
      return `The client approved. ${usd(r.amount_cents ?? 0)} is on hold, not charged yet.`;
    case "deposit.reviewed":
      return `Checked the delivery against the scope: ${String(r.verdict)} (${Math.round((r.confidence ?? 0) * 100)}% sure). ${r.reason}`;
    case "deposit.captured":
      return `${i.by ?? "An admin"} accepted the work and captured ${usd(r.amount_cents ?? 0)}. The split ran automatically.`;
    case "deposit.voided":
      return `${i.by ?? "An admin"} released the hold. The client wasn't charged.`;
    case "reminder.sent": {
      const risk =
        i.risk_level && i.risk_level !== "unknown"
          ? ` (client is ${i.risk_level} risk)`
          : "";
      return `Sent reminder ${i.tier} of 3 to a client ${i.days_overdue} days overdue${risk}: "${r.subject}"`;
    }
    case "rate.advised":
      return `Compared ${i.member ?? "a member"}'s rate with the guild (${String(r.verdict ?? "").replaceAll("_", " ")}). ${r.message ?? ""}`;
    case "client.risk_scored":
      return `Scored a client as ${r.level} risk. ${r.reason ?? ""}${r.suggest_deposit ? " Suggested a deposit hold." : ""}`;
    default:
      return a.action;
  }
}

export function AgentFeed({
  limit = 6,
  showRaw = false,
  pollMs = 4000,
}: {
  limit?: number;
  showRaw?: boolean;
  pollMs?: number;
}) {
  const reduce = useReducedMotion();
  const { data, error } = useSWR<Action[]>(
    ["agent", limit],
    () => apiGet<Action[]>(`/agent/actions?limit=${limit}`),
    { refreshInterval: pollMs },
  );

  // Remember what was already on screen, so only new entries animate.
  // Seed again when the limit changes, so "last 50" doesn't animate everything.
  const seen = useRef<Set<string> | null>(null);
  const seededFor = useRef<number | null>(null);
  if (data && seededFor.current !== limit) {
    seen.current = new Set(data.map((a) => a.id));
    seededFor.current = limit;
  }
  const isFresh = (id: string) => !!seen.current && !seen.current.has(id);

  if (error) return <p className="text-sm text-alert">{error.message}</p>;
  if (!data) return <p className="text-sm text-muted">Loading activity…</p>;
  if (data.length === 0)
    return (
      <p className="text-sm text-muted">
        Nothing yet. Post a job and ask the AI for a match.
      </p>
    );

  return (
    <ol className="divide-y divide-line">
      {data.map((a) => {
        const who = WHO[a.action] ?? {
          tag: "System",
          cls: "bg-paper text-muted",
        };
        const fresh = !reduce && isFresh(a.id);
        return (
          <motion.li
            key={a.id}
            className="flex gap-3 py-3 first:pt-0 last:pb-0"
            initial={fresh ? { opacity: 0, y: -12 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            onAnimationComplete={() => seen.current?.add(a.id)}
          >
            <motion.span
              className={`h-fit rounded px-1.5 py-0.5 text-xs font-semibold ${who.cls}`}
              initial={fresh ? { scale: 0.5, opacity: 0 } : false}
              animate={{ scale: 1, opacity: 1 }}
              transition={{
                delay: 0.18,
                type: "spring",
                stiffness: 420,
                damping: 20,
              }}
            >
              {who.tag}
            </motion.span>
            <div className="min-w-0 flex-1">
              <p className="text-sm">{describe(a)}</p>
              <p className="mt-0.5 text-xs text-muted">
                {timeAgo(a.created_at)}
              </p>
              {showRaw && (
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer rounded-sm text-muted hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40">
                    Show what the system saw
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded-md bg-paper p-3">
                    {JSON.stringify(
                      { inputs: a.inputs, result: a.result },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              )}
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}

