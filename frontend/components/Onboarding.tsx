"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { Button, ErrorText, inputCls } from "@/components/ui";

export function Onboarding() {
  const { refresh } = useMe();
  const [tab, setTab] = useState<"join" | "create">("join");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [f, setF] = useState({ guild: "", code: "", name: "", paypal: "", skills: "", rate: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      if (tab === "create") {
        await apiPost("/guilds", { name: f.guild, your_name: f.name });
      } else {
        await apiPost("/guilds/join", {
          invite_code: f.code.trim(),
          name: f.name,
          paypal_email: f.paypal,
          skills: f.skills.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
          hourly_rate_cents: Math.round(Number(f.rate || 0) * 100),
        });
      }
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="font-display text-3xl font-bold">Join your guild</h1>
      <p className="mt-2 text-muted">Ask your guild admin for an invite code, or start a new guild and invite others.</p>

      <div className="mt-6 inline-flex rounded-md border border-line bg-white p-1 text-sm" role="tablist">
        {(["join", "create"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded px-3 py-1.5 ${tab === t ? "bg-guild text-white" : "text-muted hover:text-ink"}`}>
            {t === "join" ? "I have a code" : "Start a guild"}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="mt-4 space-y-3 rounded-lg border border-line bg-white p-6">
        {tab === "create" ? (
          <input required placeholder="Guild name, like Design Collective" value={f.guild} onChange={set("guild")} className={inputCls} />
        ) : (
          <input required placeholder="Invite code" value={f.code} onChange={set("code")} className={inputCls} />
        )}
        <input required placeholder="Your name" value={f.name} onChange={set("name")} className={inputCls} />
        {tab === "join" && (
          <>
            <input type="email" placeholder="PayPal email for payouts" value={f.paypal} onChange={set("paypal")} className={inputCls} />
            <input placeholder="Skills, separated by commas" value={f.skills} onChange={set("skills")} className={inputCls} />
            <input type="number" min="0" step="1" placeholder="Hourly rate in dollars" value={f.rate} onChange={set("rate")} className={inputCls} />
          </>
        )}
        <ErrorText>{err}</ErrorText>
        <Button disabled={busy} className="w-full">
          {busy ? "Saving…" : tab === "create" ? "Start guild" : "Join guild"}
        </Button>
      </form>
    </div>
  );
}