"use client";

import { useEffect, useState } from "react";
import { apiPatch } from "@/lib/api";
import { useMe } from "@/lib/useMe";
import { Button, ErrorText, Notice, Panel, inputCls } from "@/components/ui";

export default function ProfilePage() {
  const { me, refresh } = useMe();
  const [f, setF] = useState({ name: "", paypal_email: "", skills: "", rate: "", available: true });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (me) setF({
      name: me.name,
      paypal_email: me.paypal_email,
      skills: me.skills.join(", "),
      rate: String(me.hourly_rate_cents / 100),
      available: me.available,
    });
  }, [me]);

  if (!me) return <p className="text-muted">Loading your profile…</p>;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null); setNotice(null);
    try {
      await apiPatch("/me", {
        name: f.name.trim(),
        paypal_email: f.paypal_email.trim(),
        skills: f.skills.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
        hourly_rate_cents: Math.round(Number(f.rate || 0) * 100),
        available: f.available,
      });
      await refresh();
      setNotice("Profile saved. The AI uses this the next time it matches a job.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Couldn't save your profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl font-bold">Your profile</h1>
        <p className="mt-2 text-muted">The AI matches jobs using your skills, rate, and availability.</p>
      </div>

      <Panel title="Details">
        <form onSubmit={save} className="space-y-4">
          <label className="block text-sm font-medium">Name
            <input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className={`${inputCls} mt-1`} />
          </label>
          <label className="block text-sm font-medium">PayPal email
            <input type="email" value={f.paypal_email} onChange={(e) => setF({ ...f, paypal_email: e.target.value })} className={`${inputCls} mt-1`} />
            <span className="mt-1 block text-xs font-normal text-muted">Your share of every payment goes here.</span>
          </label>
          <label className="block text-sm font-medium">Skills
            <input value={f.skills} onChange={(e) => setF({ ...f, skills: e.target.value })} className={`${inputCls} mt-1`}
              placeholder="react, tailwind, copywriting" />
            <span className="mt-1 block text-xs font-normal text-muted">Separate with commas.</span>
          </label>
          <label className="block text-sm font-medium">Hourly rate in dollars
            <input type="number" min="0" step="1" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} className={`${inputCls} mt-1`} />
          </label>
          <label className="flex items-center gap-3 text-sm font-medium">
            <input type="checkbox" checked={f.available} onChange={(e) => setF({ ...f, available: e.target.checked })}
              className="h-4 w-4 accent-[#1e6b52]" />
            Available for new work
          </label>
          <ErrorText>{err}</ErrorText>
          <Notice>{notice}</Notice>
          <Button disabled={busy}>{busy ? "Saving…" : "Save profile"}</Button>
        </form>
      </Panel>

      <Panel title="Account">
        <p className="text-sm text-muted">Signed in as {me.email}. Role: {me.role === "admin" ? "guild admin" : "member"}.</p>
      </Panel>
    </div>
  );
}