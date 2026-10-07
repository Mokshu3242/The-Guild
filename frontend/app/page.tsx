"use client";

import Link from "next/link";
import { useState } from "react";
import { createClient } from "@/lib/supabase";
import { SplitBar } from "@/components/SplitBar";

const DEMO = [
  { name: "Maya", role: "guild admin", email: "maya@guild.test", password: "maya@123" },
  { name: "Leo", role: "React developer", email: "leo@guild.test", password: "leo@123" },
  { name: "Sara", role: "copywriter", email: "sara@guild.test", password: "sara@123" },
];

const STEPS = [
  {
    title: "Share work you can't take",
    body: "Post a job to the guild. The AI picks the best member for it and explains why.",
  },
  {
    title: "Get paid, split fairly",
    body: "The client pays a PayPal invoice. The worker, the member who found the client, and the pool are paid out automatically.",
  },
  {
    title: "Covered when a client ghosts",
    body: "File a claim. The AI checks it for red flags. A guild admin decides, and the pool pays.",
  },
];

export default function Landing() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function tryAs(email: string, password: string) {
    setBusy(email);
    setError(null);
    const { error } = await createClient().auth.signInWithPassword({ email, password });
    if (error) {
      setError(error.message);
      setBusy(null);
      return;
    }
    window.location.assign("/overview/");
  }

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-5 py-5">
        <span className="font-display text-xl font-bold tracking-tight">The Guild</span>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/login/" className="text-muted hover:text-ink">Sign in</Link>
          <Link href="/login/#signup" className="rounded-md bg-guild px-3.5 py-2 font-medium text-white hover:bg-guild/90">
            Start a guild
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-5">
        <section className="grid items-center gap-10 py-14 lg:grid-cols-2">
          <div>
            <h1 className="font-display text-5xl font-bold leading-[1.05] tracking-tight sm:text-6xl">
              Freelancers, acting like a company.
            </h1>
            <p className="mt-5 max-w-md text-lg text-muted">
              A small guild shares overflow work, splits every payment fairly, and keeps a shared pool for when a client never pays.
            </p>
          </div>

          <div className="rounded-lg border border-line bg-white p-6">
            <p className="text-sm font-medium">When a client pays $100</p>
            <div className="mt-4">
              <SplitBar amount={10000} workerPct={85} referrerPct={10} poolPct={5}
                workerName="Member who did the work" referrerName="Member who brought the client" />
            </div>
            <p className="mt-4 text-sm text-muted">Paid out through PayPal the moment the invoice clears.</p>
          </div>
        </section>

        <section className="border-t border-line py-14">
          <h2 className="font-display text-2xl font-bold">How a guild works</h2>
          <ol className="mt-8 grid gap-8 sm:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className="font-display text-3xl font-bold text-guild">{i + 1}</span>
                <h3 className="mt-2 font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-line py-14">
          <div className="grid gap-8 lg:grid-cols-2">
            <div>
              <h2 className="font-display text-2xl font-bold">AI suggests. Rules calculate. People decide.</h2>
              <p className="mt-3 max-w-md text-muted">
                The AI matches jobs, reviews claims, and writes polite payment reminders. It never moves money on its own.
                Every decision is logged in plain words, so the whole guild can see why.
              </p>
            </div>
            <div>
              <h2 className="font-display text-2xl font-bold">Try it with fake money</h2>
              <p className="mt-3 text-muted">Everything runs on PayPal sandbox. Step into the demo guild as one of its members:</p>
              <div className="mt-4 grid grid-cols-3 gap-2">
                {DEMO.map((d) => (
                  <button key={d.email} disabled={!!busy} onClick={() => tryAs(d.email, d.password)}
                    className="rounded-md border border-line bg-white px-3 py-2.5 text-left hover:border-guild focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40 disabled:opacity-50">
                    <span className="block text-sm font-medium">{busy === d.email ? "Opening…" : d.name}</span>
                    <span className="block text-xs text-muted">{d.role}</span>
                  </button>
                ))}
              </div>
              {error && <p role="alert" className="mt-3 text-sm text-alert">{error}</p>}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line py-6 text-center text-xs text-muted">
        Built for the PayPal AI Hackathon. Payments by PayPal sandbox.
      </footer>
    </div>
  );
}