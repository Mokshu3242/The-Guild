"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Button, ErrorText, Notice, PageHeader, Panel, Skeleton, focusRing, inputCls } from "@/components/ui";
import { Chip, GUILD_STATUS, HEALTH, type GuildRow, useKickOutIfNotAllowed } from "@/components/PlatformBits";
import { SystemStatus } from "@/components/SystemStatus";

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

          <SystemStatus />

          <div className="grid gap-6 lg:grid-cols-2">
            <BroadcastComposer guilds={data.guilds} />
            <MaintenanceComposer guilds={data.guilds} />
          </div>
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

/* ---------------- Broadcasts and maintenance ---------------- */

interface Row {
  id: string;
  guild_id: string | null;
  starts_at: string;
  ends_at: string | null;
  state: "scheduled" | "live" | "ended";
  title?: string;
  level?: string;
  mode?: string;
  message?: string;
}

const STATE_CLS: Record<Row["state"], string> = {
  live: "bg-guild-soft text-guild",
  scheduled: "bg-seal-soft text-seal",
  ended: "bg-paper text-muted",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <div className="mt-1 font-normal">{children}</div>
    </label>
  );
}

function GuildPicker({ guilds, value, onChange }: { guilds: GuildRow[]; value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>
      <option value="">Every guild</option>
      {guilds.map((g) => (
        <option key={g.id} value={g.id}>{g.name}</option>
      ))}
    </select>
  );
}

function when(r: Row, guilds: GuildRow[]) {
  const who = r.guild_id ? guilds.find((g) => g.id === r.guild_id)?.name ?? "One guild" : "Every guild";
  const t = (iso: string) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const span = r.state === "scheduled" ? `starts ${t(r.starts_at)}` : r.ends_at ? `${r.state === "ended" ? "ended" : "until"} ${t(r.ends_at)}` : "no end time";
  return `${who}, ${span}`;
}

