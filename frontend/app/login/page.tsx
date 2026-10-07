"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";
import { Button, ErrorText, inputCls } from "@/components/ui";

const DEMO = [
  { name: "Maya", role: "guild admin", email: "maya@guild.test", password: "maya@123" },
  { name: "Leo", role: "React developer", email: "leo@guild.test", password: "leo@123" },
  { name: "Sara", role: "copywriter", email: "sara@guild.test", password: "sara@123" },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn(e: string, p: string, signup = false) {
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const { error } = signup
      ? await supabase.auth.signUp({ email: e, password: p })
      : await supabase.auth.signInWithPassword({ email: e, password: p });
    setBusy(false);
    if (error) return setError(error.message);
    router.replace("/");
  }

  return (
    <main className="grid min-h-screen place-items-center px-5 py-12">
      <div className="w-full max-w-md">
        <h1 className="font-display text-4xl font-bold tracking-tight">The Guild</h1>
        <p className="mt-2 text-muted">
          Freelancers share overflow work, split every payment fairly, and cover each other when a client never pays.
        </p>

        <form onSubmit={(e) => { e.preventDefault(); signIn(email, password, mode === "signup"); }}
          className="mt-8 space-y-3 rounded-lg border border-line bg-white p-6">
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
            {busy ? "Signing in…" : mode === "signin" ? "Sign in" : "Create account"}
          </Button>
          <button type="button" onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
            className="w-full text-sm text-muted hover:text-ink">
            {mode === "signin" ? "New here? Create an account" : "Have an account? Sign in"}
          </button>
        </form>

        <div className="mt-6">
          <p className="text-sm text-muted">Exploring the demo? Sign in as a guild member:</p>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {DEMO.map((d) => (
              <button key={d.email} disabled={busy} onClick={() => signIn(d.email, d.password)}
                className="rounded-md border border-line bg-white px-3 py-2 text-left hover:border-guild disabled:opacity-50">
                <span className="block text-sm font-medium">{d.name}</span>
                <span className="block text-xs text-muted">{d.role}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}