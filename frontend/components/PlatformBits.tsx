"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";

export interface GuildRow {
  id: string;
  name: string;
  status: "active" | "maintenance" | "suspended";
  pool_health: "healthy" | "watch" | "underfunded" | "unknown";
  member_count: number;
  admin_count: number;
  active_jobs: number;
  finished_jobs: number;
  waiting_claims: number;
  last_activity_at: string | null;
  created_at: string | null;
  attention_reasons: string[];
}

export const HEALTH: Record<GuildRow["pool_health"], { label: string; cls: string }> = {
  healthy: { label: "Pool healthy", cls: "bg-guild-soft text-guild" },
  watch: { label: "Pool: keep an eye on it", cls: "bg-seal-soft text-seal" },
  underfunded: { label: "Pool underfunded", cls: "bg-alert-soft text-alert" },
  unknown: { label: "Pool unknown", cls: "bg-paper text-muted" },
};

export const GUILD_STATUS: Record<GuildRow["status"], { label: string; cls: string }> = {
  active: { label: "Active", cls: "bg-guild-soft text-guild" },
  maintenance: { label: "Maintenance", cls: "bg-seal-soft text-seal" },
  suspended: { label: "Suspended", cls: "bg-alert-soft text-alert" },
};

/** Anyone who isn't a platform admin gets sent home, quietly. */
export function useKickOutIfNotAllowed(error: unknown) {
  const router = useRouter();
  useEffect(() => {
    if (error instanceof ApiError && (error.status === 403 || error.status === 401)) router.replace("/");
  }, [error, router]);
  return error instanceof ApiError && (error.status === 403 || error.status === 401);
}

export function Chip({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}
