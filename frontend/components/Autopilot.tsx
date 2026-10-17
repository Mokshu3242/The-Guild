"use client";

import { useState } from "react";
import Link from "next/link";
import { mutate } from "swr";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { apiPost } from "@/lib/api";
import { AiThinking } from "./AiThinking";
import { Button, ErrorText, Panel, buttonCls } from "./ui";

type Kind = "remind" | "deposit" | "match" | "scope_hint";

interface Finding {
  id: string;
  kind: Kind;
  job_id: string;
  title: string;
  rule_reason: string;
  ai_reason: string;
  action_endpoint: string;
  action_body: Record<string, unknown>;
}

interface ScanResult {
  findings: Finding[];
  summary: string;
}

// What happened after Approve, shown on the card instead of making it vanish silently.
interface Outcome {
  text: string;
  link?: { href: string; label: string; external?: boolean };
}

const KIND: Record<Kind, { label: string; cls: string; approve: string }> = {
  remind: {
    label: "Payment reminder",
    cls: "bg-seal-soft text-seal",
    approve: "Send reminder",
  },
  deposit: {
    label: "Deposit hold",
    cls: "bg-guild-soft text-guild",
    approve: "Request the hold",
  },
  match: {
    label: "Find a worker",
    cls: "bg-guild-soft text-guild",
    approve: "Ask the AI for a match",
  },
  scope_hint: {
    label: "Needs milestones",
    cls: "bg-paper text-muted",
    approve: "",
  },
};

function outcomeFor(f: Finding, r: Record<string, unknown>): Outcome {
  const job = { href: `/jobs/view/?id=${f.job_id}`, label: "Open the job" };
  switch (f.kind) {
    case "remind":
      if (r.status === "sent")
        return {
          text: `Reminder ${r.tier} of 3 sent: "${r.subject}"`,
          link: job,
        };
      if (r.status === "already_paid")
        return {
          text: "The client already paid, so the payout went out instead.",
          link: job,
        };
      if (r.status === "not_due")
        return { text: "Not due yet after all. Nothing was sent.", link: job };
      return { text: `Done. Status: ${String(r.status ?? "ok")}.`, link: job };
    case "deposit":
      return {
        text: "Hold requested. Send the client the approval link.",
        link: r.approve_url
          ? {
              href: String(r.approve_url),
              label: "Open the PayPal approval page",
              external: true,
            }
          : job,
      };
    case "match":
      return {
        text: r.top_name
          ? `The AI suggests ${r.top_name}. ${r.reason ?? ""}`
          : "Match ready.",
        link: { href: job.href, label: "Review and assign" },
      };
    default:
      return { text: "Done.", link: job };
  }
}

export function Autopilot() {
  const reduce = useReducedMotion();
  const [data, setData] = useState<ScanResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [done, setDone] = useState<Record<string, Outcome>>({});
  const [acting, setActing] = useState<string | null>(null);

  async function scanNow() {
    setBusy(true);
    setErr(null);
    setSkipped(new Set());
    setDone({});
    try {
      setData(await apiPost<ScanResult>("/autopilot/scan"));
      mutate((k) => Array.isArray(k) && k[0] === "agent"); // refresh the activity feed
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't run the agent");
    } finally {
      setBusy(false);
    }
  }

  async function approve(f: Finding) {
    setActing(f.id);
    setErr(null);
    try {
      const r = await apiPost<Record<string, unknown>>(
        f.action_endpoint,
        f.action_body,
      );
      setDone((d) => ({ ...d, [f.id]: outcomeFor(f, r ?? {}) }));
      mutate("jobs");
      mutate("invoices");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "That action didn't go through");
    } finally {
      setActing(null);
    }
  }

  const visible = (data?.findings ?? []).filter((f) => !skipped.has(f.id));
  const open = visible.filter((f) => !done[f.id]).length;

  return (
    <Panel title="Autopilot">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-prose text-sm text-muted">
          Checks every job in the guild. Rules find what needs attention, the AI
          explains it, and you decide.
        </p>
        <Button disabled={busy} onClick={scanNow} className="shrink-0">
          {busy ? "Checking…" : data ? "Check again" : "Run the agent"}
        </Button>
      </div>

      {busy && (
        <div className="mt-4">
          <AiThinking label="Reading every job, invoice, and client in the guild…" />
        </div>
      )}

      {!busy && data && (
        <p className="mt-4 text-sm font-medium">
          {data.findings.length > 0 && open === 0
            ? "All handled. Check again later."
            : data.summary}
        </p>
      )}

      <ul className="mt-3 space-y-3">
        <AnimatePresence initial={false}>
          {!busy &&
            visible.map((f) => {
              const k = KIND[f.kind];
              const result = done[f.id];
              return (
                <motion.li
                  key={f.id}
                  layout={!reduce}
                  initial={reduce ? false : { opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduce ? { opacity: 0 } : { opacity: 0, x: 24 }}
                  transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                  className={`rounded-xl border p-4 ${result ? "border-guild/30 bg-guild-soft/40" : "border-line bg-white"}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${k.cls}`}
                    >
                      {k.label}
                    </span>
                    <span className="min-w-0 truncate text-sm font-medium">
                      {f.title}
                    </span>
                  </div>

                  <p className="mt-2 text-sm">{f.ai_reason || f.rule_reason}</p>
                  {f.ai_reason && (
                    <details className="mt-1 text-xs text-muted">
                      <summary className="cursor-pointer hover:text-ink">
                        Why the rule flagged this
                      </summary>
                      <p className="mt-1">{f.rule_reason}</p>
                    </details>
                  )}

                  {result ? (
                    <div className="mt-3 text-sm">
                      <p className="text-guild">{result.text}</p>
                      {result.link &&
                        (result.link.external ? (
                          <a
                            href={result.link.href}
                            target="_blank"
                            rel="noreferrer"
                            className={buttonCls("quiet", "mt-2")}
                          >
                            {result.link.label}
                          </a>
                        ) : (
                          <Link
                            href={result.link.href}
                            className={buttonCls("quiet", "mt-2")}
                          >
                            {result.link.label}
                          </Link>
                        ))}
                    </div>
                  ) : (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {f.action_endpoint ? (
                        <Button disabled={!!acting} onClick={() => approve(f)}>
                          {acting === f.id ? "Working…" : k.approve}
                        </Button>
                      ) : (
                        <Link
                          href={`/jobs/view/?id=${f.job_id}`}
                          className={buttonCls()}
                        >
                          Open the job
                        </Link>
                      )}
                      <Button
                        variant="quiet"
                        disabled={acting === f.id}
                        onClick={() => setSkipped((s) => new Set(s).add(f.id))}
                      >
                        Skip
                      </Button>
                    </div>
                  )}
                </motion.li>
              );
            })}
        </AnimatePresence>
      </ul>

      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}
