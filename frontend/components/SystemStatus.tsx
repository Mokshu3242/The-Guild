"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { AiThinking } from "./AiThinking";
import { Button, ErrorText, Panel } from "./ui";

type State = "ok" | "slow" | "down" | "quiet" | "none";

interface Check {
  state: State;
  latency_ms?: number;
  error?: string;
  last_at?: string | null;
  last_type?: string | null;
}

interface Health {
  overall: "healthy" | "slow" | "degraded" | "down";
  checks: { db: Check; paypal: Check; ai: Check; webhooks: Check; reminders: Check };
  ran_at: string;
}

const OVERALL: Record<Health["overall"], { label: string; cls: string }> = {
  healthy: { label: "Everything is working", cls: "bg-guild-soft text-guild" },
  slow: { label: "Working, but slow", cls: "bg-seal-soft text-seal" },
  degraded: { label: "Something is down", cls: "bg-seal-soft text-seal" },
  down: { label: "Major problem", cls: "bg-alert-soft text-alert" },
};

const DOT: Record<State, { cls: string; word: string }> = {
  ok: { cls: "bg-guild", word: "Working" },
  slow: { cls: "bg-seal", word: "Slow" },
  down: { cls: "bg-alert", word: "Not reachable" },
  quiet: { cls: "bg-seal", word: "Quiet" },
  none: { cls: "bg-line", word: "No data yet" },
};

function detail(c: Check, kind: "live" | "event") {
  if (kind === "live") {
    if (c.state === "down") return c.error ?? "Not reachable";
    return `${c.latency_ms} ms`;
  }
  if (!c.last_at) return "Nothing yet";
  return `Last ${timeAgo(c.last_at)}${c.last_type ? `, ${c.last_type}` : ""}`;
}

export function SystemStatus() {
  const [data, setData] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setData(await apiPost<Health>("/platform/health"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "The check didn't finish");
    } finally {
      setBusy(false);
    }
  }

  const rows: { label: string; help: string; c: Check; kind: "live" | "event" }[] = data
    ? [
        { label: "Database", help: "Supabase Postgres", c: data.checks.db, kind: "live" },
        { label: "PayPal", help: "Sandbox API and login", c: data.checks.paypal, kind: "live" },
        { label: "AI", help: "Cloudflare Workers AI", c: data.checks.ai, kind: "live" },
        { label: "PayPal webhooks", help: "When PayPal last told us something", c: data.checks.webhooks, kind: "event" },
        { label: "Payment reminders", help: "When the daily job last sent one", c: data.checks.reminders, kind: "event" },
      ]
    : [];

  const o = data ? OVERALL[data.overall] : null;

  return (
    <Panel
      title="System status"
      action={!busy ? <Button variant={data ? "quiet" : "primary"} onClick={run}>{data ? "Check again" : "Check now"}</Button> : undefined}
    >
      {!data && !busy && (
        <p className="text-sm text-muted">
          A live check of the database, PayPal and the AI. It only runs when you click, and it never shows money.
        </p>
      )}

      {busy && <AiThinking label="Checking the database, PayPal and the AI…" />}

      {data && o && !busy && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-sm font-medium ${o.cls}`}>{o.label}</span>
            <span className="text-sm text-muted">Checked {timeAgo(data.ran_at)}</span>
          </div>
          <ul className="mt-4 divide-y divide-line border-t border-line">
            {rows.map((r) => {
              const d = DOT[r.c.state] ?? DOT.none;
              return (
                <li key={r.label} className="flex items-center justify-between gap-3 py-3 text-sm">
                  <span className="flex min-w-0 items-center gap-3">
                    <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${d.cls}`} aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block font-medium">{r.label}</span>
                      <span className="block text-xs text-muted">{r.help}</span>
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-xs font-medium">{d.word}</span>
                    <span className="block text-xs text-muted tabular-nums">{detail(r.c, r.kind)}</span>
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-muted">
            Webhooks and reminders can be quiet when nothing is happening. That's only a problem if payments are coming in and nothing shows up here.
          </p>
        </>
      )}
      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}
