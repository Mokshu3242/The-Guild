"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { ErrorText, PageHeader, Panel, Skeleton, focusRing } from "@/components/ui";
import { Chip, GUILD_STATUS, HEALTH, type GuildRow, useKickOutIfNotAllowed } from "@/components/PlatformBits";

interface ListResponse {
  guilds: GuildRow[];
  count: number;
  attention_count: number;
  member_count: number;
}

export default function PlatformPage() {
  const { data, error } = useSWR<ListResponse>("platform-guilds", () => apiGet<ListResponse>("/platform/guilds"), {
    shouldRetryOnError: false,
  });
  const blocked = useKickOutIfNotAllowed(error);

  if (blocked) return null;
  if (error) return <ErrorText>{error.message}</ErrorText>;

  const attention = (data?.guilds ?? []).filter((g) => g.attention_reasons.length > 0);
  const rest = (data?.guilds ?? []).filter((g) => g.attention_reasons.length === 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform"
        description="Every guild on The Guild, at a glance. Health and activity only. Money, claims, and members stay with each guild's own admin."
      />

      {!data ? (
        <div className="space-y-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <>
          <dl className="grid grid-cols-3 overflow-hidden rounded-xl border border-line bg-white">
            {[
              ["Guilds", data.count],
              ["Members", data.member_count],
              ["Need a look", data.attention_count],
            ].map(([label, value], i) => (
              <div key={label} className={`px-4 py-4 sm:px-6 ${i > 0 ? "border-l border-line" : ""}`}>
                <dt className="text-sm text-muted">{label}</dt>
                <dd className={`mt-1 font-display text-2xl font-semibold tabular-nums ${label === "Need a look" && Number(value) > 0 ? "text-alert" : ""}`}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>

          {attention.length > 0 && (
            <Panel title="Need a look">
              <ul className="divide-y divide-line">
                {attention.map((g) => <GuildLine key={g.id} g={g} />)}
              </ul>
            </Panel>
          )}

          <Panel title={attention.length > 0 ? "Everything else" : "All guilds"}>
            {rest.length === 0 ? (
              <p className="text-sm text-muted">
                {data.count === 0 ? "No guilds yet." : "Every guild is in the list above."}
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {rest.map((g) => <GuildLine key={g.id} g={g} />)}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function GuildLine({ g }: { g: GuildRow }) {
  const s = GUILD_STATUS[g.status] ?? GUILD_STATUS.active;
  const h = HEALTH[g.pool_health] ?? HEALTH.unknown;
  return (
    <li>
      <Link
        href={`/platform/guild/?id=${g.id}`}
        className={`-mx-2 flex flex-col gap-2 rounded-lg px-2 py-3.5 hover:bg-paper sm:flex-row sm:items-center sm:justify-between ${focusRing}`}
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{g.name}</span>
            <Chip cls={s.cls}>{s.label}</Chip>
            <Chip cls={h.cls}>{h.label}</Chip>
          </div>
          <p className="mt-1 text-sm text-muted">
            {g.member_count} member{g.member_count === 1 ? "" : "s"}, {g.active_jobs} active job
            {g.active_jobs === 1 ? "" : "s"}, {g.waiting_claims} waiting claim{g.waiting_claims === 1 ? "" : "s"}
          </p>
          {g.attention_reasons.length > 0 && (
            <p className="mt-1 text-sm text-alert">{g.attention_reasons.join(". ")}.</p>
          )}
        </div>
        <span className="shrink-0 text-xs text-muted">
          {g.last_activity_at ? `Active ${timeAgo(g.last_activity_at)}` : "No activity yet"}
        </span>
      </Link>
    </li>
  );
}
