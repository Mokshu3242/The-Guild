"use client";

import useSWR from "swr";
import { DigestCard } from "./DigestCard";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { plural, usd } from "@/lib/format";
import { useGuild, useMembers } from "@/lib/useGuild";
import type { Me } from "@/lib/useMe";
import { Panel, buttonCls } from "./ui";
import { SplitBar } from "./SplitBar";
import { JobsGrid, type Job } from "./JobsGrid";
import { AgentFeed } from "./AgentFeed";
import { PoolBalance } from "./PoolBalance";
import { Autopilot } from "./Autopilot";

interface Pool {
  pool_balance_cents: number;
  monthly_fee_cents: number;
  active_subscribers: number;
  plan_ready: boolean;
}
interface Earnings {
  total_cents: number;
  payouts: { kind: string }[];
}

export function Dashboard({ me }: { me: Me }) {
  const { data: guild } = useGuild(me.guild_id);
  const { data: members } = useMembers(me.guild_id);
  const { data: pool } = useSWR<Pool>("pool", () => apiGet<Pool>("/pool"), {
    refreshInterval: 5000,
  });
  const { data: earnings } = useSWR<Earnings>("earnings", () =>
    apiGet<Earnings>("/me/earnings"),
  );
  const { data: jobs } = useSWR<Job[]>("jobs", () => apiGet<Job[]>("/jobs"));

  const openJobs = (jobs ?? []).filter(
    (j) => !["paid", "covered"].includes(j.status),
  ).length;
  const myJobs = (jobs ?? []).filter(
    (j) => j.worker_id === me.id && !["paid", "covered"].includes(j.status),
  ).length;
  const referrals = (earnings?.payouts ?? []).filter(
    (p) => p.kind === "referral",
  ).length;

  const stats = [
    {
      label: "You've earned",
      value: earnings ? usd(earnings.total_cents) : "…",
    },
    { label: "Jobs you're working on", value: jobs ? String(myJobs) : "…" },
    {
      label: "Referral fees paid to you",
      value: earnings ? String(referrals) : "…",
    },
    { label: "Open jobs in the guild", value: jobs ? String(openJobs) : "…" },
  ];

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* The one bold moment: your guild and its safety pool. */}
      <section className="overflow-hidden rounded-2xl bg-guild-deep text-white">
        <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.3fr_1fr] lg:items-end">
          <div className="min-w-0">
            <p className="text-white/70">Hi {me.name}</p>
            <h1 className="mt-1 font-display text-3xl font-bold tracking-tight sm:text-4xl">
              {guild?.name ?? "Your guild"}
            </h1>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link
                href="/jobs/new/"
                className={buttonCls(
                  "primary",
                  "bg-seal-bright text-guild-deep shadow-none hover:bg-white",
                )}
              >
                Post a job you can&apos;t take
              </Link>
              {me.role === "admin" && guild && (
                <span className="rounded-lg border border-white/15 px-3 py-2 text-sm text-white/80">
                  Invite code{" "}
                  <span className="ml-1 font-semibold tracking-wide text-white">
                    {guild.invite_code}
                  </span>
                </span>
              )}
            </div>
          </div>

          <div className="rounded-xl bg-white/[0.06] p-5 ring-1 ring-white/10">
            <p className="text-sm text-seal-bright">Safety pool</p>
            <p className="mt-1 font-display text-4xl font-bold tabular-nums sm:text-5xl">
              <PoolBalance
                cents={pool?.pool_balance_cents}
                tagClassName="text-seal-bright"
              />
            </p>
            <p className="mt-2 text-sm text-white/70">
              Covers members when a client never pays.{" "}
              {pool?.active_subscribers ?? 0}{" "}
              {plural(
                pool?.active_subscribers ?? 0,
                "member pays",
                "members pay",
              )}{" "}
              {usd(pool?.monthly_fee_cents ?? 0)} a month.
            </p>
          </div>
        </div>
      </section>
      <DigestCard isAdmin={me.role === "admin"} />
      <dl className="grid grid-cols-2 overflow-hidden rounded-xl border border-line bg-white lg:grid-cols-4">
        {stats.map((s, i) => (
          <div
            key={s.label}
            className={`px-5 py-4 sm:px-6 sm:py-5 ${i % 2 === 1 ? "border-l border-line" : ""} ${i >= 2 ? "border-t border-line lg:border-t-0" : ""} ${i === 2 ? "lg:border-l" : ""}`}
          >
            <dt className="text-sm text-muted">{s.label}</dt>
            <dd className="mt-1 font-display text-2xl font-semibold tabular-nums">
              {s.value}
            </dd>
          </div>
        ))}
      </dl>

      {me.role === "admin" && <Autopilot />}

      <Panel
        title="Jobs"
        action={
          <Link
            href="/jobs/"
            className="text-sm font-medium text-guild hover:underline"
          >
            See all jobs
          </Link>
        }
      >
        <JobsGrid jobs={jobs ?? []} members={members ?? []} />
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title="What the agent did"
          className="lg:col-span-2"
          action={
            <Link
              href="/agent/"
              className="text-sm font-medium text-guild hover:underline"
            >
              Full activity
            </Link>
          }
        >
          <AgentFeed limit={6} />
        </Panel>

        <Panel title="How every payment splits">
          {guild ? (
            <>
              <SplitBar
                amount={10000}
                workerPct={guild.worker_pct}
                referrerPct={guild.referrer_pct}
                poolPct={guild.pool_pct}
                workerName="Did the work"
                referrerName="Found the client"
              />
              <p className="mt-4 text-sm text-muted">
                On a $100 invoice. When the client pays, PayPal pays everyone
                out automatically.
              </p>
            </>
          ) : (
            <p className="text-sm text-muted">Loading…</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
