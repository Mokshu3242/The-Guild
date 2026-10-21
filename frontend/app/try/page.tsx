"use client";

import { useState } from "react";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { createClient } from "@/lib/supabase";
import { DEMO } from "@/lib/demo";

const LOOK_FOR = [
  { title: "The money trail", body: "Jobs → Bloom Studio → Money trail. Every PayPal step with its real ID." },
  { title: "The safety pool", body: "Pool page. What the pool covered, what came back, and who was paid early." },
  { title: "The agent log", body: "Activity page. Every AI suggestion, rule and human decision, in plain words." },
  { title: "The client side", body: "Open any job's client link to see what the client sees and signs." },
];

/** 14A Judge mode. Public: no login needed to see this page. */
export default function TryPage() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function enter(email: string, password: string) {
    setBusy(email);
    setError(null);
    const supabase = createClient();
    await supabase.auth.signOut();   // switching roles: drop whoever was signed in
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      setError(
        error.message === "Invalid login credentials"
          ? "That demo login isn't set up yet. Try another one."
          : error.message,
      );
      setBusy(null);
      return;
    }
    window.location.assign("/overview/");
  }

  return (
    <main className="min-h-screen bg-paper">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-16">
        <Link href="/" className="inline-flex items-center gap-2 font-display text-lg font-bold tracking-tight">
          <Logo className="h-7 w-auto" title="" />
          The Guild
        </Link>

        <h1 className="mt-10 font-display text-4xl font-bold tracking-tight sm:text-5xl">Try the demo</h1>
        <p className="mt-3 max-w-xl text-muted">
          Pick who to be. One click, no sign-up. Everything runs on PayPal sandbox, so the money is fake but every
          PayPal call is real.
        </p>

        <div className="mt-8 grid gap-3">
          {DEMO.map((d) => (
            <button
              key={d.email}
              disabled={!!busy}
              onClick={() => enter(d.email, d.password)}
              className="group flex w-full items-center gap-4 rounded-xl border border-line bg-white p-5 text-left transition-colors hover:border-guild focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40 disabled:opacity-50"
            >
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-guild-deep font-display text-xl font-bold text-white">
                {d.name[0]}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-display text-lg font-semibold">
                  {d.name} <span className="text-sm font-normal text-muted">· {d.role}</span>
                </span>
                <span className="mt-0.5 block text-sm text-muted">{d.blurb}</span>
              </span>
              <span className="shrink-0 text-sm text-muted group-hover:text-ink">
                {busy === d.email ? "Opening…" : "Enter"}
              </span>
            </button>
          ))}
        </div>
        {error && (
          <p role="alert" className="mt-4 text-sm text-alert">
            {error}
          </p>
        )}

        <h2 className="mt-12 font-display text-xl font-bold">Worth a look</h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {LOOK_FOR.map((l) => (
            <li key={l.title} className="rounded-lg border border-line bg-white p-4">
              <p className="font-medium">{l.title}</p>
              <p className="mt-1 text-sm text-muted">{l.body}</p>
            </li>
          ))}
        </ul>

        <p className="mt-10 text-xs text-muted">
          Demo accounts only. The admin view is read-only, so the demo stays the same for everyone who visits.
        </p>
      </div>
    </main>
  );
}
