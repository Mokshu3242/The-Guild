"use client";

import useSWR from "swr";
import { apiGet } from "@/lib/api";

export interface Badge {
  key: string;
  label: string;
  tone: "guild" | "seal" | "ink";
}

const TONE: Record<Badge["tone"], string> = {
  guild: "bg-guild-soft text-guild",
  seal: "bg-seal-soft text-seal",
  ink: "bg-guild-deep text-seal-bright",
};

export function TrustBadges({ memberId, className = "" }: { memberId: string; className?: string }) {
  const { data } = useSWR<{ badges: Badge[] }>(["badges", memberId], () =>
    apiGet<{ badges: Badge[] }>(`/members/${memberId}/badges`),
  );
  if (!data || data.badges.length === 0) return null;
  return (
    <ul className={`flex flex-wrap gap-1.5 ${className}`} aria-label="Trust badges">
      {data.badges.map((b) => (
        <li key={b.key} className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE[b.tone] ?? TONE.guild}`}>
          {b.label}
        </li>
      ))}
    </ul>
  );
}