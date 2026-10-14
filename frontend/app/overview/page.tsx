"use client";

import { useMe } from "@/lib/useMe";
import { Onboarding } from "@/components/Onboarding";
import { Dashboard } from "@/components/Dashboard";
import { ErrorText, Skeleton } from "@/components/ui";

function Loading() {
  return (
    <div className="space-y-6" aria-label="Loading your guild">
      <Skeleton className="h-48 rounded-2xl" />
      <Skeleton className="h-24" />
      <Skeleton className="h-72" />
    </div>
  );
}

export default function Home() {
  const { me, isLoading, noGuild, error } = useMe();
  if (isLoading) return <Loading />;
  if (noGuild) return <Onboarding />;
  if (error) return <ErrorText>{error.message}</ErrorText>;
  if (!me) return <Loading />;
  return <Dashboard me={me} />;
}
