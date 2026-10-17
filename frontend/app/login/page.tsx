"use client";

import Link from "next/link";
import { Logo } from "@/components/Logo";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase";
import { Button, ErrorText, inputCls } from "@/components/ui";

const DEMO = [
  { name: "Maya", role: "guild admin", email: "maya@guild.test", password: "maya@123" },
  { name: "Leo", role: "React developer", email: "leo@guild.test", password: "leo@123" },
  { name: "Sara", role: "copywriter", email: "sara@guild.test", password: "sara@123" },
];

export default function LoginPage() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (window.location.hash === "#signup") setMode("signup");
  }, []);

  async function signIn(e: string, p: string, signup = false) {
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const { error } = signup
      ? await supabase.auth.signUp({ email: e, password: p })
      : await supabase.auth.signInWithPassword({ email: e, password: p });
    if (error) {
      setBusy(false);
      return setError(error.message);
    }
    window.location.assign("/overview/");
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper px-4 py-12">
      <div className="w-full max-w-sm">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1.5 rounded-md text-sm text-muted hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/50"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
            <path d="M12 5l-5 5 5 5" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to home
        </Link>
        <h1 className="mt-8 font-display text-3xl font-bold tracking-tight">
          {mode === "signin" ? "Welcome back" : "Create your account"}
        </h1>

        <form onSubmit={(ev) => { ev.preventDefault(); signIn(email, password, mode === "signup"); }}
          className="mt-6 space-y-4 rounded-xl border border-line bg-white p-5 shadow-sm sm:p-6">
          <label className="block text-sm font-medium">
            Email
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={`${inputCls} mt-1`} />
          </label>
          <label className="block text-sm font-medium">
            Password
            <input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className={`${inputCls} mt-1`} />
          </label>
          <ErrorText>{error}</ErrorText>
          <Button disabled={busy} className="w-full">
            {busy ? "One moment…" : mode === "signin" ? "Sign in" : "Create account"}
          </Button>
          <button type="button" onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
            className="w-full text-sm text-muted hover:text-ink">
            {mode === "signin" ? "New here? Create an account" : "Have an account? Sign in"}
          </button>
        </form>

        <p className="mt-6 text-sm text-muted">Or open the demo as:</p>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {DEMO.map((d) => (
            <button key={d.email} disabled={busy} onClick={() => signIn(d.email, d.password)}
              className="rounded-lg border border-line bg-white px-3 py-2.5 text-left transition-colors hover:border-guild focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/50 disabled:opacity-50">
              <span className="block text-sm font-medium">{d.name}</span>
              <span className="block text-xs text-muted">{d.role}</span>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}