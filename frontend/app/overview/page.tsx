"use client";

import { useMe } from "@/lib/useMe";
import { Onboarding } from "@/components/Onboarding";
import { Dashboard } from "@/components/Dashboard";
import { ErrorText } from "@/components/ui";

export default function Home() {
  const { me, isLoading, noGuild, error } = useMe();
  if (isLoading) return <p className="text-muted">Loading your guild…</p>;
  if (noGuild) return <Onboarding />;
  if (error) return <ErrorText>{error.message}</ErrorText>;
    if (!me) return <p className="text-muted">Loading your guild…</p>;
  return <Dashboard me={me} />;
}