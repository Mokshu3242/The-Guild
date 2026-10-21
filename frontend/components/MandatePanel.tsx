"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { apiGet, apiPut } from "@/lib/api";
import { usd } from "@/lib/format";
import { Button, ErrorText, Notice, Panel, inputCls } from "@/components/ui";

interface Mandate {
  active: boolean;
  remind_max_tier: number;
  auto_claim: boolean;
  claim_max_cents: number;
  claim_min_confidence: number;
  auto_advance: boolean;
  advance_max_cents: number;
  saved: boolean;
  set_by: string;
  set_by_ok: boolean;
  updated_at: string | null;
  paused: string | null;
  weekly_limit: number;
  used_this_week: { claim: number; advance: number };
}
type Form = Pick<
  Mandate,
  | "active"
  | "remind_max_tier"
  | "auto_claim"
  | "claim_max_cents"
  | "claim_min_confidence"
  | "auto_advance"
  | "advance_max_cents"
>;

const TIERS = [
  { v: 0, label: "None. A person sends every reminder." },
  { v: 1, label: "Friendly only (tier 1)" },
  { v: 2, label: "Friendly and firm (tiers 1 and 2)" },
  { v: 3, label: "All three, including the final one" },
];

function pick(m: Mandate): Form {
  const { active, remind_max_tier, auto_claim, claim_max_cents, claim_min_confidence, auto_advance, advance_max_cents } = m;
  return { active, remind_max_tier, auto_claim, claim_max_cents, claim_min_confidence, auto_advance, advance_max_cents };
}

function Dollars({ cents, onChange, label }: { cents: number; onChange: (c: number) => void; label: string }) {
  return (
    <label className="block text-xs text-muted">
      {label}
      <div className="relative mt-1">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted">$</span>
        <input
          type="number"
          min={0}
          max={1000}
          step={1}
          value={Math.round(cents / 100)}
          onChange={(e) => onChange(Math.max(0, Math.min(1000, Math.round(Number(e.target.value || 0)))) * 100)}
          className={`${inputCls} pl-7`}
        />
      </div>
    </label>
  );
}

/** 13B. What the agent may do on its own. Admins only. */
export function MandatePanel() {
  const { data, mutate } = useSWR<Mandate>("mandate", () => apiGet<Mandate>("/mandates"));
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (data && !form) setForm(pick(data));
  }, [data, form]);

  if (!data || !form) return null;
  const f = form;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm({ ...f, [k]: v });
  const changed = JSON.stringify(f) !== JSON.stringify(pick(data));

  async function save() {
    setBusy(true);
    setErr(null);
    setNotice(null);
    try {
      const m = await apiPut<Mandate>("/mandates", f);
      await mutate(m, { revalidate: false });
      setForm(pick(m));
      setNotice("Saved. You answer for what the agent does under it from now on.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't save the mandate");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Agent mandate">
      <p className="text-sm text-muted">
        Small, clear things the agent can do without a click. Anything outside these limits still comes to an admin.
        Every action is logged with the admin who set the rule.
      </p>

      {data.paused && (
        <p className="mt-3 rounded-md bg-alert-soft px-3 py-2 text-sm text-alert">
          Paused: {data.paused} Nothing runs on its own until it&apos;s back on.
        </p>
      )}
      {data.saved && !data.set_by_ok && (
        <p className="mt-3 rounded-md bg-alert-soft px-3 py-2 text-sm text-alert">
          {data.set_by} set this but isn&apos;t an admin any more, so claims and advances wait for a person. Save it to
          take it over.
        </p>
      )}

      <label className="mt-4 flex items-start gap-3 rounded-lg border border-line bg-paper px-4 py-3">
        <input
          type="checkbox"
          checked={f.active}
          onChange={(e) => set("active", e.target.checked)}
          className="mt-1 h-4 w-4 accent-guild"
        />
        <span>
          <span className="block font-medium">Mandate on</span>
          <span className="text-xs text-muted">Off means a person clicks for everything, reminders too.</span>
        </span>
      </label>

      <fieldset disabled={!f.active} className="mt-5 space-y-6 disabled:opacity-50">
        <div>
          <p className="font-medium">Payment reminders</p>
          <p className="text-xs text-muted">The daily run sends these on its own. Higher tiers wait for an admin.</p>
          <select
            value={f.remind_max_tier}
            onChange={(e) => set("remind_max_tier", Number(e.target.value))}
            className={`${inputCls} mt-2 sm:max-w-sm`}
          >
            {TIERS.map((t) => (
              <option key={t.v} value={t.v}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="flex items-center gap-2.5 font-medium">
            <input
              type="checkbox"
              checked={f.auto_claim}
              onChange={(e) => set("auto_claim", e.target.checked)}
              className="h-4 w-4 accent-guild"
            />
            Pay small claims
          </label>
          <p className="mt-1 text-xs text-muted">
            Only when the AI says approve with no red flags, and the pool keeps at least a quarter of its money.
            {data.auto_claim && ` ${data.used_this_week.claim} of ${data.weekly_limit} used this week.`}
          </p>
          {f.auto_claim && (
            <div className="mt-2 grid gap-3 sm:max-w-sm sm:grid-cols-2">
              <Dollars label="Up to" cents={f.claim_max_cents} onChange={(c) => set("claim_max_cents", c)} />
              <label className="block text-xs text-muted">
                AI at least this sure
                <select
                  value={f.claim_min_confidence}
                  onChange={(e) => set("claim_min_confidence", Number(e.target.value))}
                  className={`${inputCls} mt-1`}
                >
                  {[70, 75, 80, 85, 90, 95].map((n) => (
                    <option key={n} value={n}>
                      {n}%
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}
        </div>

        <div>
          <label className="flex items-center gap-2.5 font-medium">
            <input
              type="checkbox"
              checked={f.auto_advance}
              onChange={(e) => set("auto_advance", e.target.checked)}
              className="h-4 w-4 accent-guild"
            />
            Pay small advances
          </label>
          <p className="mt-1 text-xs text-muted">
            Every &quot;Get paid now&quot; rule still applies. This only skips the click.
            {data.auto_advance && ` ${data.used_this_week.advance} of ${data.weekly_limit} used this week.`}
          </p>
          {f.auto_advance && (
            <div className="mt-2 sm:max-w-[12rem]">
              <Dollars label="Up to" cents={f.advance_max_cents} onChange={(c) => set("advance_max_cents", c)} />
            </div>
          )}
        </div>
      </fieldset>

      <p className="mt-5 text-xs text-muted">
        At most {data.weekly_limit} claims and {data.weekly_limit} advances a week run on their own. A request from the
        admin who set the mandate always goes to another admin.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={busy || (!changed && data.saved)}>
          {busy ? "Saving…" : data.saved ? "Save changes" : "Save mandate"}
        </Button>
        {data.saved && data.updated_at && (
          <span className="text-xs text-muted">
            Set by {data.set_by}, {new Date(data.updated_at).toLocaleDateString()}. Limits go up to {usd(100_000)}.
          </span>
        )}
      </div>
      <ErrorText>{err}</ErrorText>
      {notice && <Notice>{notice}</Notice>}
    </Panel>
  );
}