function RowList({ rows, guilds, onEnd, busy, label }: {
  rows: Row[]; guilds: GuildRow[]; onEnd: (id: string) => void; busy: boolean; label: (r: Row) => string;
}) {
  if (rows.length === 0) return null;
  return (
    <ul className="mt-5 divide-y divide-line border-t border-line">
      {rows.slice(0, 8).map((r) => (
        <li key={r.id} className="flex items-start justify-between gap-3 py-3 text-sm">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE_CLS[r.state]}`}>{r.state}</span>
              <span className="truncate font-medium">{label(r)}</span>
            </div>
            <p className="mt-0.5 text-xs text-muted">{when(r, guilds)}</p>
          </div>
          {r.state !== "ended" && (
            <Button variant="quiet" disabled={busy} onClick={() => onEnd(r.id)} className="shrink-0 px-3 py-1.5">
              {r.state === "scheduled" ? "Cancel" : "End now"}
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function BroadcastComposer({ guilds }: { guilds: GuildRow[] }) {
  const { data: rows, mutate } = useSWR<Row[]>("platform-broadcasts", () => apiGet<Row[]>("/platform/broadcasts"));
  const [f, setF] = useState({ guild_id: "", level: "info", title: "", body: "", starts: "0", hours: "24" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>, done?: string) {
    setBusy(true); setErr(null); setOk(null);
    try { await fn(); await mutate(); if (done) setOk(done); }
    catch (e) { setErr(e instanceof Error ? e.message : "That didn't work"); }
    finally { setBusy(false); }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    run(async () => {
      await apiPost("/platform/broadcasts", {
        guild_id: f.guild_id || null,
        level: f.level,
        title: f.title,
        body: f.body,
        starts_in_minutes: Number(f.starts) || 0,
        duration_minutes: f.hours ? Math.round(Number(f.hours) * 60) : null,
      });
      setF({ ...f, title: "", body: "" });
    }, "Posted. Members see it within 30 seconds.");
  }

  return (
    <Panel title="Post an announcement">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Who sees it"><GuildPicker guilds={guilds} value={f.guild_id} onChange={(v) => setF({ ...f, guild_id: v })} /></Field>
          <Field label="Type">
            <select value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })} className={inputCls}>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical (can't be dismissed)</option>
            </select>
          </Field>
        </div>
        <Field label="Title"><input required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} className={inputCls} placeholder="New: deposit holds" /></Field>
        <Field label="Message"><textarea required minLength={5} rows={2} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} className={inputCls} placeholder="You can now hold a client's payment before work starts." /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Starts in (minutes)"><input type="number" min={0} value={f.starts} onChange={(e) => setF({ ...f, starts: e.target.value })} className={inputCls} /></Field>
          <Field label="Shows for (hours, empty = until ended)"><input type="number" min={0} step="0.5" value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} className={inputCls} /></Field>
        </div>
        <Button disabled={busy}>{busy ? "Posting…" : "Post announcement"}</Button>
      </form>
      <ErrorText>{err}</ErrorText>
      <Notice>{ok}</Notice>
      <RowList rows={rows ?? []} guilds={guilds} busy={busy} label={(r) => r.title ?? ""}
        onEnd={(id) => run(() => apiPost(`/platform/broadcasts/${id}/end`))} />
    </Panel>
  );
}

function MaintenanceComposer({ guilds }: { guilds: GuildRow[] }) {
  const { data: rows, mutate } = useSWR<Row[]>("platform-maintenance", () => apiGet<Row[]>("/platform/maintenance"));
  const DEFAULT_MSG = {
    read_only: "We're doing some maintenance. You can look around, but changes are paused.",
    full_pause: "The Guild is down for a short maintenance. Please check back soon.",
  } as const;
  const [f, setF] = useState({
    guild_id: "", mode: "read_only", starts: "0", minutes: "30",
    message: DEFAULT_MSG.read_only,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>, done?: string) {
    setBusy(true); setErr(null); setOk(null);
    try { await fn(); await mutate(); if (done) setOk(done); }
    catch (e) { setErr(e instanceof Error ? e.message : "That didn't work"); }
    finally { setBusy(false); }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const where = f.guild_id ? "that guild" : "every guild";
    const what = f.mode === "full_pause" ? "show a maintenance page to" : "block all changes for";
    if (!window.confirm(`This will ${what} ${where}. PayPal payments keep working. Go ahead?`)) return;
    run(() => apiPost("/platform/maintenance", {
      guild_id: f.guild_id || null,
      mode: f.mode,
      message: f.message,
      starts_in_minutes: Number(f.starts) || 0,
      duration_minutes: Math.max(1, Number(f.minutes) || 30),
    }), Number(f.starts) > 0 ? "Scheduled. Members see a countdown banner." : "Maintenance is on.");
  }

  return (
    <Panel title="Maintenance">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Who it affects"><GuildPicker guilds={guilds} value={f.guild_id} onChange={(v) => setF({ ...f, guild_id: v })} /></Field>
          <Field label="Strength">
            <select value={f.mode} onChange={(e) => {
  const mode = e.target.value as keyof typeof DEFAULT_MSG;
  const untouched = Object.values(DEFAULT_MSG).includes(f.message as never);
  setF({ ...f, mode, message: untouched ? DEFAULT_MSG[mode] : f.message });
}} className={inputCls}>
              <option value="read_only">Read only: look, but no changes</option>
              <option value="full_pause">Full pause: maintenance page</option>
            </select>
          </Field>
        </div>
        <Field label="Message members see"><textarea required minLength={5} rows={2} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} className={inputCls} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Starts in (minutes, 0 = now)"><input type="number" min={0} value={f.starts} onChange={(e) => setF({ ...f, starts: e.target.value })} className={inputCls} /></Field>
          <Field label="Lasts (minutes)"><input type="number" min={1} max={1440} required value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} className={inputCls} /></Field>
        </div>
        <p className="text-xs text-muted">It always ends on its own. PayPal webhooks and the daily reminder job keep running, so no payment is lost.</p>
        <Button variant={f.mode === "full_pause" ? "danger" : "primary"} disabled={busy}>
          {busy ? "Saving…" : Number(f.starts) > 0 ? "Schedule maintenance" : "Start maintenance"}
        </Button>
      </form>
      <ErrorText>{err}</ErrorText>
      <Notice>{ok}</Notice>
      <RowList rows={rows ?? []} guilds={guilds} busy={busy}
        label={(r) => (r.mode === "full_pause" ? "Full pause" : "Read only")}
        onEnd={(id) => run(() => apiPost(`/platform/maintenance/${id}/end`), "Ended. Members are back within 20 seconds.")} />
    </Panel>
  );
}
