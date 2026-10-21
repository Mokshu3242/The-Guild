"use client";

import { useState } from "react";
import useSWR from "swr";
import { apiGet, apiPost } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Button, ErrorText, Panel, inputCls } from "@/components/ui";

interface Settings {
  ai_enabled: boolean;
  reminders_enabled: boolean;
  ai_disabled_features: string[];
}

interface MemberHit {
  member_id: string;
  name: string;
  email: string;
  role: string;
  guild_id: string;
  guild_name: string;
  guild_status: string;
  joined_at: string | null;
}

interface AuditRow {
  id: string;
  actor_email: string;
  action: string;
  target_id: string;
  inputs: Record<string, unknown>;
  created_at: string;
}

const FEATURES = [
  { key: "match", label: "Job matching" },
  { key: "scope", label: "Scope builder" },
  { key: "claim", label: "Claim review" },
  { key: "reminder", label: "Reminder writing" },
  { key: "deposit_review", label: "Delivery review" },
  { key: "risk", label: "Client risk" },
  { key: "autopilot", label: "Autopilot" },
  { key: "rate", label: "Rate advice" },
  { key: "forecast", label: "Pool forecast" },
  { key: "digest", label: "Weekly digest" },
  { key: "agreement", label: "Agreement summary" },
];

const ACTION_LABEL: Record<string, string> = {
  "setting.update": "Changed a switch",
  "guild.suspend": "Suspended a guild",
  "guild.unsuspend": "Restored a guild",
  "member.lookup": "Looked up a member",
  "broadcast.create": "Posted an announcement",
  "broadcast.end": "Ended an announcement",
  "maintenance.create": "Scheduled maintenance",
  "maintenance.end": "Ended maintenance",
};

function Switch({ on, disabled, onChange, label }: { on: boolean; disabled?: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${on ? "bg-guild" : "bg-line"}`}
    >
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

export function PlatformSettings() {
  const { data, mutate } = useSWR<Settings>("platform-settings", () => apiGet<Settings>("/platform/settings"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function update(patch: Partial<Settings>) {
    setBusy(true);
    setErr(null);
    try {
      await mutate(await apiPost<Settings>("/platform/settings", patch), { revalidate: false });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return <Panel title="Kill switches"><p className="text-sm text-muted">Loading…</p></Panel>;
  }

  const off = data.ai_disabled_features;
  const toggleFeature = (key: string) =>
    update({ ai_disabled_features: off.includes(key) ? off.filter((f) => f !== key) : [...off, key] });

  return (
    <Panel title="Kill switches">
      <p className="text-sm text-muted">
        Use these if the AI or emails misbehave. Payments and payouts keep running no matter what.
      </p>

      <div className="mt-4 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">All AI features</p>
            <p className="text-xs text-muted">{data.ai_enabled ? "On" : "Off. Members see a clear message instead."}</p>
          </div>
          <Switch label="All AI features" on={data.ai_enabled} disabled={busy} onChange={(v) => update({ ai_enabled: v })} />
        </div>

        <div className={data.ai_enabled ? "" : "pointer-events-none opacity-50"}>
          <p className="text-xs text-muted">Tap a feature to turn just that one off</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {FEATURES.map((f) => {
              const isOff = off.includes(f.key);
              return (
                <li key={f.key}>
                  <button
                    type="button"
                    disabled={busy}
                    aria-pressed={isOff}
                    onClick={() => toggleFeature(f.key)}
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      isOff ? "border-alert/30 bg-alert-soft text-alert line-through" : "border-line bg-white text-muted hover:text-ink"
                    }`}
                  >
                    {f.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
          <div>
            <p className="text-sm font-medium">Reminder emails</p>
            <p className="text-xs text-muted">{data.reminders_enabled ? "On" : "Paused. No reminder goes out, even from the daily run."}</p>
          </div>
          <Switch label="Reminder emails" on={data.reminders_enabled} disabled={busy} onChange={(v) => update({ reminders_enabled: v })} />
        </div>
      </div>

      <ErrorText>{err}</ErrorText>
    </Panel>
  );
}

