"use client";

import { useState } from "react";
import useSWR from "swr";
import { createClient } from "@/lib/supabase";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui";
import { NOTICES_KEY, fetchNotices, type Notices } from "@/components/BroadcastBanner";

export default function MaintenancePage() {
  const { data } = useSWR<Notices>(NOTICES_KEY, fetchNotices, { refreshInterval: 15_000 });
  const [leaving, setLeaving] = useState(false);
  const m = data?.maintenance;
  const back = m?.ends_at ? new Date(m.ends_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;

  async function signOut() {
    setLeaving(true);
    // AppShell sends everyone to the home page when they sign out.
    await createClient().auth.signOut();
    window.location.assign("/");
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper px-4 py-12">
      <div className="max-w-md text-center">
        <Logo className="mx-auto h-14 w-auto" title="The Guild" />
        <h1 className="mt-6 font-display text-3xl font-bold tracking-tight">We&apos;ll be right back</h1>
        <p className="mt-3 text-muted">{m?.message ?? "The Guild is down for a short maintenance."}</p>
        {back && <p className="mt-2 text-sm text-muted">Expected back around {back}.</p>}

        <p className="mt-8 rounded-xl border border-line bg-white px-4 py-3 text-sm text-muted">
          Payments still go through while we work. Anything a client pays now is split and paid out as normal.
        </p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Button variant="quiet" disabled={leaving} onClick={signOut}>
            {leaving ? "Signing out…" : "Sign out"}
          </Button>
          <a
            href="/"
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-muted hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/50"
          >
            Go to the home page
          </a>
        </div>

        <p className="mt-4 text-xs text-muted">This page checks again on its own every 15 seconds.</p>
      </div>
    </main>
  );
}