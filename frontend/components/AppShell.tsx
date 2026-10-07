"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { mutate } from "swr";
import { createClient } from "@/lib/supabase";
import { useMe } from "@/lib/useMe";
import { useGuild } from "@/lib/useGuild";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/jobs", label: "Jobs" },
  { href: "/claims", label: "Claims" },
  { href: "/pool", label: "Pool" },
  { href: "/agent", label: "Agent log" },
];

const clearCache = () => mutate(() => true, undefined, { revalidate: false });

function Brand() {
  const { me } = useMe();
  const { data: guild } = useGuild(me?.guild_id);
  return (
    <Link href="/" className="group flex flex-col leading-tight focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40 rounded-sm">
      <span className="font-display text-xl font-bold tracking-tight">The Guild</span>
      <span className="min-h-4 text-xs text-muted group-hover:text-ink">{guild?.name ?? ""}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/login";
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      const e = data.session?.user.email ?? null;
      setEmail(e);
      setReady(true);
      if (!e && !isLogin) router.replace("/login");
      if (e && isLogin) router.replace("/");
    });
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      setEmail(session?.user.email ?? null);
      if (event === "SIGNED_IN" || event === "SIGNED_OUT") clearCache();
      if (event === "SIGNED_OUT") router.replace("/login");
    });
    return () => sub.subscription.unsubscribe();
  }, [isLogin, router]);

  if (isLogin) return <>{children}</>;
  if (!ready || !email) return null;

  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3">
          <div className="flex items-center gap-8">
            <Brand />
            <nav className="flex gap-1 overflow-x-auto text-sm" aria-label="Main">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active(n.href) ? "page" : undefined}
                  className={`whitespace-nowrap rounded-sm border-b-2 px-2.5 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40 ${
                    active(n.href) ? "border-guild font-medium text-ink" : "border-transparent text-muted hover:text-ink"
                  }`}
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="hidden text-muted sm:inline">{email}</span>
            <button
              onClick={() => createClient().auth.signOut()}
              className="rounded-sm text-muted hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-guild/40"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
    </div>
  );
}