export function MemberLookup() {
  const [email, setEmail] = useState("");
  const [hits, setHits] = useState<MemberHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await apiGet<{ results: MemberHit[] }>(`/platform/members?email=${encodeURIComponent(email.trim())}`);
      setHits(r.results);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Member lookup">
      <p className="text-sm text-muted">Find which guild someone is in. Read only, and each search is logged.</p>
      <form onSubmit={search} className="mt-3 flex gap-2">
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Part of an email" className={inputCls} />
        <Button disabled={busy || email.trim().length < 3}>{busy ? "Searching…" : "Search"}</Button>
      </form>
      <ErrorText>{err}</ErrorText>
      {hits && (
        <ul className="mt-3 divide-y divide-line text-sm">
          {hits.map((r) => (
            <li key={r.member_id} className="flex flex-wrap items-center gap-x-2 gap-y-1 py-2">
              <span className="font-medium">{r.name}</span>
              <span className="text-xs text-muted">{r.email}</span>
              <span className="rounded bg-paper px-1.5 py-0.5 text-xs">{r.role}</span>
              <a href={`/platform/guild/?id=${r.guild_id}`} className="text-xs text-guild-deep hover:underline">
                {r.guild_name}
              </a>
              {r.guild_status === "suspended" && <span className="text-xs text-alert">suspended</span>}
            </li>
          ))}
          {hits.length === 0 && <li className="py-2 text-muted">No members matched.</li>}
        </ul>
      )}
    </Panel>
  );
}

const FEATURE_LABEL: Record<string, string> = Object.fromEntries(FEATURES.map((f) => [f.key, f.label]));

function describe(a: AuditRow): string {
  const i = a.inputs ?? {};
  if (a.action === "setting.update") {
    const parts: string[] = [];
    if (typeof i.ai_enabled === "boolean") parts.push(`All AI ${i.ai_enabled ? "on" : "off"}`);
    if (typeof i.reminders_enabled === "boolean") parts.push(`Reminder emails ${i.reminders_enabled ? "on" : "off"}`);
    if (Array.isArray(i.ai_disabled_features)) {
      const off = (i.ai_disabled_features as string[]).map((k) => FEATURE_LABEL[k] ?? k);
      parts.push(off.length ? `Off: ${off.join(", ")}` : "All AI features back on");
    }
    return parts.join(" · ");
  }
  if (a.action === "member.lookup" && typeof i.query === "string") return `Searched "${i.query}"`;
  if (typeof i.title === "string") return `"${i.title}"`;
  if (typeof i.mode === "string") return i.mode === "full_pause" ? "Full pause" : "Read only";
  if (typeof i.reason === "string" && i.reason) return `"${i.reason}"`;
  return "";
}

export function AuditLog() {
  const { data } = useSWR<AuditRow[]>("platform-audit", () => apiGet<AuditRow[]>("/platform/audit?limit=50"), {
    refreshInterval: 10_000,
  });
  return (
    <Panel title="Audit log">
      <p className="text-sm text-muted">Every platform action, newest first. Guilds never see this.</p>
      <ul className="mt-3 max-h-96 divide-y divide-line overflow-y-auto text-sm">
        {(data ?? []).map((a) => {
          return (
            <li key={a.id} className="py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{ACTION_LABEL[a.action] ?? a.action}</span>
                <span className="text-xs text-muted">{timeAgo(a.created_at)}</span>
              </div>
              <p className="mt-0.5 text-xs text-muted">
                {describe(a) && <span className="text-ink">{describe(a)}</span>}
                {describe(a) && " · "}
                {a.actor_email}
              </p>
            </li>
          );
        })}
        {data && data.length === 0 && <li className="py-2 text-muted">No platform actions yet.</li>}
      </ul>
    </Panel>
  );
}

