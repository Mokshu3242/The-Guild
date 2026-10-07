"use client";

import useSWR from "swr";
import { apiGet } from "./api";
import type { Me } from "./useMe";

export interface Guild {
  id: string;
  name: string;
  invite_code: string;
  pool_balance: number;
  worker_pct: number;
  referrer_pct: number;
  pool_pct: number;
  monthly_fee: number;
  claim_cap_pct: number;
}

export function useGuild(guildId?: string) {
  return useSWR<Guild>(guildId ? ["guild", guildId] : null, () => apiGet<Guild>(`/guilds/${guildId}`));
}

export function useMembers(guildId?: string) {
  return useSWR<Me[]>(guildId ? ["members", guildId] : null, () => apiGet<Me[]>(`/guilds/${guildId}/members`));
}