"use client";

import Link from "next/link";
import useSWR from "swr";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { createClient } from "@/lib/supabase";
import { apiGet } from "@/lib/api";
import { usd } from "@/lib/format";
import { useMe } from "@/lib/useMe";
import { useGuild } from "@/lib/useGuild";
import { focusRing } from "./ui";
import { Logo } from "./Logo";
import { Avatar } from "./Avatar";
import { BroadcastBanner, NOTICES_KEY, fetchNotices, type Notices } from "./BroadcastBanner";

const NAV = [
  { href: "/overview/", label: "Home" },
  { href: "/jobs/", label: "Jobs" },
  { href: "/claims/", label: "Claims" },
  { href: "/pool/", label: "Safety pool" },
  { href: "/agent/", label: "Activity" },
];

function Brand() {
  const { me } = useMe();
  const { data: guild } = useGuild(me?.guild_id);
  return (
    <Link href="/overview/" className={`group flex shrink-0 items-center gap-2.5 rounded-md ${focusRing}`}>
      <Logo className="h-9 w-auto" title="" />
      <span className="flex flex-col leading-tight">
        <span className="font-display text-lg font-bold tracking-tight">The Guild</span>
        {guild?.name && (
          <span className="hidden max-w-[11rem] truncate text-xs text-muted group-hover:text-ink sm:block">
            {guild.name}
          </span>
        )}
      </span>
    </Link>
  );
}

// Small gold dot on Claims when an admin has claims waiting for a decision.
function useOpenClaims(isAdmin: boolean) {
  const { data } = useSWR<{ status: string }[]>(
    isAdmin ? ["claims", true] : null,
    () => apiGet<{ status: string }[]>("/claims"),
  );
  return (data ?? []).filter((c) => c.status === "submitted" || c.status === "ai_reviewed").length;
}

