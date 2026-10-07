"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { plural, usd } from "@/lib/format";
import { useGuild, useMembers } from "@/lib/useGuild";
import type { Me } from "@/lib/useMe";
import { Panel } from "./ui";
import { SplitBar } from "./SplitBar";
import { JobsGrid, type Job } from "./JobsGrid";
import { AgentFeed } from "./AgentFeed";

interface Pool { pool_balance_cents: number; monthly_fee_cents: number; active_subscribers: number; plan_ready: boolean }
interface Earnings { total_cents: number; payouts: { kind: string }[] }

export function Dashboard({ me }: { me: Me }) {
  const { data: guild } = useGuild(me.guild_id);
  const { data: members } = useMembers(me.guild_id);
  const { data: pool } = useSWR<Pool>("pool", () => apiGet<Pool>("/pool"));
  const { data: earnings } = useSWR<Earnings>("earnings", () => apiGet<Earnings>("/me/earnings"));
  const { data: jobs } = useSWR<Job[]>("jobs", () => apiGet<Job[]>("/jobs"));

  const openJobs = (jobs ?? []).filter((j) => !["paid", "covered"].includes(j.status)).length;
  const referrals = (earnings?.payouts ?? []).filter((p) => p.kind === "referral").length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-muted">Hi {me.name}</p>
          <h1 className="font-display text-3xl font-bold">{guild?.name ?? "Your guild"}</h1>
        </div>
        {me.role === "admin" && guild && (
          <p className="text-sm text-muted">
            Invite code <span className="ml-1 rounded bg-white px-2 py-1 font-medium text-ink ring-1 ring-line">{guild.invite_code}</span>
          </p>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-lg bg-seal-soft p-6 ring-1 ring-seal/20 lg:col-span-1">
          <h2 className="text-sm font-medium text-seal">Safety pool</h2>
          <p className="mt-1 font-display text-5xl font-bold tabular-nums text-ink">{usd(pool?.pool_balance_cents ?? 0)}</p>
          <p className="mt-2 text-sm text-muted">
            Covers members when a client never pays. {pool?.active_subscribers ?? 0}{" "}
            {plural(pool?.active_subscribers ?? 0, "member pays", "members pay")} {usd(pool?.monthly_fee_cents ?? 0)} a month.
          </p>
        </section>

        <Panel title="How every payment splits" className="lg:col-span-2">
          {guild ? (
            <>
              <SplitBar amount={10000} workerPct={guild.worker_pct} referrerPct={guild.referrer_pct} poolPct={guild.pool_pct}
                workerName="Member who did the work" referrerName="Member who brought the client" />
              <p className="mt-3 text-sm text-muted">
                On a $100 invoice. When a client pays, the money splits and pays out automatically through PayPal.
              </p>
            </>
          ) : <p className="text-sm text-muted">Loading…</p>}
        </Panel>
      </div>

      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[
          ["Jobs in progress", String(openJobs)],
          ["You've earned", usd(earnings?.total_cents ?? 0)],
          ["Referral fees", `${referrals} paid`],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-line bg-white px-5 py-4">
            <dt className="text-sm text-muted">{label}</dt>
            <dd className="mt-1 font-display text-2xl font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <Panel title="Jobs" action={<Link href="/jobs/new" className="rounded-md bg-guild px-3 py-1.5 text-sm font-medium text-white hover:bg-guild/90">Post a job</Link>}>
        <JobsGrid jobs={jobs ?? []} members={members ?? []} />
      </Panel>

      <Panel title="What the agent did" action={<Link href="/agent" className="text-sm text-guild hover:underline">Full log</Link>}>
        <AgentFeed limit={6} />
      </Panel>
    </div>
  );
}