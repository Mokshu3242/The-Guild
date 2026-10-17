"use client";

import { Suspense } from "react";
import useSWR from "swr";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { apiGet } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { ErrorText, PageHeader, Panel, Skeleton } from "@/components/ui";
import { Chip, GUILD_STATUS, HEALTH, type GuildRow, useKickOutIfNotAllowed } from "@/components/PlatformBits";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <GuildDetail />
    </Suspense>
  );
}

function GuildDetail() {
  const id = useSearchParams().get("id") ?? "";
  const { data, error } = useSWR<GuildRow>(id ? ["platform-guild", id] : null, () =>
    apiGet<GuildRow>(`/platform/guilds/${id}`),
  { shouldRetryOnError: false });
  const blocked = useKickOutIfNotAllowed(error);

  if (blocked) return null;

  return (
    <div className="space-y-6">
      <Link href="/platform/" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
          <path d="M12 5l-5 5 5 5" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        All guilds
      </Link>

      {error && <ErrorText>{error.message}</ErrorText>}
      {!data && !error && <Skeleton className="h-64" />}

      {data && (
        <>
          <PageHeader
            title={data.name}
            description={
              <span className="flex flex-wrap gap-2">
                <Chip cls={(GUILD_STATUS[data.status] ?? GUILD_STATUS.active).cls}>
                  {(GUILD_STATUS[data.status] ?? GUILD_STATUS.active).label}
                </Chip>
                <Chip cls={(HEALTH[data.pool_health] ?? HEALTH.unknown).cls}>
                  {(HEALTH[data.pool_health] ?? HEALTH.unknown).label}
                </Chip>
              </span>
            }
          />

          {data.attention_reasons.length > 0 && (
            <div className="rounded-xl border border-alert/20 bg-alert-soft px-5 py-4 text-sm text-alert">
              <p className="font-medium">Why this guild needs a look</p>
              <ul className="mt-1 list-disc pl-5">
                {data.attention_reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
            </div>
          )}

          <Panel title="Activity">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3">
              {[
                ["Members", data.member_count],
                ["Admins", data.admin_count],
                ["Active jobs", data.active_jobs],
                ["Finished jobs", data.finished_jobs],
                ["Waiting claims", data.waiting_claims],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-sm text-muted">{label}</dt>
                  <dd className="mt-0.5 font-display text-2xl font-semibold tabular-nums">{value}</dd>
                </div>
              ))}
              <div>
                <dt className="text-sm text-muted">Last activity</dt>
                <dd className="mt-1 text-sm">{data.last_activity_at ? timeAgo(data.last_activity_at) : "None yet"}</dd>
              </div>
            </dl>
          </Panel>

          <p className="text-sm text-muted">
            This page is read only. Money, claims, and members are managed inside the guild by its own admin.
          </p>
        </>
      )}
    </div>
  );
}