function UserMenu({ email }: { email: string }) {
  const { me } = useMe();
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { data: earnings } = useSWR<{ total_cents: number }>(
    me ? "earnings" : null,
    () => apiGet<{ total_cents: number }>("/me/earnings"),
  );

  // Close on outside click or Esc.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const name = me?.name || email.split("@")[0];
  const role = me?.role === "admin" ? "Admin" : "Member";

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={`flex items-center gap-2.5 rounded-full py-1 pl-1 pr-3 hover:bg-paper ${focusRing}`}
      >
        <Avatar name={name} url={me?.avatar_url} size={36} />
        <span className="hidden flex-col items-start leading-tight sm:flex">
          <span className="text-sm font-medium text-ink">{name}</span>
          <span className="text-xs text-muted">{role}</span>
        </span>
        <svg viewBox="0 0 20 20" className="h-4 w-4 text-muted" aria-hidden="true">
          <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={reduce ? false : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 z-40 mt-2 w-[min(17rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-line bg-white shadow-xl shadow-ink/10"
          >
            <div className="flex items-center gap-3 border-b border-line px-4 py-3">
              <Avatar name={name} url={me?.avatar_url} size={40} />
              <div className="min-w-0">
              <p className="truncate font-medium">{name}</p>
              <p className="truncate text-xs text-muted">{email}</p>
              </div>
            </div>
            {earnings && (
              <div className="border-b border-line bg-guild-soft/50 px-4 py-3">
                <p className="text-xs text-muted">You&apos;ve earned</p>
                <p className="font-display text-xl font-semibold tabular-nums text-guild">
                  {usd(earnings.total_cents)}
                </p>
              </div>
            )}
            <Link
              href="/profile/"
              role="menuitem"
              onClick={() => setOpen(false)}
              className={`block px-4 py-2.5 text-sm hover:bg-paper ${focusRing}`}
            >
              My profile
            </Link>
            <button
              role="menuitem"
              onClick={() => createClient().auth.signOut()}
              className={`block w-full border-t border-line px-4 py-2.5 text-left text-sm text-alert hover:bg-alert-soft ${focusRing}`}
            >
              Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const rawPath = usePathname();
  const pathname = rawPath.length > 1 ? rawPath.replace(/\/$/, "") : rawPath;
  const router = useRouter();
  const isLogin = pathname === "/login";
  const isMaintenance = pathname === "/maintenance";
  const isPlatform = pathname.startsWith("/platform");
  const isPublic = pathname === "/" || isLogin;
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { me } = useMe();
  const openClaims = useOpenClaims(me?.role === "admin");

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      const e = data.session?.user.email ?? null;
      setEmail(e);
      setReady(true);
      if (!e && !isPublic) router.replace("/login/");
      if (e && isLogin) window.location.assign("/overview/");
    });
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      setEmail(session?.user.email ?? null);
      if (event === "SIGNED_OUT") window.location.assign("/");
    });
    return () => sub.subscription.unsubscribe();
  }, [isLogin, isPublic, router]);

  // Full pause: send everyone to the maintenance page, and back when it ends.
  // Platform pages stay open so the platform admin can end it.
  const { data: notices } = useSWR<Notices>(ready && email && !isPublic ? NOTICES_KEY : null, fetchNotices, {
    refreshInterval: 20_000,
  });
  const paused = notices?.maintenance?.mode === "full_pause";
  useEffect(() => {
    if (!notices) return;
    if (paused && !isMaintenance && !isPlatform) router.replace("/maintenance/");
    if (!paused && isMaintenance) router.replace("/overview/");
  }, [notices, paused, isMaintenance, isPlatform, router]);

  // Close the mobile menu after navigating.
  useEffect(() => setMobileOpen(false), [pathname]);

  if (isPublic || isMaintenance) return <>{children}</>;
  if (!ready || !email)
    return (
      <div className="min-h-screen">
        <div className="h-16 border-b border-line bg-white" />
      </div>
    );

  const active = (href: string) => {
    const h = href.replace(/\/$/, "") || "/";
    return h === "/" ? pathname === "/" : pathname.startsWith(h);
  };

  const links = (mobile: boolean) =>
    NAV.map((n) => {
      const on = active(n.href);
      const dot = n.href === "/claims/" && openClaims > 0;
      return (
        <Link
          key={n.href}
          href={n.href}
          aria-current={on ? "page" : undefined}
          className={
            mobile
              ? `flex items-center justify-between rounded-md px-3 py-2.5 text-sm ${on ? "bg-guild-soft font-medium text-guild" : "text-ink hover:bg-paper"} ${focusRing}`
              : `relative whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm transition-colors ${on ? "bg-guild-soft font-medium text-guild-deep" : "text-muted hover:bg-paper hover:text-ink"} ${focusRing}`
          }
        >
          {n.label}
          {dot && (
            <span
              className={mobile ? "rounded-full bg-seal px-2 text-xs text-white" : "absolute right-1 top-1 h-2 w-2 rounded-full bg-seal ring-2 ring-white"}
              aria-label={`${openClaims} waiting`}
            >
              {mobile ? openClaims : null}
            </span>
          )}
        </Link>
      );
    });

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line/80 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-6 lg:gap-8">
            <Brand />
            <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
              {links(false)}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <UserMenu email={email} />
            <button
              onClick={() => setMobileOpen((o) => !o)}
              aria-expanded={mobileOpen}
              aria-label="Menu"
              className={`grid h-9 w-9 place-items-center rounded-md text-ink hover:bg-paper md:hidden ${focusRing}`}
            >
              <svg viewBox="0 0 20 20" className="h-5 w-5" aria-hidden="true">
                <path
                  d={mobileOpen ? "M5 5l10 10M15 5L5 15" : "M3 6h14M3 10h14M3 14h14"}
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        </div>
        {mobileOpen && (
          <nav className="space-y-1 border-t border-line px-4 py-3 md:hidden" aria-label="Main">
            {links(true)}
          </nav>
        )}
      </header>
      <BroadcastBanner />
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">{children}</main>
    </div>
  );
}
