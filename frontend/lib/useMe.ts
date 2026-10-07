"use client";

import useSWR from "swr";
import { apiGet, ApiError } from "./api";

export interface Me {
  id: string;
  guild_id: string;
  name: string;
  email: string;
  paypal_email: string;
  skills: string[];
  hourly_rate_cents: number;
  available: boolean;
  role: "admin" | "member";
}

export function useMe() {
  const { data, error, isLoading, mutate } = useSWR<Me>("me", () => apiGet<Me>("/me"), {
    shouldRetryOnError: false,
  });
  const noGuild = error instanceof ApiError && error.status === 404;
  return { me: data, isLoading, error, noGuild, refresh: mutate };
}